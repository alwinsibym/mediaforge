"""Convert local audio/video files with FFmpeg."""

import shutil
import subprocess
from pathlib import Path

from . import formats
from .downloader import ConversionError

FFMPEG_TIMEOUT_SECONDS = 1800


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def build_command(source: Path, target: Path, fmt: str, quality: str) -> list[str]:
    """Build the ffmpeg argument list for converting `source` into `fmt`."""
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]

    if formats.is_audio(fmt):
        command += ["-vn", "-c:a", formats.AUDIO_FORMATS[fmt]["ffmpeg_codec"]]
        if fmt not in formats.LOSSLESS_AUDIO:
            command += ["-b:a", f"{quality}k"]
    else:
        if quality != "best":
            # Scale down only; never upscale. -2 keeps the width even.
            command += ["-vf", f"scale=-2:'min(ih,{quality})'"]
        if fmt == "webm":
            command += [
                "-c:v",
                "libvpx-vp9",
                "-crf",
                "32",
                "-b:v",
                "0",
                "-row-mt",
                "1",
                "-c:a",
                "libopus",
            ]
        else:  # mp4, mkv
            command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac"]
            if fmt == "mp4":
                command += ["-movflags", "+faststart"]

    command.append(str(target))
    return command


def convert_file(source: Path, fmt: str, quality: str, workdir: Path) -> Path:
    """Convert `source` and return the path of the converted file."""
    if not ffmpeg_available():
        raise ConversionError("FFmpeg is not installed on the server.")

    target = workdir / f"{source.stem}.{fmt}"
    if target == source:
        target = workdir / f"{source.stem}-converted.{fmt}"

    try:
        result = subprocess.run(
            build_command(source, target, fmt, quality),
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError("The conversion took too long and was stopped.") from exc

    if result.returncode != 0 or not target.exists():
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else "unknown error"
        raise ConversionError(f"FFmpeg could not convert this file: {reason[:200]}")

    return target
