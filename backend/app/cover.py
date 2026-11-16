"""Add square cover art to MP3 and M4A files in the way players and car units expect.

yt-dlp can embed a cover too, but it keeps the 16:9 video frame and writes ID3 version 2.4.
Many car head units, Windows Explorer and older players ignore that. This module crops the
image to a square JPEG and writes ID3 version 2.3, which they read.
"""

import subprocess
from pathlib import Path

from . import ffmpeg_locator

COVER_FORMATS = {"mp3", "m4a"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TIMEOUT_SECONDS = 120

# Centre-crop to a square, then shrink to at most 1000 pixels. Never enlarge.
_SQUARE_FILTER = "crop='min(iw,ih)':'min(iw,ih)',scale='min(1000,iw)':-2"


class CoverError(Exception):
    """The cover could not be added."""


def _run(command: list[str]) -> None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CoverError(str(exc)) from exc
    if result.returncode != 0:
        lines = (result.stderr or "").strip().splitlines()
        raise CoverError(lines[-1][:200] if lines else "FFmpeg failed")


def make_square_jpeg(image: Path, target: Path) -> None:
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    _run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(image)]
        + ["-vf", _SQUARE_FILTER, "-frames:v", "1", "-q:v", "2", "-pix_fmt", "yuvj420p"]
        + [str(target)]
    )


def has_cover(audio: Path) -> bool:
    """True when the file contains an attached picture."""
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(audio)],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    return "Video:" in (result.stderr or "")


def embed_cover(audio: Path, image: Path) -> None:
    """Replace `audio` with a copy that carries `image` as its front cover."""
    fmt = audio.suffix.lower().lstrip(".")
    if fmt not in COVER_FORMATS:
        raise CoverError(f"Cover art is not supported for .{fmt} files.")

    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    square = audio.with_name(f"{audio.stem}.cover.jpg")
    tagged = audio.with_name(f"{audio.stem}.tagged{audio.suffix}")
    try:
        make_square_jpeg(image, square)
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(audio)]
        command += ["-i", str(square), "-map", "0:a", "-map", "1:v", "-c", "copy"]
        command += ["-map_metadata", "0"]
        if fmt == "mp3":
            command += ["-id3v2_version", "3"]
            command += ["-metadata:s:v", "title=Album cover"]
            command += ["-metadata:s:v", "comment=Cover (front)"]
        else:
            command += ["-disposition:v:0", "attached_pic"]
        command.append(str(tagged))
        _run(command)
        if not has_cover(tagged):
            raise CoverError("The cover did not end up in the file.")
        tagged.replace(audio)
    finally:
        square.unlink(missing_ok=True)
        tagged.unlink(missing_ok=True)


def find_image(workdir: Path) -> Path | None:
    """The thumbnail image yt-dlp left in `workdir`, if any."""
    images = [p for p in workdir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    return max(images, key=lambda p: p.stat().st_size) if images else None
