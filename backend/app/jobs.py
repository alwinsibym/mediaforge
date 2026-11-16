"""Background playlist jobs: convert many videos, one after another."""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import config, downloader, validators
from .downloader import ConversionError

MAX_KEPT_JOBS = 10

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
    status: str = "queued"  # queued, running, done, cancelled
    folder: Path | None = None
    zip_path: Path | None = None
    produced: list[Path] = field(default_factory=list)
    cancel_requested: bool = False


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
) -> Job:
    """Validate a request, register the job and queue it."""
    if not (save_to_folder or make_zip):
        raise ValueError("Choose at least one way to receive the files: a folder or a ZIP.")
    if not items:
        raise ValueError("Select at least one video.")
    if len(items) > config.MAX_PLAYLIST_ITEMS:
        raise ValueError(f"A job can hold at most {config.MAX_PLAYLIST_ITEMS} videos.")

    cleaned = [
        Item(
            index=number,
            title=str(entry.get("title") or "Untitled")[:200],
            url=validators.validate_url(entry.get("url")),
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
    )
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
    _executor.submit(_run, job)
    return job


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def cancel_job(job: Job) -> None:
    job.cancel_requested = True


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
        "folder": str(job.folder) if job.folder else None,
        "zip_ready": bool(job.zip_path and job.zip_path.exists()),
        "items": [
            {
                "index": item.index,
                "title": item.title,
                "status": item.status,
                "error": item.error,
                "filename": item.filename,
            }
            for item in job.items
        ],
    }


def _destination_dir(job: Job) -> Path:
    if job.save_to_folder:
        if job.folder is None:
            job.folder = _unique_folder(config.DOWNLOAD_DIR, job.title)
        job.folder.mkdir(parents=True, exist_ok=True)
        return job.folder
    target = job.staging / "files"
    target.mkdir(exist_ok=True)
    return target


def _run_item(job: Job, item: Item) -> None:
    workdir = job.staging / f"item-{item.index}"
    workdir.mkdir()
    try:
        output = downloader.download_and_convert(
            item.url,
            job.fmt,
            job.quality,
            workdir,
            {"album": job.title, "track": item.index},
            mute=job.mute,
        )
        name = validators.safe_filename(f"{item.index:02d} - {output.stem}", max_length=120)
        final = _destination_dir(job) / f"{name}{output.suffix}"
        counter = 2
        while final.exists():
            final = final.with_name(f"{name} ({counter}){output.suffix}")
            counter += 1
        shutil.move(str(output), final)
        job.produced.append(final)
        item.filename = final.name
        item.status = "done"
    except ConversionError as exc:
        item.status, item.error = "failed", str(exc)
    except Exception:  # keep going with the rest of the playlist
        item.status, item.error = "failed", "Unexpected error while converting this video."
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _make_zip(job: Job) -> None:
    archive = job.staging / f"{job.title}.zip"
    # Media files are already compressed, so storing them is much faster.
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        for path in job.produced:
            bundle.write(path, arcname=path.name)
    job.zip_path = archive


def _run(job: Job) -> None:
    job.status = "running"
    for item in job.items:
        if job.cancel_requested:
            item.status = "skipped"
            continue
        item.status = "running"
        _run_item(job, item)

    if job.make_zip and job.produced:
        try:
            _make_zip(job)
        except OSError:
            job.zip_path = None
    if not job.save_to_folder:
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
