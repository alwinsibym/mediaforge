"""Convert local audio/video files with FFmpeg."""

import subprocess
from pathlib import Path

from . import ffmpeg_locator, formats
from .downloader import FFMPEG_HELP, ConversionError

FFMPEG_TIMEOUT_SECONDS = 1800


def ffmpeg_available() -> bool:
    return ffmpeg_locator.find_tool("ffmpeg") is not None


# Limits of the Sony XAV-W650BT USB video player (from Sony's manual):
#   MP4: MPEG-4 Simple Profile + AAC, up to 4 Mbps
#   AVI: Xvid (MPEG-4 ASP) + MP3, up to 8 Mbps
#   Both: up to 720 x 576 pixels and 30 frames per second.
_SONY_SCALE = (
    "scale='min(720,iw)':'min(576,ih)':force_original_aspect_ratio=decrease"
    ":force_divisible_by=2,setsar=1"
)
_SONY_VIDEO_COMMON = ["-vf", _SONY_SCALE, "-r", "30", "-pix_fmt", "yuv420p", "-c:v", "mpeg4"]
_SONY_VIDEO_COMMON += ["-bf", "0", "-g", "60"]
_SONY_STREAMS = ["-map", "0:v:0", "-map", "0:a:0?", "-sn", "-map_metadata", "0"]


def _sony_args(fmt: str) -> list[str]:
    if fmt == "sony_mp4":
        # 3.3 Mbps video + 192 kbps audio stays under the 4 Mbps limit.
        video = ["-b:v", "3300k", "-maxrate", "3500k", "-bufsize", "3500k"]
        audio = ["-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "44100"]
        return _SONY_STREAMS + _SONY_VIDEO_COMMON + video + audio + ["-movflags", "+faststart"]
    video = ["-b:v", "6500k", "-maxrate", "7200k", "-bufsize", "7200k", "-vtag", "XVID"]
    audio = ["-c:a", "libmp3lame", "-b:a", "192k", "-ac", "2", "-ar", "44100"]
    return _SONY_STREAMS + _SONY_VIDEO_COMMON + video + audio


def build_command(source: Path, target: Path, fmt: str, quality: str) -> list[str]:
    """Build the ffmpeg argument list for converting `source` into `fmt`."""
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]

    if formats.is_preset(fmt):
        command += _sony_args(fmt)
    elif formats.is_audio(fmt):
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
        raise ConversionError(FFMPEG_HELP)

    ext = formats.extension(fmt)
    target = workdir / f"{source.stem}.{ext}"
    if target == source:
        target = workdir / f"{source.stem}-converted.{ext}"

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
