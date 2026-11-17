"""MediaForge API: convert media from a URL or an uploaded file."""

import importlib.metadata
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from . import (
    __version__,
    config,
    downloader,
    features,
    ffmpeg_locator,
    formats,
    history,
    jobs,
    settings,
    transcoder,
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


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _cleanup(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _file_response(path: Path, workdir: str) -> FileResponse:
    """Send a file, then delete its temporary folder."""
    return FileResponse(
        path,
        filename=path.name,
        background=BackgroundTask(_cleanup, workdir),
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "ffmpeg": downloader.ffmpeg_ready(),
        "ffmpeg_path": ffmpeg_locator.find_tool("ffmpeg"),
        "js_runtimes": sorted(downloader.js_runtimes()),
        "yt_dlp": _ytdlp_version(),
        "aria2c": downloader.aria2c_available(),
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
            if written > limit:
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
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return jobs.snapshot(job)


@app.post("/api/jobs/upload")
async def create_upload_job(
    file: UploadFile = File(...),
    format: str = Form("mp3"),
    quality: str | None = Form(None),
    mute: bool = Form(False),
    normalize: bool = Form(False),
) -> dict:
    """Upload a file and convert it in the background, with live progress."""
    try:
        fmt, quality = formats.normalize(format, quality)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    job, destination = jobs.prepare_upload_job(
        file.filename or "upload", fmt, quality, mute, features.Features(normalize=normalize)
    )
    try:
        await _save_upload(file, destination)
    except ConversionError as exc:
        jobs.discard(job)
        raise _bad_request(exc) from exc
    except Exception:
        jobs.discard(job)
        raise HTTPException(status_code=500, detail="Unexpected server error.") from None
    jobs.submit_upload(job)
    return jobs.snapshot(job)


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
            command, capture_output=True, text=True, timeout=300
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
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
