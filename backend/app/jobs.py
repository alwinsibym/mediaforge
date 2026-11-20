"""Background playlist jobs: convert many videos, one after another."""

import atexit
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import (
    config,
    downloader,
    errors,
    history,
    pending,
    settings,
    transcoder,
    validators,
)
from . import (
    features as features_mod,
)
from . import (
    tweaks as tweaks_mod,
)
from .downloader import BotCheckError, ConversionError, NetworkError

MAX_KEPT_JOBS = 10

# When YouTube asks "are you a bot", wait this long (seconds) before each new attempt.
BOT_CHECK_WAITS = (45, 90)
# When the internet connection to the site drops, wait this long (seconds) before each new attempt.
NETWORK_WAITS = (15, 45, 120)
# After this many videos in a row cannot reach the site, the rest of the job is left for later.
NETWORK_STOP_AFTER = 3
# How long (seconds) to wait for the internet to come back before giving up on a video.
OFFLINE_MAX_WAIT = 30 * 60
OFFLINE_POLL = 3.0
# After this many videos in a row are refused, the rest of the job is left for later.
BOT_CHECK_STOP_AFTER = 2
# Videos of one playlist start at least this far apart (seconds), so the site is not hammered.
PACE_MIN, PACE_MAX = 1.5, 4.0

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mediaforge-job")
_lock = threading.Lock()
_jobs: "OrderedDict[str, Job]" = OrderedDict()


@dataclass
class Item:
    index: int
    title: str
    url: str
    status: str = "queued"  # queued, running, done, failed, skipped
    error: str | None = None
    filename: str | None = None
    # Live progress of the step in progress.
    phase: str | None = None
    percent: float | None = None
    speed: float | None = None  # bytes per second
    eta: float | None = None  # seconds left
    note: str | None = None
    error_info: dict | None = None
    number: int = 0  # position shown in the file name and track number (0 means `index`)
    source: Path | None = None  # an uploaded file to convert instead of a link
    path: Path | None = None  # the finished file, when it is kept for the browser


@dataclass
class Job:
    id: str
    title: str
    fmt: str
    quality: str
    items: list[Item]
    save_to_folder: bool
    make_zip: bool
    staging: Path
    mute: bool = False
    browser_download: bool = False  # keep the file for the browser to download
    status: str = "queued"  # queued, running, done, cancelled
    folder: Path | None = None
    zip_path: Path | None = None
    produced: list[Path] = field(default_factory=list)
    cancel_requested: bool = False
    features: features_mod.Features = field(default_factory=features_mod.Features)
    tweaks: tweaks_mod.Tweaks = field(default_factory=tweaks_mod.Tweaks)
    audio_file: Path | None = None
    subtitle_file: Path | None = None
    cover_file: Path | None = None
    parallel: int = 1  # items worked on at the same time
    blocked: bool = False  # the job stopped early because the site kept refusing or was unreachable
    blocked_reason: str = ""  # "sign-in" or "network"
    network_streak: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    next_start: float = 0.0
    block_streak: int = 0


def _unique_folder(base: Path, name: str) -> Path:
    candidate = base / name
    counter = 2
    while candidate.exists():
        candidate = base / f"{name} ({counter})"
        counter += 1
    return candidate


def _forget(job: Job) -> None:
    shutil.rmtree(job.staging, ignore_errors=True)


