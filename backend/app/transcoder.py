"""Convert local audio/video files with FFmpeg."""

import dataclasses
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import ffmpeg_locator, formats, gpu
from . import tweaks as tw
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


# Evens out the volume to the level streaming sites use, with headroom against clipping.
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"


def build_command(
    source: Path,
    target: Path,
    fmt: str,
    quality: str,
    mute: bool = False,
    normalize: bool = False,
    use_gpu: bool = False,
) -> list[str]:
    """Build the ffmpeg argument list for converting `source` into `fmt`."""
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    if normalize and not mute:
        command += ["-af", LOUDNORM]  # applies to the output below

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
            if use_gpu:
                command += gpu.args("h264", fmt)
            else:
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
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _DURATION_RE.search(result.stderr or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _run_with_progress(
    command: list[str], duration: float | None, report, cwd: Path | None = None
) -> tuple[int, str]:
    """Run FFmpeg and report how far along it is. Returns (exit code, error text)."""
    command = [command[0], "-progress", "pipe:1", "-nostats", *command[1:]]
    started = time.monotonic()
    with tempfile.TemporaryFile("w+") as errors:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            encoding="utf-8",
            errors="replace",
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
    normalize: bool = False,
    tweaks: "tw.Tweaks | None" = None,
    audio_file: Path | None = None,
    subtitle_file: Path | None = None,
    cover_file: Path | None = None,
) -> Path:
    """Convert `source` and return the path of the converted file.

    `progress`, if given, receives dicts with phase, percent and eta while FFmpeg works. It may
    raise `downloader.Cancelled` to stop the conversion.
    """
    if not ffmpeg_available():
        raise ConversionError(FFMPEG_HELP)

    if tweaks is not None and not tweaks.is_default:
        return _convert_with_tweaks(
            source,
            fmt,
            quality,
            workdir,
            mute,
            progress,
            normalize,
            tweaks,
            audio_file,
            subtitle_file,
            cover_file,
        )

    ext = formats.extension(fmt)
    target = workdir / f"{source.stem}.{ext}"
    if target == source:
        target = workdir / f"{source.stem}-converted.{ext}"

    wants_gpu = (
        formats.is_video(fmt)
        and not formats.is_preset(fmt)
        and fmt in ("mp4", "mkv")
        and gpu.enabled("h264")
    )
    duration = media_duration(source)
    for use_gpu in (True, False) if wants_gpu else (False,):
        command = build_command(source, target, fmt, quality, mute, normalize, use_gpu)
        if progress is not None:
            progress({"phase": "converting", "percent": 0})
        code, error_text = _run(command, duration, progress, workdir)
        if (code == 0 and target.exists()) or not use_gpu:
            break
        gpu.disable("The graphics card could not encode, so the processor is used instead.")

    if code != 0 or not target.exists():
        detail = error_text.strip().splitlines()
        reason = detail[-1] if detail else "unknown error"
        raise ConversionError(f"FFmpeg could not convert this file: {reason[:200]}")

    return target


def _has_audio(path: Path) -> bool:
    return bool(probe(path).get("audio"))


def _audio_channels(path: Path) -> str | None:
    """'stereo', '5.1' and so on for the first sound track, if FFmpeg reported it."""
    tracks = probe(path).get("audio") or []
    return tracks[0].get("channels") if tracks else None


def _run(command: list[str], duration: float | None, progress, cwd: Path) -> tuple[int, str]:
    if progress is not None:
        return _run_with_progress(command, duration, progress, cwd=cwd)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError("The conversion took too long and was stopped.") from exc
    return result.returncode, result.stderr or ""


