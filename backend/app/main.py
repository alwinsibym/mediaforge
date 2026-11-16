"""MediaForge API: convert media from a URL or an uploaded file."""

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from . import (
    __version__,
    config,
    downloader,
    ffmpeg_locator,
    formats,
    jobs,
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


class PlaylistItem(BaseModel):
    title: str = ""
    url: str


class JobRequest(BaseModel):
    title: str = "Playlist"
    items: list[PlaylistItem]
    format: str = "mp3"
    quality: str | None = None
    save_to_folder: bool = True
    make_zip: bool = False


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


@app.post("/api/convert")
async def convert_url(body: ConvertRequest) -> FileResponse:
    """Download a URL and return it converted to the requested format."""
    workdir = tempfile.mkdtemp(prefix="mediaforge-")
    try:
        url = validators.validate_url(body.url)
        fmt, quality = formats.normalize(body.format, body.quality)
        output = await run_in_threadpool(
            downloader.download_and_convert, url, fmt, quality, Path(workdir)
        )
    except (ValueError, ConversionError) as exc:
        _cleanup(workdir)
        raise _bad_request(exc) from exc
    except Exception:
        _cleanup(workdir)
        raise HTTPException(status_code=500, detail="Unexpected server error.") from None
    return _file_response(output, workdir)


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
) -> FileResponse:
    """Convert an uploaded audio/video file to the requested format."""
    workdir = tempfile.mkdtemp(prefix="mediaforge-")
    try:
        fmt, quality = formats.normalize(format, quality)
        name = validators.safe_filename(file.filename, default="upload")
        source = Path(workdir) / name
        await _save_upload(file, source)
        output = await run_in_threadpool(
            transcoder.convert_file, source, fmt, quality, Path(workdir)
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
        job = jobs.start_job(
            body.title,
            [item.model_dump() for item in body.items],
            fmt,
            quality,
            body.save_to_folder,
            body.make_zip,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
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


@app.get("/api/jobs/{job_id}/zip")
def job_zip(job_id: str) -> FileResponse:
    job = _find_job(job_id)
    if not job.zip_path or not job.zip_path.exists():
        raise HTTPException(status_code=404, detail="The ZIP file is not ready.")
    return FileResponse(job.zip_path, filename=job.zip_path.name)


@app.post("/api/jobs/{job_id}/open-folder")
def job_open_folder(job_id: str) -> dict:
    job = _find_job(job_id)
    try:
        jobs.open_folder(job)
    except (ValueError, OSError) as exc:
        raise _bad_request(exc) from exc
    return {"opened": str(job.folder)}


# Serve the frontend last so /api/* routes take priority.
if config.FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