def start_job(
    title: str,
    items: list[dict],
    fmt: str,
    quality: str,
    save_to_folder: bool,
    make_zip: bool,
    mute: bool = False,
    browser_download: bool = False,
    features: features_mod.Features | None = None,
    folder: Path | None = None,
    options: dict | None = None,
) -> Job:
    """Validate a request, register the job and queue it.

    `options` are the extras as the person chose them, kept so an unfinished job can resume.
    `folder` makes the job save into a folder an earlier job already made (used to retry the
    videos that failed).
    """
    if not (save_to_folder or make_zip or browser_download):
        raise ValueError("Choose at least one way to receive the files: a folder or a ZIP.")
    if not items:
        raise ValueError("Select at least one video.")
    if len(items) > config.MAX_PLAYLIST_ITEMS:
        raise ValueError(f"A job can hold at most {config.MAX_PLAYLIST_ITEMS} videos.")
    _check_capacity()

    cleaned = [
        Item(
            index=number,
            title=str(entry.get("title") or "Untitled")[:200],
            url=validators.validate_url(entry.get("url")),
            number=_number(entry.get("number"), number),
        )
        for number, entry in enumerate(items, start=1)
    ]
    job = Job(
        id=uuid.uuid4().hex[:12],
        title=validators.safe_filename(title, default="Playlist"),
        fmt=fmt,
        quality=quality,
        items=cleaned,
        save_to_folder=save_to_folder,
        make_zip=make_zip,
        staging=Path(tempfile.mkdtemp(prefix="mediaforge-job-")),
        mute=mute,
        browser_download=browser_download,
        features=features or features_mod.Features(),
        parallel=settings.load()["parallel"] if len(cleaned) > 1 else 1,
        folder=folder if folder is not None and folder.is_dir() and save_to_folder else None,
    )
    _register(job)
    if save_to_folder and not browser_download:
        pending.save(
            job.id,
            {
                "title": title,
                "format": fmt,
                "quality": quality,
                "mute": mute,
                "options": options or {},
                "folder": str(job.folder) if job.folder else None,
                "items": [
                    {"title": item.title, "url": item.url, "number": item.number or item.index}
                    for item in cleaned
                ],
            },
        )
    _executor.submit(_run, job)
    return job


def _online() -> bool:
    """True when the internet answers. Tries two public servers, quickly."""
    for address in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            socket.create_connection(address, timeout=3).close()
            return True
        except OSError:
            continue
    return False


def _wait_for_internet(job: Job, item: Item) -> None:
    """Pause until the internet is back, so the download can carry on where it stopped."""
    item.phase, item.percent, item.speed, item.eta = "offline", None, None, None
    deadline = time.monotonic() + OFFLINE_MAX_WAIT
    while True:
        _sleep(job, OFFLINE_POLL)
        if _online():
            return
        if time.monotonic() > deadline:
            raise NetworkError("The internet connection did not come back.")


