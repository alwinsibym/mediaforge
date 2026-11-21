"""Optional hardware video encoding on an NVIDIA graphics card (NVENC).

Off unless the person turns on "Use my graphics card" in Settings. Whether it works is tested by
encoding one tiny frame, not guessed from a driver name. If a real conversion fails on the card,
MediaForge switches it off for the rest of the session and redoes the job on the processor.
"""

import subprocess
import threading

from . import ffmpeg_locator, settings

_ENCODERS = {"h264": "h264_nvenc", "h265": "hevc_nvenc"}
_lock = threading.Lock()
_state: dict | None = None
_disabled_reason: str | None = None


def _try_encoder(ffmpeg: str, encoder: str) -> bool:
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.2",
        "-frames:v", "1", "-c:v", encoder, "-f", "null", "-",
    ]  # fmt: skip
    try:
        return subprocess.run(command, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _card_name() -> str | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = (out.stdout or "").strip().splitlines()
    return line[0].strip() if out.returncode == 0 and line else None


def detect(force: bool = False) -> dict:
    """What the graphics card can encode: h264 and h265 (True or False) and its name."""
    global _state
    with _lock:
        if _state is not None and not force:
            return _state
        ffmpeg = ffmpeg_locator.find_tool("ffmpeg")
        if not ffmpeg:
            return {"h264": False, "h265": False, "name": None}
        found = {codec: _try_encoder(ffmpeg, enc) for codec, enc in _ENCODERS.items()}
        found["name"] = _card_name() if any(found.values()) else None
        _state = found
        return found


def reset() -> None:
    """Forget what was detected, and any earlier failure (used by 'Test again')."""
    global _state, _disabled_reason
    with _lock:
        _state = None
        _disabled_reason = None


def disable(reason: str) -> None:
    global _disabled_reason
    _disabled_reason = reason


def disabled_reason() -> str | None:
    return _disabled_reason


def enabled(codec: str) -> bool:
    """True when the person asked for the card, it works, and it has not failed this session."""
    if _disabled_reason is not None or codec not in _ENCODERS:
        return False
    if not settings.load().get("gpu"):
        return False
    return bool(detect().get(codec))


def args(codec: str, container: str, bitrate_kbps: int | None = None) -> list[str]:
    """Encoder arguments for the card. `bitrate_kbps` switches from quality to a size target."""
    encoder = _ENCODERS[codec]
    result = ["-c:v", encoder, "-preset", "p4", "-rc", "vbr", "-pix_fmt", "yuv420p"]
    if bitrate_kbps is None:
        result += ["-cq", "23" if codec == "h264" else "28", "-b:v", "0"]
    else:
        result += [
            "-b:v", f"{bitrate_kbps}k",
            "-maxrate", f"{int(bitrate_kbps * 1.1)}k",
            "-bufsize", f"{bitrate_kbps * 2}k",
        ]  # fmt: skip
    if codec == "h265" and container == "mp4":
        result += ["-tag:v", "hvc1"]
    return result
