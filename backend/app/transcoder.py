"""Convert local audio/video files with FFmpeg."""

import re
import subprocess
import tempfile
import time
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
_SONY_STREAMS_MUTED = ["-map", "0:v:0", "-an", "-sn", "-map_metadata", "0"]


def _sony_args(fmt: str, mute: bool = False) -> list[str]:
    if fmt == "sony_mp4":
        # 3.3 Mbps video + 192 kbps audio stays under the 4 Mbps limit.
        video = ["-b:v", "3300k", "-maxrate", "3500k", "-bufsize", "3500k"]
        audio = ["-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "44100"]
        streams = _SONY_STREAMS_MUTED if mute else _SONY_STREAMS
        audio = [] if mute else audio
        return streams + _SONY_VIDEO_COMMON + video + audio + ["-movflags", "+faststart"]
    video = ["-b:v", "6500k", "-maxrate", "7200k", "-bufsize", "7200k", "-vtag", "XVID"]
    audio = ["-c:a", "libmp3lame", "-b:a", "192k", "-ac", "2", "-ar", "44100"]
    streams = _SONY_STREAMS_MUTED if mute else _SONY_STREAMS
    audio = [] if mute else audio
    return streams + _SONY_VIDEO_COMMON + video + audio


def build_command(
    source: Path, target: Path, fmt: str, quality: str, mute: bool = False
) -> list[str]:
    """Build the ffmpeg argument list for converting `source` into `fmt`."""
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]

    if formats.is_preset(fmt):
        command += _sony_args(fmt, mute)
    elif formats.is_audio(fmt):
        command += ["-vn", "-c:a", formats.AUDIO_FORMATS[fmt]["ffmpeg_codec"]]
        if fmt not in formats.LOSSLESS_AUDIO:
            command += ["-b:a", f"{quality}k"]
    else:
        height, _ = formats.parse_quality(quality)
        if height:
            # Scale down only; never upscale. -2 keeps the width even.
            command += ["-vf", f"scale=-2:'min(ih,{height})'"]
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
            ]
            command += ["-an"] if mute else ["-c:a", "libopus"]
        else:  # mp4, mkv
            command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
            command += ["-an"] if mute else ["-c:a", "aac"]
            if fmt == "mp4":
                command += ["-movflags", "+faststart"]

    command.append(str(target))
    return command


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def media_duration(path: Path) -> float | None:
    """Length of a media file in seconds, read from FFmpeg's own report (no ffprobe needed)."""
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _DURATION_RE.search(result.stderr or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _run_with_progress(command: list[str], duration: float | None, report) -> tuple[int, str]:
    """Run FFmpeg and report how far along it is. Returns (exit code, error text)."""
    command = [command[0], "-progress", "pipe:1", "-nostats", *command[1:]]
    started = time.monotonic()
    with tempfile.TemporaryFile("w+") as errors:
        process = subprocess.Popen(  # noqa: S603
            command, stdout=subprocess.PIPE, stderr=errors, text=True
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                if time.monotonic() - started > FFMPEG_TIMEOUT_SECONDS:
                    raise ConversionError("The conversion took too long and was stopped.")
                key, _, value = line.strip().partition("=")
                if key not in ("out_time_us", "out_time_ms") or not value.lstrip("-").isdigit():
                    continue
                seconds = int(value) / 1_000_000
                if duration and seconds > 0:
                    percent = min(99.0, seconds / duration * 100)
                    elapsed = time.monotonic() - started
                    eta = elapsed / percent * (100 - percent) if percent > 1 else None
                    report({"phase": "converting", "percent": percent, "speed": None, "eta": eta})
                else:
                    report({"phase": "converting", "percent": None})
            process.wait(timeout=30)
        except BaseException:
            process.kill()
            process.wait()
            raise
        errors.seek(0)
        return process.returncode, errors.read()


def convert_file(
    source: Path,
    fmt: str,
    quality: str,
    workdir: Path,
    mute: bool = False,
    progress=None,
) -> Path:
    """Convert `source` and return the path of the converted file.

    `progress`, if given, receives dicts with phase, percent and eta while FFmpeg works. It may
    raise `downloader.Cancelled` to stop the conversion.
    """
    if not ffmpeg_available():
        raise ConversionError(FFMPEG_HELP)

    ext = formats.extension(fmt)
    target = workdir / f"{source.stem}.{ext}"
    if target == source:
        target = workdir / f"{source.stem}-converted.{ext}"

    command = build_command(source, target, fmt, quality, mute)
    if progress is not None:
        progress({"phase": "converting", "percent": 0})
        code, error_text = _run_with_progress(command, media_duration(source), progress)
    else:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired as exc:
            raise ConversionError("The conversion took too long and was stopped.") from exc
        code, error_text = result.returncode, result.stderr or ""

    if code != 0 or not target.exists():
        detail = error_text.strip().splitlines()
        reason = detail[-1] if detail else "unknown error"
        raise ConversionError(f"FFmpeg could not convert this file: {reason[:200]}")

    return target


def strip_audio(path: Path) -> None:
    """Remove the sound from a finished video file, without re-encoding the picture."""
    if not ffmpeg_available():
        raise ConversionError(FFMPEG_HELP)
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    silent = path.with_name(f"{path.stem}.silent{path.suffix}")
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path)]
    command += ["-map", "0", "-map", "-0:a", "-c", "copy", "-map_metadata", "0", str(silent)]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        silent.unlink(missing_ok=True)
        raise ConversionError("Removing the sound took too long and was stopped.") from exc
    if result.returncode != 0 or not silent.exists():
        silent.unlink(missing_ok=True)
        lines = (result.stderr or "").strip().splitlines()
        raise ConversionError(
            f"FFmpeg could not remove the sound: {(lines or ['error'])[-1][:200]}"
        )
    silent.replace(path)