def _number(value, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if 1 <= number <= 9999 else fallback


def _check_capacity() -> None:
    """Refuse new work while too many jobs are waiting or running."""
    with _lock:
        busy = sum(1 for job in _jobs.values() if job.status in ("queued", "running", "uploading"))
    if busy >= config.MAX_ACTIVE_JOBS:
        raise ConversionError(
            f"MediaForge already has {busy} jobs in progress. Wait for one to finish or cancel it.",
            "MF-LIM-04",
        )


def _register(job: Job) -> None:
    with _lock:
        _jobs[job.id] = job
        while len(_jobs) > MAX_KEPT_JOBS:
            _, oldest = _jobs.popitem(last=False)
            if oldest.status in ("done", "cancelled"):
                _forget(oldest)
            else:  # never drop a job that is still working
                _jobs[oldest.id] = oldest
                _jobs.move_to_end(oldest.id, last=False)
                break


def prepare_upload_job(
    filename: str,
    fmt: str,
    quality: str,
    mute: bool,
    features: features_mod.Features | None = None,
    tweaks: tweaks_mod.Tweaks | None = None,
) -> tuple[Job, Path]:
    """Create a job for a file that is about to be uploaded. Returns it and where to save it.

    Call `submit_upload` once the file is saved, or `discard` if the upload fails.
    """
    _check_capacity()
    name = validators.safe_filename(filename, default="upload")
    staging = Path(tempfile.mkdtemp(prefix="mediaforge-job-"))
    destination = staging / "upload" / name
    destination.parent.mkdir()
    item = Item(index=1, title=name, url="", source=destination)
    job = Job(
        id=uuid.uuid4().hex[:12],
        title=Path(name).stem,
        fmt=fmt,
        quality=quality,
        items=[item],
        save_to_folder=False,
        make_zip=False,
        staging=staging,
        mute=mute,
        browser_download=True,
        status="uploading",
        features=features or features_mod.Features(),
        tweaks=tweaks or tweaks_mod.Tweaks(),
    )
    _register(job)
    return job, destination


def submit_upload(job: Job) -> None:
    job.status = "queued"
    _executor.submit(_run, job)


def discard(job: Job) -> None:
    with _lock:
        _jobs.pop(job.id, None)
    _forget(job)


def any_active() -> bool:
    with _lock:
        return any(job.status in ("queued", "running", "uploading") for job in _jobs.values())


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def cancel_job(job: Job) -> None:
    job.cancel_requested = True


def _reporter(job: Job, item: Item):
    """A progress callback for one item. It also carries the Cancel request into the work."""

    def report(update: dict) -> None:
        if job.cancel_requested:
            raise downloader.Cancelled()
        item.phase = update.get("phase", item.phase)
        item.percent = update.get("percent")
        item.speed = update.get("speed")
        item.eta = update.get("eta")

    return report


def snapshot(job: Job) -> dict:
    counts = {"done": 0, "failed": 0}
    for item in job.items:
        if item.status in counts:
            counts[item.status] += 1
    return {
        "id": job.id,
        "title": job.title,
        "format": job.fmt,
        "status": job.status,
        "total": len(job.items),
        "done": counts["done"],
        "failed": counts["failed"],
        "blocked": job.blocked,
        "blocked_reason": job.blocked_reason,
        "parallel": job.parallel,
        "folder": str(job.folder) if job.folder else None,
        "zip_ready": bool(job.zip_path and job.zip_path.exists()),
        "items": [
            {
                "index": item.index,
                "number": item.number or item.index,
                "url": item.url or None,
                "title": item.title,
                "status": item.status,
                "error": item.error,
                "error_info": item.error_info,
                "filename": item.filename,
                "phase": item.phase,
                "percent": item.percent,
                "speed": item.speed,
                "eta": item.eta,
                "note": item.note,
                "downloadable": bool(item.path and item.path.exists()),
            }
            for item in job.items
        ],
    }


def _destination_dir(job: Job) -> Path:
    with job.lock:
        if job.save_to_folder:
            if job.folder is None:
                job.folder = _unique_folder(config.DOWNLOAD_DIR, job.title)
                pending.set_folder(job.id, str(job.folder))
            job.folder.mkdir(parents=True, exist_ok=True)
            return job.folder
        target = job.staging / "files"
        target.mkdir(exist_ok=True)
        return target


def _sleep(job: Job, seconds: float, item: Item | None = None) -> None:
    """Wait, but notice a Cancel request within a second. Shows the countdown on `item`."""
    end = time.monotonic() + seconds
    while True:
        left = end - time.monotonic()
        if job.cancel_requested:
            raise downloader.Cancelled()
        if item is not None:
            item.eta = max(0.0, left)
        if left <= 0:
            return
        time.sleep(min(1.0, left))


def _pace(job: Job, item: Item) -> None:
    """Space out the starts of a playlist's videos a little."""
    if len(job.items) < 3 or item.source is not None:
        return
    with job.lock:
        now = time.monotonic()
        start = max(now, job.next_start)
        job.next_start = start + random.uniform(PACE_MIN, PACE_MAX)  # noqa: S311
    if start > now:
        item.phase, item.percent = "queued", None
        _sleep(job, start - now)


def _produce(job: Job, item: Item, workdir: Path, report, notes: list[str]) -> Path:
    if item.source is not None:
        return transcoder.convert_file(
            item.source,
            job.fmt,
            job.quality,
            workdir,
            job.mute,
            report,
            normalize=job.features.normalize,
            tweaks=job.tweaks,
            audio_file=job.audio_file,
            subtitle_file=job.subtitle_file,
            cover_file=job.cover_file,
        )
    return downloader.download_and_convert(
        item.url,
        job.fmt,
        job.quality,
        workdir,
        {"album": job.title, "track": item.number or item.index},
        notes,
        job.mute,
        report,
        job.features,
    )


def _wait_out_block(job: Job, item: Item, seconds: float, phase: str = "waiting") -> None:
    item.phase, item.percent, item.speed = phase, None, None
    _sleep(job, seconds, item)


def _deliver(job: Job, item: Item, output: Path) -> None:
    if job.browser_download:
        kept = job.staging / "files"
        kept.mkdir(exist_ok=True)
        final = kept / output.name
        shutil.move(str(output), final)
        item.path = final
        item.filename = final.name
        return
    number = item.number or item.index
    name = validators.safe_filename(f"{number:02d} - {output.stem}", max_length=120)
    folder = _destination_dir(job)
    with job.lock:
        final = folder / f"{name}{output.suffix}"
        counter = 2
        while final.exists():
            final = final.with_name(f"{name} ({counter}){output.suffix}")
            counter += 1
        shutil.move(str(output), final)
        job.produced.append(final)
    item.filename = final.name


def _run_item(job: Job, item: Item) -> None:
    workdir = job.staging / f"item-{item.index}"
    workdir.mkdir()
    report = _reporter(job, item)
    notes: list[str] = []
    try:
        _pace(job, item)
        item.status = "running"
        bot_tries = network_tries = 0
        while True:
            try:
                output = _produce(job, item, workdir, report, notes)
                break
            except BotCheckError:
                if bot_tries >= len(BOT_CHECK_WAITS):
                    raise
                wait, phase = BOT_CHECK_WAITS[bot_tries], "waiting"
                bot_tries += 1
            except NetworkError:
                if not _online():
                    # The whole connection is down: wait for it, then continue the same
                    # download (yt-dlp resumes the partly downloaded file).
                    _wait_for_internet(job, item)
                    continue
                if network_tries >= len(NETWORK_WAITS):
                    raise
                wait, phase = NETWORK_WAITS[network_tries], "waiting"
                network_tries += 1
            downloader._discard_partial_files(workdir)
            _wait_out_block(job, item, wait, phase)
        item.note = " ".join(notes) or None
        _deliver(job, item, output)
        item.status = "done"
        with job.lock:
            job.block_streak = job.network_streak = 0
        if item.url:
            history.add(
                job.features.title or item.title, item.url, job.fmt, job.quality, item.filename
            )
            pending.mark_done(job.id, item.number or item.index)
    except downloader.Cancelled:
        item.status = "skipped"
    except BotCheckError as exc:
        item.status, item.error = "failed", str(exc)
        item.error_info = errors.describe_exception(exc)
        with job.lock:
            job.block_streak += 1
            if job.block_streak >= BOT_CHECK_STOP_AFTER:
                job.blocked, job.blocked_reason = True, job.blocked_reason or "sign-in"
    except NetworkError as exc:
        item.status, item.error = "failed", str(exc)
        item.error_info = errors.describe_exception(exc)
        with job.lock:
            job.network_streak += 1
            if job.network_streak >= NETWORK_STOP_AFTER:
                job.blocked, job.blocked_reason = True, job.blocked_reason or "network"
    except ConversionError as exc:
        item.status, item.error = "failed", str(exc)
        item.error_info = errors.describe_exception(exc)
    except Exception:  # keep going with the rest of the playlist
        item.status, item.error = "failed", "Unexpected error while converting this video."
        item.error_info = errors.describe("MF-GEN-00")
    finally:
        item.phase = item.percent = item.speed = item.eta = None
        shutil.rmtree(workdir, ignore_errors=True)


def _make_zip(job: Job) -> None:
    archive = job.staging / f"{job.title}.zip"
    # Media files are already compressed, so storing them is much faster.
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        for path in job.produced:
            bundle.write(path, arcname=path.name)
    job.zip_path = archive


def _worker(job: Job, waiting: deque, first: bool) -> None:
    """Take videos from the queue until it is empty, the job is cancelled, or the site blocks us."""
    while True:
        with job.lock:
            if job.cancel_requested or job.blocked or not waiting:
                return
            # After a sign-in check only the first worker carries on, one video at a time.
            if (job.block_streak or job.network_streak) and not first:
                return
            item = waiting.popleft()
        _run_item(job, item)


def _run(job: Job) -> None:
    job.status = "running"
    waiting = deque(job.items)
    workers = [
        threading.Thread(
            target=_worker, args=(job, waiting, number == 0), name=f"mediaforge-item-{number}"
        )
        for number in range(max(1, min(job.parallel, len(job.items))))
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    for item in job.items:
        if item.status == "queued":
            item.status = "skipped"
            if job.blocked:
                reason = (
                    "the connection to the site was lost"
                    if job.blocked_reason == "network"
                    else "the site kept asking for a sign-in check"
                )
                item.error = f"Not tried: {reason}. Choose Retry to continue later."

    if job.make_zip and job.produced:
        try:
            _make_zip(job)
        except OSError:
            job.zip_path = None
    if not job.save_to_folder and not job.browser_download:
        # The files only existed to build the ZIP.
        shutil.rmtree(job.staging / "files", ignore_errors=True)
    job.status = "cancelled" if job.cancel_requested else "done"


def open_folder(job: Job) -> None:
    """Show the job's output folder in the system file manager."""
    if job.folder is None or not job.folder.is_dir():
        raise ValueError("This job has no folder yet.")
    if sys.platform.startswith("win"):
        os.startfile(job.folder)  # noqa: S606  (Windows only)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(job.folder)])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", str(job.folder)])  # noqa: S603, S607


@atexit.register
def _cleanup_all() -> None:
    for job in list(_jobs.values()):
        _forget(job)