def _convert_with_tweaks(
    source,
    fmt,
    quality,
    workdir,
    mute,
    progress,
    normalize,
    tweaks,
    audio_file,
    subtitle_file,
    cover_file=None,
) -> Path:
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    ext = (
        "gif"
        if tweaks.animated == "gif"
        else "webp"
        if tweaks.animated == "webp"
        else formats.extension(fmt)
    )
    target = workdir / f"{source.stem}.{ext}"
    if target == source:
        target = workdir / f"{source.stem}-converted.{ext}"

    duration = media_duration(source)
    out_len = tw.effective_duration(duration, tweaks)
    if tweaks.animated:
        if out_len is None or out_len > tw.ANIMATED_MAX_SECONDS:
            raise ConversionError(
                f"GIF and WebP are for short clips. Trim to {tw.ANIMATED_MAX_SECONDS} seconds "
                "or less."
            )

    # Subtitle files are copied to a name MediaForge chose, so the filter never sees user text.
    sub_name = None
    sub_path = None
    if subtitle_file is not None and tweaks.subtitles:
        suffix = subtitle_file.suffix.lower()
        sub_name = f"subtitles{suffix}"
        sub_path = workdir / sub_name
        shutil.copyfile(subtitle_file, sub_path)

    has_audio = _has_audio(source)
    channels = _audio_channels(source) if tweaks.spatial else None
    if not has_audio and not mute and tweaks.changes_sound and not tweaks.replace_audio:
        raise ConversionError("This file has no sound, so the sound tweaks cannot be applied.")

    codec = tweaks.video_codec or ("vp9" if fmt == "webm" else "h264")
    gpu_codec = (
        codec if formats.is_video(fmt) and not tweaks.animated and gpu.enabled(codec) else None
    )

    def run(bitrate=None, audio_kbps=None):
        for use_gpu in (True, False) if gpu_codec and gpu.enabled(gpu_codec) else (False,):
            try:
                _run_once(bitrate, audio_kbps, use_gpu)
                return
            except ConversionError:
                if not use_gpu:
                    raise
                gpu.disable("The graphics card could not encode, so the processor is used instead.")

    def _run_once(bitrate, audio_kbps, use_gpu):
        try:
            command = tw.build_command(
                source,
                target,
                fmt,
                quality,
                tweaks,
                ffmpeg=ffmpeg,
                duration=duration,
                mute=mute,
                normalize=normalize,
                audio_file=audio_file,
                subtitle_name=sub_name,
                subtitle_file=sub_path,
                cover_file=cover_file,
                bitrate_kbps=bitrate,
                audio_kbps=audio_kbps,
                has_audio=has_audio,
                channels=channels,
                use_gpu=use_gpu,
            )
        except ValueError as exc:
            raise ConversionError(str(exc)) from exc
        if progress is not None:
            progress({"phase": "converting", "percent": 0})
        code, error_text = _run(command, out_len, progress, workdir)
        if code != 0 or not target.exists():
            detail = error_text.strip().splitlines()
            reason = detail[-1] if detail else "unknown error"
            raise ConversionError(f"FFmpeg could not convert this file: {reason[:200]}")

    limit = int(tweaks.target_mb * 1024 * 1024) if tweaks.target_mb else None
    if limit is None:
        run()
        return target
    if out_len is None or out_len <= 0:
        raise ConversionError(
            "The length of this file could not be read, so a size target cannot be set."
        )
    shrink = 1.0
    for _attempt in range(3):
        try:
            if formats.is_audio(fmt):
                run(audio_kbps=tw.audio_bitrate_for_size(tweaks.target_mb, out_len, shrink))
            else:
                video_kbps, audio_kbps = tw.plan_bitrates(
                    tweaks.target_mb, out_len, has_audio and not mute, shrink
                )
                run(bitrate=video_kbps, audio_kbps=audio_kbps or None)
        except ValueError as exc:
            raise ConversionError(str(exc)) from exc
        size = target.stat().st_size
        if size <= limit:
            return target
        shrink *= max(0.5, limit / size * 0.92)
    raise ConversionError(
        f"Could not get this under {tweaks.target_mb:g} MB without ruining it. "
        "Try a larger size or a shorter clip."
    )


SAMPLE_SECONDS = 10


def make_sample(
    source: Path,
    fmt: str,
    quality: str,
    workdir: Path,
    mute: bool = False,
    normalize: bool = False,
    tweaks: "tw.Tweaks | None" = None,
    audio_file: Path | None = None,
    subtitle_file: Path | None = None,
    cover_file: Path | None = None,
) -> dict:
    """Convert a short piece from the middle of the file with the chosen settings.

    Returns the sample's path and an estimate for the whole file: its size and how long the
    conversion should take, worked out from how long and how big the sample turned out.
    """
    if not ffmpeg_available():
        raise ConversionError(FFMPEG_HELP)
    tweaks = tweaks or tw.Tweaks()
    duration = media_duration(source)
    full = tw.effective_duration(duration, tweaks)
    if not full or full <= 0:
        raise ConversionError(
            "The length of this file could not be read, so no sample can be made."
        )
    begin = tweaks.start or 0.0
    length = min(float(SAMPLE_SECONDS), full)
    start = begin + max(0.0, (full - length) / 2)
    scaled_target = tweaks.target_mb * length / full if tweaks.target_mb else None
    sample_tweaks = dataclasses.replace(
        tweaks, start=start, end=start + length, target_mb=scaled_target, title=None
    )
    started = time.monotonic()
    path = convert_file(
        source, fmt, quality, workdir, mute, None, normalize, sample_tweaks,
        audio_file, subtitle_file, cover_file,
    )  # fmt: skip
    seconds = time.monotonic() - started
    size = path.stat().st_size
    whole = tweaks.target_mb * 1024 * 1024 if tweaks.target_mb else size / length * full
    return {
        "path": path,
        "sample_seconds": round(length, 1),
        "sample_bytes": size,
        "estimated_bytes": int(whole),
        "estimated_seconds": round(seconds / length * full, 1),
        "whole_seconds": round(full, 1),
    }


