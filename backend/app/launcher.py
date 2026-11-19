"""Helpers for run.py: reuse a running MediaForge, pick a port, log when there is no console."""

import json
import socket
import sys
import urllib.request
from pathlib import Path


def is_mediaforge(port: int, host: str = "127.0.0.1") -> bool:
    """True when a MediaForge server already answers on this port."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=1.5) as reply:
            data = json.loads(reply.read().decode("utf-8", errors="replace"))
        return isinstance(data, dict) and "ffmpeg" in data and "yt_dlp" in data
    except (OSError, ValueError):
        return False


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) != 0


def choose_port(start: int, tries: int = 10) -> tuple[int, bool]:
    """Return (port, already_running). Reuses a running MediaForge, else the first free port."""
    for port in range(start, start + tries):
        if is_mediaforge(port):
            return port, True
        if port_is_free(port):
            return port, False
    raise OSError(f"Ports {start} to {start + tries - 1} are all in use.")


def log_file(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "mediaforge.log"
    if path.exists() and path.stat().st_size > 1_000_000:
        path.replace(data_dir / "mediaforge.log.old")
    return path


def redirect_output_if_no_console(data_dir: Path) -> Path | None:
    """With pythonw (a double-clicked shortcut) there is no console: write to a log file."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    path = log_file(data_dir)
    stream = open(path, "a", encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stderr = stream
    return path


def alert(title: str, text: str) -> None:
    """Show a message when there is no console to print to. Windows only; otherwise print."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
            return
        except Exception:  # fall through to printing
            pass
    print(f"{title}: {text}", file=sys.stderr)
