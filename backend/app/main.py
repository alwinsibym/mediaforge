"""MediaForge API: convert media from a URL or an uploaded file."""

import hmac
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from . import (
    __version__,
    config,
    downloader,
    errors,
    features,
    ffmpeg_locator,
    formats,
    history,
    jobs,
    pending,
    runtime,
    settings,
    transcoder,
    tweaks,
    validators,
)
from .downloader import ConversionError

app = FastAPI(title="MediaForge", version=__version__)

CHUNK_SIZE = 1024 * 1024  # 1 MB


class UrlRequest(BaseModel):
    url: str


class ConvertRequest(BaseModel):
    url: str
    format: str = "mp3"
    quality: str | None = None
    mute: bool = False  # video only: leave the sound out


class ThumbnailRequest(BaseModel):
    url: str
    id: str
    format: str = "jpg"
    square: bool = False


class PlaylistItem(BaseModel):
    title: str = ""
    url: str
    number: int | None = None  # keeps the original position when retrying failed videos


class JobRequest(BaseModel):
    title: str = "Playlist"
    items: list[PlaylistItem]
    format: str = "mp3"
    quality: str | None = None
    mute: bool = False
    save_to_folder: bool = True
    make_zip: bool = False
    # Keep the finished file for this browser to download (used for single links).
    deliver_to_browser: bool = False
    # Extras: normalize, sponsorblock, subtitles, subtitle_langs, trim_start, trim_end, ...
    options: dict = {}
    # Save into the folder of an earlier job (used to retry the videos that failed).
    continue_job: str | None = None


class ApiError(HTTPException):
    """An HTTP error that also carries the full explanation for the page."""

    def __init__(self, status_code: int, detail: str, info: dict):
        super().__init__(status_code=status_code, detail=detail)
        self.info = info


@app.exception_handler(ApiError)
async def _api_error(_request: Request, exc: ApiError):
    return JSONResponse({"detail": exc.detail, "error": exc.info}, status_code=exc.status_code)


TOKEN_COOKIE = "mf_token"
_OPEN_PATHS = {"/api/health", "/api/login"}


def _is_local(request: Request) -> bool:
    return request.client is not None and request.client.host in _LOCAL_CLIENTS


def _authorised(request: Request) -> bool:
    """True when no token is set, the client is this computer, or it sent the right token."""
    if not config.ACCESS_TOKEN or _is_local(request):
        return True
    given = request.cookies.get(TOKEN_COOKIE, "")
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        given = header[7:].strip()
    return hmac.compare_digest(given.encode(), config.ACCESS_TOKEN.encode())


