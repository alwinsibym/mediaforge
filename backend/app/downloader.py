"""Download media from a URL with yt-dlp and convert it with FFmpeg."""

import os
import re
import shutil
import sys
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError

from . import config, formats

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class ConversionError(Exception):
    """A problem the user can understand (bad URL, too long, unsupported...)."""


def _clean_error(exc: Exception) -> str:
    message = _ANSI_RE.sub("", str(exc)).strip()
    message = re.sub(r"^ERROR:\s*", "", message)
    # yt-dlp appends a bug-report hint that isn't useful to end users.
    message = message.split("; please report this issue")[0]
    return message[:300] or "The download failed."


# yt-dlp needs a JavaScript runtime to read YouTube. name -> executable.
_JS_RUNTIME_BINARIES = (
    ("deno", "deno"),
    ("node", "node"),
    ("bun", "bun"),
    ("quickjs", "qjs"),
)


def js_runtimes() -> dict:
    """Find installed JavaScript runtimes, including ones in the active venv."""
    search_path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    found = {}
    for name, binary in _JS_RUNTIME_BINARIES:
        path = shutil.which(binary, path=search_path)
        if path:
            found[name] = {"path": path}
    return found


def _base_options() -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "windowsfilenames": True,
    }
    runtimes = js_runtimes()
    if runtimes:
        options["js_runtimes"] = runtimes
    return options


def fetch_info(url: str) -> dict:
    """Return basic metadata for a URL without downloading it."""
    options = {**_base_options(), "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise ConversionError(_clean_error(exc)) from exc

    return {
        "title": info.get("title") or "Untitled",
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "thumbnail": info.get("thumbnail"),
        "is_live": bool(info.get("is_live")),
    }


def _video_selector(fmt: str, height: str) -> str:
    h = "" if height == "best" else f"[height<={height}]"
    if fmt == "mp4":
        return (
            f"bestvideo[ext=mp4]{h}+bestaudio[ext=m4a]"
            f"/best[ext=mp4]{h}/bestvideo{h}+bestaudio/best{h}"
        )
    if fmt == "webm":
        return (
            f"bestvideo[ext=webm]{h}+bestaudio[ext=webm]"
            f"/best[ext=webm]{h}/bestvideo{h}+bestaudio/best{h}"
        )
    return f"bestvideo{h}+bestaudio/best{h}"  # mkv


def _build_options(fmt: str, quality: str, workdir: Path) -> dict:
    options = _base_options()
    options["outtmpl"] = str(workdir / "%(title).80s.%(ext)s")

    if formats.is_audio(fmt):
        options["format"] = "bestaudio/best"
        postprocessor = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": formats.AUDIO_FORMATS[fmt]["ytdlp_codec"],
        }
        if fmt not in formats.LOSSLESS_AUDIO:
            postprocessor["preferredquality"] = quality
        options["postprocessors"] = [postprocessor]
    else:
        options["format"] = _video_selector(fmt, quality)
        options["merge_output_format"] = fmt
        # Re-mux only when the downloaded container differs from the request.
        options["postprocessors"] = [{"key": "FFmpegVideoConvertor", "preferedformat": fmt}]
    return options


def _find_output(workdir: Path, fmt: str) -> Path:
    files = [
        p for p in workdir.iterdir() if p.is_file() and p.suffix not in {".part", ".ytdl", ".tmp"}
    ]
    if not files:
        raise ConversionError("Conversion finished but no file was produced.")
    preferred = [p for p in files if p.suffix.lower() == f".{fmt}"]
    return max(preferred or files, key=lambda p: p.stat().st_size)


def download_and_convert(url: str, fmt: str, quality: str, workdir: Path) -> Path:
    """Download `url`, convert it to `fmt`, and return the output file path."""
    info = fetch_info(url)

    if info["is_live"]:
        raise ConversionError("Live streams can't be converted.")
    duration = info["duration"]
    if duration and duration > config.MAX_DURATION_SECONDS:
        limit_min = config.MAX_DURATION_SECONDS // 60
        raise ConversionError(f"This video is longer than the {limit_min}-minute limit.")

    options = _build_options(fmt, quality, workdir)
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except DownloadError as exc:
        raise ConversionError(_clean_error(exc)) from exc

    return _find_output(workdir, fmt)