def probe(path: Path) -> dict:
    """Plain facts about a media file, read from FFmpeg's report (no ffprobe needed)."""
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    try:
        text = (
            subprocess.run(
                [ffmpeg, "-hide_banner", "-i", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            ).stderr
            or ""
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"video": [], "audio": [], "subtitles": []}
    info = {
        "duration": None,
        "bitrate_kbps": None,
        "video": [],
        "audio": [],
        "subtitles": [],
        "metadata": False,
    }
    m = _DURATION_RE.search(text)
    if m:
        h, mi, se = m.groups()
        info["duration"] = int(h) * 3600 + int(mi) * 60 + float(se)
    b = re.search(r"bitrate:\s*(\d+)\s*kb/s", text)
    if b:
        info["bitrate_kbps"] = int(b.group(1))
    for line in text.splitlines():
        s = re.match(
            r"\s*Stream #\d+:\d+(?:\[[^\]]*\])?(?:\((\w+)\))?: (Video|Audio|Subtitle): (.*)", line
        )
        if not s:
            continue
        lang, kind, rest = s.groups()
        codec = rest.split(",")[0].split(" ")[0].strip()
        entry = {"codec": codec}
        if lang and lang != "und":
            entry["language"] = lang
        kb = re.search(r"(\d+)\s*kb/s", rest)
        if kb:
            entry["bitrate_kbps"] = int(kb.group(1))
        if kind == "Video":
            size = re.search(r"(\d{2,5})x(\d{2,5})", rest)
            if size:
                entry["width"], entry["height"] = int(size.group(1)), int(size.group(2))
            fps = re.search(r"([\d.]+)\s*fps", rest)
            if fps:
                entry["fps"] = float(fps.group(1))
            if "attached pic" in rest:
                continue
            info["video"].append(entry)
        elif kind == "Audio":
            hz = re.search(r"(\d+)\s*Hz", rest)
            if hz:
                entry["sample_rate"] = int(hz.group(1))
            for name in ("mono", "stereo", "5.1", "7.1"):
                if f", {name}" in rest:
                    entry["channels"] = name
            info["audio"].append(entry)
        else:
            info["subtitles"].append(entry)
    info["metadata"] = bool(
        re.search(
            r"^\s{2,4}(location|com\.apple|make|model|creation_time|artist|title|comment|encoder)\b",
            text,
            re.M | re.I,
        )
    )
    return info


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
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFMPEG_TIMEOUT_SECONDS,
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


# Audio codec to use when a finished file has to be re-encoded to change its volume.
_NORMALIZE_CODECS = {
    "mp3": ("libmp3lame", True),
    "m4a": ("aac", True),
    "aac": ("aac", True),
    "mp4": ("aac", True),
    "mkv": ("aac", True),
    "webm": ("libopus", True),
    "ogg": ("libvorbis", True),
    "opus": ("libopus", True),
    "flac": ("flac", False),
    "wav": ("pcm_s16le", False),
}


def normalize_loudness(path: Path, fmt: str, quality: str, progress=None) -> None:
    """Even out the volume of a finished file in place. The picture is copied, not re-encoded."""
    if not ffmpeg_available():
        raise ConversionError(FFMPEG_HELP)
    codec, lossy = _NORMALIZE_CODECS.get(fmt, ("aac", True))
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg") or "ffmpeg"
    louder = path.with_name(f"{path.stem}.normalized{path.suffix}")
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path)]
    command += ["-map", "0", "-map_metadata", "0", "-c", "copy", "-c:a", codec]
    if lossy and quality.isdigit():
        command += ["-b:a", f"{quality}k"]
    elif lossy:
        command += ["-b:a", "192k"]
    command += ["-af", LOUDNORM]
    if fmt == "mp3":
        command += ["-id3v2_version", "3"]
    command.append(str(louder))

    report = progress or (lambda update: None)
    report({"phase": "converting", "percent": 0})
    code, error_text = _run_with_progress(command, media_duration(path), report)
    if code != 0 or not louder.exists():
        louder.unlink(missing_ok=True)
        lines = error_text.strip().splitlines()
        raise ConversionError(
            f"FFmpeg could not even out the volume: {(lines or ['error'])[-1][:200]}"
        )
    louder.replace(path)
