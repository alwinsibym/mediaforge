"""Where MediaForge finds its own files, as a normal Python program and as the Windows app.

The Windows app is built with PyInstaller. It has no pip and no Python to run it, so three things
differ: the page and data files live inside the app's bundle, the user's files (settings, history,
downloads) sit in folders next to the program, and yt-dlp updates are unpacked into a folder that
is put in front of the copy inside the bundle.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

_REPO = Path(__file__).resolve().parents[2]


def bundle_dir() -> Path:
    """Folder holding the page and data files the program was built with."""
    return Path(getattr(sys, "_MEIPASS", _REPO))


def app_dir() -> Path:
    """Folder the user sees: the one with the program (or the project, when run from source)."""
    return Path(sys.executable).resolve().parent if FROZEN else _REPO


def data_dir() -> Path:
    override = os.getenv("MEDIAFORGE_DATA_DIR")
    return Path(override) if override else app_dir() / "data"


def updates_dir() -> Path:
    """Where downloaded yt-dlp updates are unpacked (the Windows app only)."""
    return data_dir() / "updates"


def version_tuple(text: str) -> tuple[int, ...]:
    """'2025.11.12' -> (2025, 11, 12). Anything that is not a number is ignored."""
    return tuple(int(part) for part in re.findall(r"\d+", text)[:4])


def bundled_ytdlp_version() -> str | None:
    """The yt-dlp version the app was built with, written to a file at build time."""
    try:
        return (bundle_dir() / "ytdlp_bundled.txt").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def updated_ytdlp_version(folder: Path) -> str | None:
    """The version of an unpacked yt-dlp update, read from its version.py."""
    try:
        text = (folder / "yt_dlp" / "version.py").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", text)
    return match.group(1) if match else None


def _forget_modules(*prefixes: str) -> None:
    for name in list(sys.modules):
        if any(name == p or name.startswith(p + ".") for p in prefixes):
            del sys.modules[name]


def use_updated_packages() -> None:
    """Prefer a newer yt-dlp that the user downloaded over the one inside the app.

    A newer copy in the updates folder is put first on the import path. An update that is older
    than the bundled copy (the app itself was updated since) is deleted. An update that fails to
    import is deleted too, so a bad download can never stop the app from starting.
    """
    if not FROZEN:
        return
    folder = updates_dir()
    if not folder.is_dir():
        return
    newer = updated_ytdlp_version(folder)
    bundled = bundled_ytdlp_version()
    if not newer or (bundled and version_tuple(newer) <= version_tuple(bundled)):
        shutil.rmtree(folder, ignore_errors=True)
        return
    sys.path.insert(0, str(folder))
    try:
        import yt_dlp  # noqa: F401

        _forget_modules("yt_dlp")
        import yt_dlp.version  # noqa: F401
    except Exception as exc:  # a broken update must not stop the app
        print(f"The downloaded yt-dlp update could not be used and was removed: {exc}")
        sys.path.remove(str(folder))
        _forget_modules("yt_dlp", "yt_dlp_ejs")
        shutil.rmtree(folder, ignore_errors=True)
