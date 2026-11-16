"""Supported output formats and quality options."""

# ffmpeg audio codec per output format (used by the file-upload converter).
# "ytdlp" is the codec name yt-dlp's audio extractor expects.
AUDIO_FORMATS = {
    "mp3": {"label": "MP3", "ffmpeg_codec": "libmp3lame", "ytdlp_codec": "mp3"},
    "m4a": {"label": "M4A (AAC)", "ffmpeg_codec": "aac", "ytdlp_codec": "m4a"},
    "aac": {"label": "AAC", "ffmpeg_codec": "aac", "ytdlp_codec": "aac"},
    "wav": {"label": "WAV (lossless)", "ffmpeg_codec": "pcm_s16le", "ytdlp_codec": "wav"},
    "flac": {"label": "FLAC (lossless)", "ffmpeg_codec": "flac", "ytdlp_codec": "flac"},
    "ogg": {"label": "OGG Vorbis", "ffmpeg_codec": "libvorbis", "ytdlp_codec": "vorbis"},
    "opus": {"label": "Opus", "ffmpeg_codec": "libopus", "ytdlp_codec": "opus"},
}

VIDEO_FORMATS = {
    "mp4": {"label": "MP4 (H.264)"},
    "webm": {"label": "WebM (VP9)"},
    "mkv": {"label": "MKV"},
    # Presets for older car head units. The quality is fixed by the preset.
    "sony_mp4": {
        "label": "Sony car MP4 (XAV-W650BT)",
        "extension": "mp4",
        "preset": True,
    },
    "sony_avi": {
        "label": "Sony car AVI (Xvid)",
        "extension": "avi",
        "preset": True,
    },
}

# Quality value used by presets, which have no quality choices of their own.
PRESET_QUALITY = "preset"

# Lossless formats ignore the bitrate setting.
LOSSLESS_AUDIO = {"wav", "flac"}

AUDIO_BITRATES = ["128", "192", "256", "320"]  # kbps
VIDEO_HEIGHTS = ["360", "480", "720", "1080", "best"]

DEFAULT_AUDIO_BITRATE = "192"
DEFAULT_VIDEO_HEIGHT = "720"


def is_audio(fmt: str) -> bool:
    return fmt in AUDIO_FORMATS


def is_video(fmt: str) -> bool:
    return fmt in VIDEO_FORMATS


def is_preset(fmt: str) -> bool:
    return bool(VIDEO_FORMATS.get(fmt, {}).get("preset"))


def extension(fmt: str) -> str:
    """File extension (without the dot) for an output format."""
    return VIDEO_FORMATS.get(fmt, {}).get("extension", fmt)


def normalize(fmt: str, quality: str | None) -> tuple[str, str]:
    """Validate a format/quality pair and return the normalised values.

    Raises ValueError with a user-friendly message for unsupported input.
    """
    fmt = (fmt or "").lower().strip()

    if is_audio(fmt):
        quality = (quality or DEFAULT_AUDIO_BITRATE).strip()
        if quality not in AUDIO_BITRATES:
            raise ValueError(f"Unsupported audio bitrate '{quality}'.")
        return fmt, quality

    if is_preset(fmt):
        return fmt, PRESET_QUALITY

    if is_video(fmt):
        quality = (quality or DEFAULT_VIDEO_HEIGHT).strip()
        if quality not in VIDEO_HEIGHTS:
            raise ValueError(f"Unsupported video quality '{quality}'.")
        return fmt, quality

    raise ValueError(f"Unsupported format '{fmt}'.")


def describe() -> dict:
    """Format catalogue sent to the frontend."""
    return {
        "audio": [{"id": k, "label": v["label"]} for k, v in AUDIO_FORMATS.items()],
        "video": [
            {"id": k, "label": v["label"], "preset": bool(v.get("preset"))}
            for k, v in VIDEO_FORMATS.items()
        ],
        "audio_bitrates": AUDIO_BITRATES,
        "video_heights": VIDEO_HEIGHTS,
        "lossless_audio": sorted(LOSSLESS_AUDIO),
        "defaults": {
            "audio_bitrate": DEFAULT_AUDIO_BITRATE,
            "video_height": DEFAULT_VIDEO_HEIGHT,
        },
    }
