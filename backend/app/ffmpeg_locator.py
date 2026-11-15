"""Find FFmpeg, even when this terminal's PATH is out of date.

Search order:
1. The folder named in the MEDIAFORGE_FFMPEG_DIR environment variable.
2. The PATH.
3. Folders where common installers put FFmpeg (WinGet, Chocolatey, C:\\ffmpeg).
"""

import os
import shutil
from pathlib import Path


def _configured_dir() -> str | None:
    value = os.environ.get("MEDIAFORGE_FFMPEG_DIR", "").strip().strip('"')
    return value or None


def known_install_dirs() -> list[Path]:
    """Folders where installers commonly place ffmpeg and ffprobe."""
    dirs: list[Path] = []

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget = Path(local_app_data) / "Microsoft" / "WinGet"
        dirs.append(winget / "Links")
        dirs.extend(sorted((winget / "Packages").glob("*FFmpeg*/**/bin")))

    program_data = os.environ.get("ProgramData")
    if program_data:
        dirs.append(Path(program_data) / "chocolatey" / "bin")

    dirs.append(Path("C:/ffmpeg/bin"))
    dirs.append(Path("C:/Program Files/ffmpeg/bin"))
    return dirs


def find_tool(name: str) -> str | None:
    """Return the full path of the tool `name` (for example "ffmpeg"), or None."""
    configured = _configured_dir()
    if configured:
        found = shutil.which(name, path=configured)
        if found:
            return found

    found = shutil.which(name)
    if found:
        return found

    for directory in known_install_dirs():
        found = shutil.which(name, path=str(directory))
        if found:
            return found
    return None


def ready() -> bool:
    """Merging, audio extraction and conversion only need ffmpeg itself."""
    return find_tool("ffmpeg") is not None


def ytdlp_location() -> str | None:
    """Folder containing ffmpeg, to hand to yt-dlp (None if ffmpeg isn't found)."""
    ffmpeg = find_tool("ffmpeg")
    return str(Path(ffmpeg).parent) if ffmpeg else None
