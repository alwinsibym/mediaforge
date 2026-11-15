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

from . import __version__, config, downloader, formats, transcoder, validators
from .downloader import ConversionError

app = FastAPI(title="MediaForge", version=__version__)

CHUNK_SIZE = 1024 * 1024  # 1 MB


class UrlRequest(BaseModel):
    url: str


class ConvertRequest(BaseModel):
    url: str
    format: str = "mp3"
    quality: str | None = None


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
        "ffmpeg": transcoder.ffmpeg_available(),
    }


@app.get("/api/formats")
def list_formats() -> dict:
    return {
        **formats.describe(),
        "limits": {
            "max_duration_seconds": config.MAX_DURATION_SECONDS,
            "max_upload_mb": config.MAX_UPLOAD_MB,
        },
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
        raise HTTPException(status_code=500, detail="Unexpected server error.")
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
        raise HTTPException(status_code=500, detail="Unexpected server error.")
    return _file_response(output, workdir)


# Serve the frontend last so /api/* routes take priority.
if config.FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