@app.middleware("http")
async def _require_token(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in _OPEN_PATHS and not _authorised(request):
        return JSONResponse(
            {
                "detail": "This MediaForge asks for an access token.",
                "error": errors.describe("MF-AUTH-01"),
                "auth_required": True,
            },
            status_code=401,
        )
    return await call_next(request)


@app.post("/api/login")
def login(body: dict, request: Request) -> JSONResponse:
    """Check the access token and remember it in a cookie for this browser."""
    given = str(body.get("token") or "")
    if config.ACCESS_TOKEN and not hmac.compare_digest(
        given.encode(), config.ACCESS_TOKEN.encode()
    ):
        raise HTTPException(status_code=401, detail="That token is not correct.")
    response = JSONResponse({"ok": True})
    if config.ACCESS_TOKEN:
        response.set_cookie(
            TOKEN_COOKIE,
            given,
            httponly=True,
            samesite="strict",
            max_age=30 * 24 * 3600,
        )
    return response


def _bad_request(exc: Exception) -> HTTPException:
    return ApiError(400, str(exc), errors.describe_exception(exc))


def _cleanup(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _file_response(path: Path, workdir: str) -> FileResponse:
    """Send a file, then delete its temporary folder."""
    return FileResponse(
        path,
        filename=path.name,
        background=BackgroundTask(_cleanup, workdir),
    )


@app.post("/api/quit")
def quit_app(request: Request) -> dict:
    """Stop MediaForge. Only the computer running it may do this."""
    _local_only(request)
    if runtime.SERVER is None:
        raise HTTPException(status_code=409, detail="MediaForge was not started with run.py.")
    runtime.SERVER.should_exit = True
    return {"ok": True}


@app.get("/api/health")
def health(request: Request) -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "ffmpeg": downloader.ffmpeg_ready(),
        "ffmpeg_path": ffmpeg_locator.find_tool("ffmpeg"),
        "js_runtimes": sorted(downloader.js_runtimes()),
        "yt_dlp": _ytdlp_version(),
        "aria2c": downloader.aria2c_available(),
        "auth_required": bool(config.ACCESS_TOKEN),
        "authorised": _authorised(request),
        "can_quit": runtime.SERVER is not None and _is_local(request),
    }


@app.get("/api/formats")
def list_formats() -> dict:
    return {
        **formats.describe(),
        "limits": {
            "max_duration_seconds": config.MAX_DURATION_SECONDS,
            "max_upload_mb": config.MAX_UPLOAD_MB,
            "max_playlist_items": config.MAX_PLAYLIST_ITEMS,
        },
        "download_dir": str(config.DOWNLOAD_DIR),
        "tweaks": tweaks.describe(),
    }


@app.post("/api/info")
async def video_info(body: UrlRequest) -> dict:
    """Look up the title and duration of a URL before converting it."""
    try:
        url = validators.validate_url(body.url)
        return await run_in_threadpool(downloader.fetch_info, url)
    except (ValueError, ConversionError) as exc:
        raise _bad_request(exc) from exc


@app.post("/api/thumbnail")
async def get_thumbnail(body: ThumbnailRequest) -> FileResponse:
    """Download one of a video's thumbnails as JPG, PNG or WebP."""
    workdir = tempfile.mkdtemp(prefix="mediaforge-")
    try:
        url = validators.validate_url(body.url)
        output = await run_in_threadpool(
            downloader.download_thumbnail, url, body.id, body.format, body.square, Path(workdir)
        )
    except (ValueError, ConversionError) as exc:
        _cleanup(workdir)
        raise _bad_request(exc) from exc
    except Exception:
        _cleanup(workdir)
        raise HTTPException(status_code=500, detail="Unexpected server error.") from None
    return _file_response(output, workdir)


@app.post("/api/convert")
async def convert_url(body: ConvertRequest) -> FileResponse:
    """Download a URL and return it converted to the requested format."""
    workdir = tempfile.mkdtemp(prefix="mediaforge-")
    try:
        url = validators.validate_url(body.url)
        fmt, quality = formats.normalize(body.format, body.quality)
        notes: list[str] = []
        output = await run_in_threadpool(
            downloader.download_and_convert,
            url,
            fmt,
            quality,
            Path(workdir),
            None,
            notes,
            body.mute,
        )
    except (ValueError, ConversionError) as exc:
        _cleanup(workdir)
        raise _bad_request(exc) from exc
    except Exception:
        _cleanup(workdir)
        raise HTTPException(status_code=500, detail="Unexpected server error.") from None
    response = _file_response(output, workdir)
    if notes:
        response.headers["X-MediaForge-Note"] = quote(" ".join(notes))
    return response


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    """Stream an upload to disk, enforcing the size limit."""
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    with destination.open("wb") as out:
        while chunk := await upload.read(CHUNK_SIZE):
            written += len(chunk)
            if limit and written > limit:
                raise ConversionError(f"File is larger than the {config.MAX_UPLOAD_MB} MB limit.")
            out.write(chunk)
    if written == 0:
        raise ConversionError("The uploaded file is empty.")


@app.post("/api/convert-file")
async def convert_upload(
    file: UploadFile = File(...),
    format: str = Form("mp3"),
    quality: str | None = Form(None),
    mute: bool = Form(False),
) -> FileResponse:
    """Convert an uploaded audio/video file to the requested format."""
    workdir = tempfile.mkdtemp(prefix="mediaforge-")
    try:
        fmt, quality = formats.normalize(format, quality)
        name = validators.safe_filename(file.filename, default="upload")
        source = Path(workdir) / name
        await _save_upload(file, source)
        output = await run_in_threadpool(
            transcoder.convert_file, source, fmt, quality, Path(workdir), mute
        )
    except (ValueError, ConversionError) as exc:
        _cleanup(workdir)
        raise _bad_request(exc) from exc
    except Exception:
        _cleanup(workdir)
        raise HTTPException(status_code=500, detail="Unexpected server error.") from None
    return _file_response(output, workdir)


@app.post("/api/playlist/info")
async def playlist_info(body: UrlRequest) -> dict:
    """List the videos in a playlist link."""
    try:
        url = validators.validate_url(body.url)
        return await run_in_threadpool(downloader.fetch_playlist, url)
    except (ValueError, ConversionError) as exc:
        raise _bad_request(exc) from exc


@app.post("/api/jobs")
def create_job(body: JobRequest) -> dict:
    """Start converting the chosen playlist videos in the background."""
    try:
        fmt, quality = formats.normalize(body.format, body.quality)
        extras = features.parse(body.options, fmt, single=len(body.items) == 1)
        earlier = jobs.get_job(body.continue_job) if body.continue_job else None
        job = jobs.start_job(
            body.title,
            [item.model_dump() for item in body.items],
            fmt,
            quality,
            body.save_to_folder,
            body.make_zip,
            body.mute,
            body.deliver_to_browser,
            extras,
            earlier.folder if earlier else None,
            body.options,
        )
    except (ValueError, ConversionError) as exc:
        raise _bad_request(exc) from exc
    if body.continue_job:
        pending.remove(body.continue_job)  # its leftovers now belong to the new job
    return jobs.snapshot(job)


class _Frontend(StaticFiles):
    """Serve the page, but make the browser re-check it, so an update is never hidden by a cache."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


SUBTITLE_LIMIT = 5 * 1024 * 1024


async def _save_extra(upload: UploadFile | None, folder: Path, stem: str, allowed: set[str] | None):
    """Save an optional extra file (subtitles or replacement audio) and return its path."""
    if upload is None or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if allowed is not None and suffix not in allowed:
        raise ConversionError(
            "Subtitles must be a .srt, .vtt, .ass or .ssa file."
            if allowed is tweaks.SUBTITLE_EXTENSIONS
            else "The cover picture must be a JPG, PNG or WebP image."
            if allowed is tweaks.COVER_EXTENSIONS
            else tweaks.AUDIO_FILE_LIMIT_NOTE
        )
    if allowed is None and not re.fullmatch(r"\.[a-z0-9]{1,5}", suffix):
        suffix = ".audio"
    folder.mkdir(exist_ok=True)
    destination = folder / f"{stem}{suffix}"
    await _save_upload(upload, destination)
    if allowed in (tweaks.SUBTITLE_EXTENSIONS, tweaks.COVER_EXTENSIONS) and (
        destination.stat().st_size > SUBTITLE_LIMIT * 2
    ):
        raise ConversionError("That file is too large to use here.")
    return destination


@app.post("/api/jobs/upload")
async def create_upload_job(
    file: UploadFile = File(...),
    format: str = Form("mp3"),
    quality: str | None = Form(None),
    mute: bool = Form(False),
    normalize: bool = Form(False),
    title: str = Form(""),
    options: str = Form(""),
    audio_file: UploadFile | None = File(None),
    subtitle_file: UploadFile | None = File(None),
    cover_file: UploadFile | None = File(None),
) -> dict:
    """Upload a file and convert it in the background, with live progress."""
    try:
        fmt, quality = formats.normalize(format, quality)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    original = file.filename or "upload"
    try:
        wanted = features.parse({"title": title}, fmt, single=True).title
        raw = json.loads(options) if options.strip() else {}
        if not isinstance(raw, dict):
            raise ValueError("The tweaks were not understood.")
        chosen = tweaks.parse(
            {**raw, "mute": mute},
            fmt,
            audio_file=bool(audio_file and audio_file.filename),
            subtitle_file=bool(subtitle_file and subtitle_file.filename),
            cover_file=bool(cover_file and cover_file.filename),
        )
    except json.JSONDecodeError:
        raise _bad_request("The tweaks were not understood.") from None
    except ValueError as exc:
        raise _bad_request(exc) from exc
    name = f"{wanted}{Path(original).suffix}" if wanted else original
    try:
        job, destination = jobs.prepare_upload_job(
            name, fmt, quality, mute, features.Features(normalize=normalize), chosen
        )
    except ConversionError as exc:
        raise _bad_request(exc) from exc
    try:
        await _save_upload(file, destination)
        extra = job.staging / "extra"
        job.audio_file = await _save_extra(audio_file, extra, "audio", None)
        job.subtitle_file = await _save_extra(
            subtitle_file, extra, "subtitles", tweaks.SUBTITLE_EXTENSIONS
        )
        job.cover_file = await _save_extra(cover_file, extra, "cover", tweaks.COVER_EXTENSIONS)
    except ConversionError as exc:
        jobs.discard(job)
        raise _bad_request(exc) from exc
    except Exception:
        jobs.discard(job)
        raise HTTPException(status_code=500, detail="Unexpected server error.") from None
    jobs.submit_upload(job)
    return jobs.snapshot(job)


@app.post("/api/probe")
async def probe_file(file: UploadFile = File(...)) -> dict:
    """Read the codec, bitrate, streams and length of a file, without converting it."""
    workdir = Path(tempfile.mkdtemp(prefix="mediaforge-probe-"))
    try:
        destination = workdir / validators.safe_filename(file.filename, default="upload")
        await _save_upload(file, destination)
        info = await run_in_threadpool(transcoder.probe, destination)
        info["size_bytes"] = destination.stat().st_size
        info["name"] = destination.name
        return info
    except ConversionError as exc:
        raise _bad_request(exc) from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _find_job(job_id: str) -> jobs.Job:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="That job was not found.")
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return jobs.snapshot(_find_job(job_id))


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = _find_job(job_id)
    jobs.cancel_job(job)
    return jobs.snapshot(job)


@app.get("/api/jobs/{job_id}/items/{index}/file")
def job_item_file(job_id: str, index: int) -> FileResponse:
    """Send a finished file to the browser, then delete it."""
    job = _find_job(job_id)
    item = next((item for item in job.items if item.index == index), None)
    if item is None or not item.path or not item.path.exists():
        raise HTTPException(status_code=404, detail="That file is not available any more.")
    path = item.path

    def forget() -> None:
        path.unlink(missing_ok=True)
        item.path = None

    return FileResponse(path, filename=path.name, background=BackgroundTask(forget))


@app.get("/api/jobs/{job_id}/zip")
def job_zip(job_id: str) -> FileResponse:
    job = _find_job(job_id)
    if not job.zip_path or not job.zip_path.exists():
        raise HTTPException(status_code=404, detail="The ZIP file is not ready.")
    return FileResponse(job.zip_path, filename=job.zip_path.name)


_LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@app.post("/api/jobs/{job_id}/open-folder")
def job_open_folder(job_id: str, request: Request) -> dict:
    # The folder opens on the computer running MediaForge, so only that computer may ask.
    if request.client is None or request.client.host not in _LOCAL_CLIENTS:
        raise HTTPException(
            status_code=403,
            detail="The folder can only be opened from the computer running MediaForge.",
        )
    job = _find_job(job_id)
    try:
        jobs.open_folder(job)
    except (ValueError, OSError) as exc:
        raise _bad_request(exc) from exc
    return {"opened": str(job.folder)}


def _local_only(request: Request) -> None:
    """Settings, updates and history belong to the person at this computer."""
    if config.TRUST_ALL_CLIENTS:
        return
    if request.client is None or request.client.host not in _LOCAL_CLIENTS:
        raise HTTPException(
            status_code=403,
            detail="This can only be changed from the computer running MediaForge.",
        )


def _settings_payload() -> dict:
    return {
        **settings.load(),
        "cookie_browsers": list(settings.COOKIE_BROWSERS),
        "max_parallel": settings.MAX_PARALLEL,
        "aria2c_installed": downloader.aria2c_available(),
        "impersonation_installed": downloader.impersonation_available(),
    }


@app.get("/api/settings")
def get_settings(request: Request) -> dict:
    _local_only(request)
    return _settings_payload()


@app.post("/api/settings")
def save_settings(body: dict, request: Request) -> dict:
    _local_only(request)
    try:
        settings.save(body)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except OSError:
        raise HTTPException(status_code=500, detail="The settings could not be saved.") from None
    return _settings_payload()


@app.get("/api/history")
def get_history(request: Request) -> dict:
    _local_only(request)
    return {"items": history.recent()}


@app.delete("/api/history")
def clear_history(request: Request) -> dict:
    _local_only(request)
    history.clear()
    return {"items": []}


@app.get("/api/pending")
def get_pending(request: Request) -> dict:
    _local_only(request)
    return {
        "items": [
            {
                "id": entry["id"],
                "title": entry["title"],
                "format": entry["format"],
                "left": len(entry["items"]),
                "created": entry.get("created"),
            }
            for entry in pending.all_entries()
        ]
    }


@app.post("/api/pending/{pending_id}/resume")
def resume_pending(pending_id: str, request: Request) -> dict:
    """Start the videos that were left unfinished, into the same folder with the same numbers."""
    _local_only(request)
    entry = pending.get(pending_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="That download list is no longer there.")
    try:
        fmt, quality = formats.normalize(entry["format"], entry["quality"])
        extras = features.parse(entry.get("options"), fmt, single=len(entry["items"]) == 1)
        folder = Path(entry["folder"]) if entry.get("folder") else None
        job = jobs.start_job(
            entry["title"],
            entry["items"],
            fmt,
            quality,
            True,
            False,
            bool(entry.get("mute")),
            False,
            extras,
            folder,
            entry.get("options"),
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    pending.remove(pending_id)
    return {
        **jobs.snapshot(job),
        "request": {
            "title": entry["title"],
            "format": fmt,
            "quality": quality,
            "mute": bool(entry.get("mute")),
            "save_to_folder": True,
            "make_zip": False,
            "options": entry.get("options") or {},
        },
    }


@app.delete("/api/pending/{pending_id}")
def discard_pending(pending_id: str, request: Request) -> dict:
    _local_only(request)
    pending.remove(pending_id)
    return get_pending(request)


def _ytdlp_version() -> str:
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _upgrade_ytdlp() -> dict:
    before = _ytdlp_version()
    command = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]"]
    try:
        result = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ConversionError(
            "The update could not be run. Try the command in a terminal."
        ) from None
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        raise ConversionError(f"The update failed: {(lines or ['unknown error'])[-1][:200]}")
    after = _ytdlp_version()
    return {"before": before, "after": after, "changed": before != after}


@app.post("/api/update-ytdlp")
async def update_ytdlp(request: Request) -> dict:
    """Upgrade yt-dlp, the part that breaks when sites change. A restart applies it."""
    _local_only(request)
    if jobs.any_active():
        raise HTTPException(
            status_code=409, detail="Wait for the current downloads to finish, then update."
        )
    try:
        return await run_in_threadpool(_upgrade_ytdlp)
    except ConversionError as exc:
        raise _bad_request(exc) from exc


# Serve the frontend last so /api/* routes take priority.
if config.FRONTEND_DIR.is_dir():
    app.mount("/", _Frontend(directory=config.FRONTEND_DIR, html=True), name="frontend")
