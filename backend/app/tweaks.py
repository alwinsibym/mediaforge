"""Optional changes to an uploaded file: codec, size, sound, subtitles, GIF and more.

Everything here builds FFmpeg arguments from validated choices. The page never sends raw
FFmpeg arguments, and file names never reach a filter string.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import ffmpeg_locator, formats
from .features import parse_timestamp

RESIZE_HEIGHTS = (360, 480, 720, 1080, 1440, 2160)
ANIMATED_WIDTHS = (320, 480, 640, 800)
ANIMATED_MAX_SECONDS = 60
MAX_FADE_SECONDS = 30
MIN_VOLUME, MAX_VOLUME = 10, 400  # percent
MIN_TARGET_MB, MAX_TARGET_MB = 0.5, 20000.0
MIN_VIDEO_KBPS = 100
SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa"}
AUDIO_FILE_LIMIT_NOTE = "Pick an audio file (MP3, M4A, WAV, FLAC, OGG, Opus and similar)."

# Container choices per video codec, and the FFmpeg encoders that make them.
VIDEO_CODECS = {
    "h264": {"label": "H.264 (plays everywhere)", "containers": {"mp4", "mkv"}},
    "h265": {"label": "H.265 / HEVC (smaller files)", "containers": {"mp4", "mkv"}},
    "vp9": {"label": "VP9", "containers": {"webm", "mkv"}},
    "av1": {"label": "AV1 (smallest, slow)", "containers": {"mp4", "webm", "mkv"}},
}

# Sound effects: plain names for a single FFmpeg filter chain each.
EFFECTS = {
    "bass": ("Bass boost", "bass=g=8:f=110:w=0.6"),
    "treble": ("Treble boost", "treble=g=6:f=3000"),
    "voice": ("Clearer voice", "highpass=f=90,equalizer=f=3000:t=q:w=1:g=3,afftdn=nf=-25"),
    "widen": ("Wider stereo", "stereowiden=delay=20:feedback=0.35:crossfeed=0.3:drymix=0.8"),
    "crossfeed": ("Headphone crossfeed", "crossfeed=strength=0.4"),
    "surround": (
        "Virtual surround (headphones)",
        "aresample=44100,aformat=channel_layouts=stereo,earwax",
    ),
}
_EFFECT_FILTERS = {
    "bass": "bass",
    "treble": "treble",
    "voice": "afftdn",
    "widen": "stereowiden",
    "crossfeed": "crossfeed",
    "surround": "earwax",
}

_TWEAK_KEYS = (
    "video_codec",
    "resize",
    "volume",
    "fade_in",
    "fade_out",
    "effect",
    "target_mb",
    "strip_metadata",
    "subtitles",
    "replace_audio",
    "animated",
    "start",
    "end",
)
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"
ANIMATED = ("", "gif", "webp")
SUBTITLE_MODES = ("", "soft", "burn")


@dataclass(frozen=True)
class Tweaks:
    video_codec: str = ""  # "" = the format's usual codec
    resize: int | None = None  # output height in pixels, up or down
    volume: int = 100  # percent
    fade_in: float = 0.0  # seconds
    fade_out: float = 0.0
    effect: str = ""
    target_mb: float | None = None  # compress to at most this many megabytes
    strip_metadata: bool = False
    subtitles: str = ""  # "", "soft" (a selectable track) or "burn" (drawn on the picture)
    replace_audio: bool = False
    animated: str = ""  # "", "gif" or "webp": make an animated picture instead
    animated_width: int = 480
    start: float | None = None  # seconds
    end: float | None = None
    title: str | None = None

    @property
    def trimmed(self) -> bool:
        return self.start is not None or self.end is not None

    @property
    def changes_picture(self) -> bool:
        return bool(
            self.video_codec
            or self.resize
            or self.subtitles == "burn"
            or self.target_mb
            or self.animated
        )

    @property
    def changes_sound(self) -> bool:
        return bool(
            self.volume != 100 or self.fade_in or self.fade_out or self.effect or self.replace_audio
        )

    @property
    def is_default(self) -> bool:
        return self == Tweaks()


def _number(data: dict, key: str, low: float, high: float, label: str) -> float | None:
    raw = data.get(key)
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.") from None
    if not low <= value <= high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}.")
    return value


def parse(
    data: dict | None, fmt: str, *, audio_file: bool = False, subtitle_file: bool = False
) -> Tweaks:
    """Check the person's choices against the output format and build a Tweaks.

    Raises ValueError with a plain-English message for anything that cannot work.
    """
    data = data or {}
    if formats.is_preset(fmt) and (
        audio_file or subtitle_file or any(data.get(k) for k in _TWEAK_KEYS)
    ):
        raise ValueError("The Sony presets cannot be combined with tweaks. Choose MP4 instead.")
    is_video = formats.is_video(fmt) and not formats.is_preset(fmt)
    animated = str(data.get("animated") or "")
    if animated not in ANIMATED:
        raise ValueError("Animated picture must be GIF or WebP.")

    codec = str(data.get("video_codec") or "")
    if codec and codec not in VIDEO_CODECS:
        raise ValueError(f"Unknown video codec '{codec}'.")
    if codec and not animated:
        if not is_video:
            raise ValueError("A video codec only applies when the output is MP4, WebM or MKV.")
        if fmt not in VIDEO_CODECS[codec]["containers"]:
            names = ", ".join(sorted(c.upper() for c in VIDEO_CODECS[codec]["containers"]))
            raise ValueError(
                f"{VIDEO_CODECS[codec]['label'].split(' (')[0]} can be stored in {names}."
            )

    height = _number(data, "resize", 100, 4320, "Resize")
    if height is not None and int(height) not in RESIZE_HEIGHTS:
        raise ValueError("Resize to 360, 480, 720, 1080, 1440 or 2160 pixels high.")
    if height is not None and not (is_video or animated):
        raise ValueError("Resizing only applies when the output is a video.")

    volume = _number(data, "volume", MIN_VOLUME, MAX_VOLUME, "Volume")
    fade_in = _number(data, "fade_in", 0, MAX_FADE_SECONDS, "Fade in") or 0.0
    fade_out = _number(data, "fade_out", 0, MAX_FADE_SECONDS, "Fade out") or 0.0

    effect = str(data.get("effect") or "")
    if effect and effect not in EFFECTS:
        raise ValueError(f"Unknown sound effect '{effect}'.")

    target = _number(data, "target_mb", MIN_TARGET_MB, MAX_TARGET_MB, "Target size")
    if target is not None and (animated or formats.is_preset(fmt) or fmt in formats.LOSSLESS_AUDIO):
        raise ValueError(
            "Compressing to a size does not work for lossless audio, GIF or the Sony presets."
        )

    mode = str(data.get("subtitles") or "")
    if mode not in SUBTITLE_MODES:
        raise ValueError("Subtitles must be 'add as a track' or 'burn in'.")
    if mode and not subtitle_file:
        raise ValueError("Choose a subtitle file (.srt, .vtt or .ass) first.")
    if subtitle_file and not mode:
        mode = "soft"
    if mode and not (is_video or animated):
        raise ValueError("Subtitles only apply when the output is a video.")
    if mode == "soft" and fmt == "webm" and animated:
        mode = ""
    if mode and animated:
        raise ValueError("Subtitles cannot be added to a GIF or WebP.")

    replace = bool(data.get("replace_audio")) or audio_file
    if replace and not audio_file:
        raise ValueError("Choose the audio file that should replace the sound.")
    if replace and (not is_video or animated):
        raise ValueError("Replacing the sound only applies when the output is a video.")
    if replace and data.get("mute"):
        raise ValueError("Pick either 'no sound' or a replacement audio file, not both.")

    strip = bool(data.get("strip_metadata"))
    title = str(data.get("title") or "").strip() or None
    if strip and title:
        raise ValueError("Removing metadata and setting a new title cannot be combined.")

    start = parse_timestamp(data.get("start"))
    end = parse_timestamp(data.get("end"))
    if start is not None and end is not None and end <= start:
        raise ValueError("The stop time must be after the start time.")

    width = _number(data, "animated_width", 100, 4000, "Width")
    if width is not None and int(width) not in ANIMATED_WIDTHS:
        raise ValueError("Pick a width of 320, 480, 640 or 800 pixels.")

    result = Tweaks(
        video_codec=codec if not animated else "",
        resize=int(height) if height is not None else None,
        volume=int(volume) if volume is not None else 100,
        fade_in=fade_in,
        fade_out=fade_out,
        effect=effect,
        target_mb=target,
        strip_metadata=strip,
        subtitles=mode,
        replace_audio=replace,
        animated=animated,
        animated_width=int(width) if width is not None else 480,
        start=start,
        end=end,
        title=title,
    )
    if formats.is_preset(fmt) and (
        result.changes_picture or result.changes_sound or result.trimmed
    ):
        raise ValueError("The Sony presets cannot be combined with tweaks. Choose MP4 instead.")
    return result


# ---------------------------------------------------------------- what this FFmpeg can do


_CAPS_CACHE: dict | None = None


def _listing(ffmpeg: str, flag: str) -> str:
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout or ""


def capabilities() -> dict:
    """Which encoders and filters this FFmpeg has, so the page can grey out what would fail.

    If FFmpeg's list cannot be read (slow start, odd build), the matching choices stay enabled:
    a real conversion still reports a clear error, which is better than hiding a working option.
    A list that could not be read is not remembered, so the next request tries again.
    """
    global _CAPS_CACHE
    if _CAPS_CACHE is not None:
        return _CAPS_CACHE
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg")
    if not ffmpeg:
        return {
            "video_codecs": {name: False for name in VIDEO_CODECS},
            "effects": {name: False for name in EFFECTS},
            "subtitles_burn": False,
            "animated": {"gif": False, "webp": False},
        }
    encoders_text = _listing(ffmpeg, "-encoders")
    filters_text = _listing(ffmpeg, "-filters")
    encoders = set(re.findall(r"^\s*[VAS][\w.]{5}\s+(\S+)", encoders_text, re.M))
    filters = set(re.findall(r"^\s*[\w.]{3}\s+(\S+)\s", filters_text, re.M))
    unknown_encoders = not encoders
    unknown_filters = not filters
    caps = {
        "video_codecs": {
            "h264": unknown_encoders or "libx264" in encoders,
            "h265": unknown_encoders or "libx265" in encoders,
            "vp9": unknown_encoders or "libvpx-vp9" in encoders,
            "av1": unknown_encoders or "libsvtav1" in encoders or "libaom-av1" in encoders,
        },
        "effects": {
            name: unknown_filters or flt in filters for name, flt in _EFFECT_FILTERS.items()
        },
        "subtitles_burn": unknown_filters or "subtitles" in filters,
        "animated": {
            "gif": unknown_filters or ("palettegen" in filters and "paletteuse" in filters),
            "webp": unknown_encoders or "libwebp" in encoders or "libwebp_anim" in encoders,
        },
    }
    if encoders and filters:
        _CAPS_CACHE = caps
    return caps


def describe() -> dict:
    """Choices and what this computer can do, for the page."""
    return {
        "resize_heights": list(RESIZE_HEIGHTS),
        "video_codecs": [
            {"id": k, "label": v["label"], "containers": sorted(v["containers"])}
            for k, v in VIDEO_CODECS.items()
        ],
        "effects": [{"id": k, "label": v[0]} for k, v in EFFECTS.items()],
        "animated_widths": list(ANIMATED_WIDTHS),
        "animated_max_seconds": ANIMATED_MAX_SECONDS,
        "subtitle_extensions": sorted(SUBTITLE_EXTENSIONS),
        "capabilities": capabilities(),
    }


def av1_encoder() -> str | None:
    ffmpeg = ffmpeg_locator.find_tool("ffmpeg")
    if not ffmpeg:
        return None
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for name in ("libsvtav1", "libaom-av1"):
        if re.search(rf"\s{name}\s", out):
            return name
    return None


# ---------------------------------------------------------------- building the command


def effective_duration(duration: float | None, tweaks: Tweaks) -> float | None:
    """Length of the output after trimming."""
    if duration is None:
        return (tweaks.end - (tweaks.start or 0)) if tweaks.end is not None else None
    end = min(tweaks.end, duration) if tweaks.end is not None else duration
    return max(0.0, end - (tweaks.start or 0))


def audio_filters(tweaks: Tweaks, normalize: bool, duration: float | None) -> list[str]:
    """Audio filters in the order they should run: effect, volume, loudness, then fades."""
    chain: list[str] = []
    if tweaks.effect:
        chain.append(EFFECTS[tweaks.effect][1])
    if tweaks.volume != 100:
        chain.append(f"volume={tweaks.volume / 100:g}")
    if normalize:
        chain.append(LOUDNORM)
    if tweaks.fade_in:
        chain.append(f"afade=t=in:st=0:d={tweaks.fade_in:g}")
    if tweaks.fade_out:
        if duration is None:
            raise ValueError(
                "The length of this file could not be read, so the fade out cannot be placed."
            )
        if tweaks.fade_out > duration:
            raise ValueError("The fade out is longer than the file.")
        chain.append(
            f"afade=t=out:st={max(0.0, duration - tweaks.fade_out):g}:d={tweaks.fade_out:g}"
        )
    return chain


def video_args(fmt: str, tweaks: Tweaks, quality: str, bitrate_kbps: int | None) -> list[str]:
    """Encoder arguments for the picture. `bitrate_kbps` switches from quality to a size target."""
    codec = tweaks.video_codec or {"webm": "vp9"}.get(fmt, "h264")
    kb = bitrate_kbps
    if codec == "h264":
        args = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        args += (
            ["-crf", "23"]
            if kb is None
            else ["-b:v", f"{kb}k", "-maxrate", f"{int(kb * 1.1)}k", "-bufsize", f"{kb * 2}k"]
        )
    elif codec == "h265":
        args = ["-c:v", "libx265", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        if fmt == "mp4":
            args += ["-tag:v", "hvc1"]
        args += (
            ["-crf", "28"]
            if kb is None
            else ["-b:v", f"{kb}k", "-maxrate", f"{int(kb * 1.1)}k", "-bufsize", f"{kb * 2}k"]
        )
    elif codec == "vp9":
        args = ["-c:v", "libvpx-vp9", "-row-mt", "1", "-pix_fmt", "yuv420p"]
        args += (
            ["-crf", "32", "-b:v", "0"]
            if kb is None
            else ["-b:v", f"{kb}k", "-maxrate", f"{int(kb * 1.1)}k"]
        )
    else:  # av1
        encoder = av1_encoder()
        if encoder is None:
            raise ValueError("This FFmpeg has no AV1 encoder. Choose H.264, H.265 or VP9.")
        if encoder == "libsvtav1":
            args = ["-c:v", "libsvtav1", "-preset", "8", "-pix_fmt", "yuv420p"]
            args += ["-crf", "35"] if kb is None else ["-b:v", f"{kb}k"]
        else:
            args = ["-c:v", "libaom-av1", "-cpu-used", "6", "-row-mt", "1", "-pix_fmt", "yuv420p"]
            args += ["-crf", "32", "-b:v", "0"] if kb is None else ["-b:v", f"{kb}k"]
    return args


def audio_codec_args(fmt: str) -> list[str]:
    return ["-c:a", "libopus"] if fmt == "webm" else ["-c:a", "aac"]


def plan_bitrates(
    target_mb: float, duration: float, has_audio: bool, shrink: float = 1.0
) -> tuple[int, int]:
    """(video kbps, audio kbps) that should land under `target_mb` for this length.

    `shrink` lowers the video bitrate when an earlier try came out too big.
    Raises ValueError when the target is too small to give a watchable picture.
    """
    total_kbits = target_mb * 8 * 1024 * 0.93  # leave room for the container
    audio = 0
    if has_audio:
        audio = 128 if total_kbits / duration > 400 else 64
    video = int((total_kbits / duration - audio) * shrink)
    if video < MIN_VIDEO_KBPS:
        longest = int(total_kbits / (MIN_VIDEO_KBPS + audio))
        raise ValueError(
            f"{target_mb:g} MB is too small for {int(duration)} seconds of video. "
            f"Try a larger size, or a clip of about {longest} seconds or less."
        )
    return video, audio


def audio_bitrate_for_size(target_mb: float, duration: float, shrink: float = 1.0) -> int:
    """Audio bitrate in kbps for an audio-only output under `target_mb`."""
    kbps = int(target_mb * 8 * 1024 * 0.95 / duration * shrink)
    if kbps < 24:
        raise ValueError(f"{target_mb:g} MB is too small for {int(duration)} seconds of audio.")
    return min(kbps, 320)


def build_command(
    source: Path,
    target: Path,
    fmt: str,
    quality: str,
    tweaks: Tweaks,
    *,
    ffmpeg: str,
    duration: float | None,
    mute: bool = False,
    normalize: bool = False,
    audio_file: Path | None = None,
    subtitle_name: str | None = None,
    subtitle_file: Path | None = None,
    bitrate_kbps: int | None = None,
    audio_kbps: int | None = None,
    has_audio: bool = True,
) -> list[str]:
    """The FFmpeg arguments for one conversion with tweaks.

    `subtitle_name` is the file name (not path) of a subtitle file that sits in the folder FFmpeg
    runs in; it is used by the burn-in filter, so it must be a plain name made by MediaForge.
    """
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    next_input = 1
    audio_input = None
    sub_input = None
    if audio_file is not None:
        command += ["-i", str(audio_file)]
        audio_input = next_input
        next_input += 1
    if subtitle_file is not None and tweaks.subtitles == "soft":
        command += ["-i", str(subtitle_file)]
        sub_input = next_input
        next_input += 1

    out_len = effective_duration(duration, tweaks)
    if tweaks.start is not None:
        command += ["-ss", f"{tweaks.start:g}"]
    if tweaks.end is not None:
        command += ["-to", f"{tweaks.end:g}"]
    if tweaks.animated and tweaks.start is None and tweaks.end is None:
        pass

    # ---- an animated picture
    if tweaks.animated:
        scale = f"fps=12,scale={tweaks.animated_width}:-2:flags=lanczos"
        if tweaks.resize:
            scale = f"fps=12,scale=-2:{tweaks.resize}:flags=lanczos"
        command += ["-map", "0:v:0", "-an", "-sn"]
        if tweaks.animated == "gif":
            command += [
                "-vf",
                f"{scale},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5",
                "-loop",
                "0",
            ]
        else:
            command += ["-vf", scale, "-c:v", "libwebp", "-q:v", "70", "-loop", "0"]
        if tweaks.strip_metadata:
            command += ["-map_metadata", "-1"]
        command.append(str(target))
        return command

    chain = audio_filters(tweaks, normalize and not mute, out_len)
    is_audio_out = formats.is_audio(fmt)

    if is_audio_out:
        command += ["-map", "0:a:0", "-vn"]
        command += ["-c:a", formats.AUDIO_FORMATS[fmt]["ffmpeg_codec"]]
        if fmt not in formats.LOSSLESS_AUDIO:
            kbps = audio_kbps or int(quality)
            command += ["-b:a", f"{kbps}k"]
        if chain:
            command += ["-af", ",".join(chain)]
    else:
        # picture
        command += ["-map", "0:v:0"]
        vfilters = []
        if tweaks.resize:
            vfilters.append(f"scale=-2:{tweaks.resize}:flags=lanczos")
        else:
            height, _ = formats.parse_quality(quality)
            if height:
                vfilters.append(f"scale=-2:'min(ih,{height})'")
        if tweaks.subtitles == "burn" and subtitle_name:
            vfilters.append(f"subtitles={subtitle_name}")
        if vfilters:
            command += ["-vf", ",".join(vfilters)]
        command += video_args(fmt, tweaks, quality, bitrate_kbps)
        # sound
        if mute:
            command += ["-an"]
        else:
            command += ["-map", f"{audio_input}:a:0" if audio_input is not None else "0:a:0?"]
            command += audio_codec_args(fmt)
            if audio_kbps:
                command += ["-b:a", f"{audio_kbps}k"]
            if chain:
                command += ["-af", ",".join(chain)]
            if audio_input is not None:
                command += ["-shortest"]
        # soft subtitles
        if sub_input is not None:
            codec = {"mp4": "mov_text", "webm": "webvtt"}.get(fmt, "srt")
            command += ["-map", f"{sub_input}:0", "-c:s", codec]
        else:
            command += ["-sn"]
        if fmt == "mp4":
            command += ["-movflags", "+faststart"]

    if tweaks.strip_metadata:
        command += ["-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact"]
        command += ["-flags:v", "+bitexact", "-flags:a", "+bitexact"]
    else:
        command += ["-map_metadata", "0"]
        if tweaks.title:
            command += ["-metadata", f"title={tweaks.title}"]
    if fmt == "mp3":
        command += ["-id3v2_version", "3"]
    command.append(str(target))
    return command
