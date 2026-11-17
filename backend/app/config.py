"""Runtime settings, overridable with environment variables."""

import os
from pathlib import Path

# Longest video (in seconds) that the URL converter will accept.
MAX_DURATION_SECONDS = int(os.getenv("MEDIAFORGE_MAX_DURATION", "3600"))

# Largest file (in megabytes) accepted by the upload converter.
MAX_UPLOAD_MB = int(os.getenv("MEDIAFORGE_MAX_UPLOAD_MB", "500"))

# Where the static frontend lives (repo_root/frontend by default).
FRONTEND_DIR = Path(
    os.getenv(
        "MEDIAFORGE_FRONTEND_DIR",
        Path(__file__).resolve().parents[2] / "frontend",
    )
)

# Where playlist downloads are saved (repo_root/downloads by default).
DOWNLOAD_DIR = Path(
    os.getenv(
        "MEDIAFORGE_DOWNLOAD_DIR",
        Path(__file__).resolve().parents[2] / "downloads",
    )
)

# Most videos accepted from one playlist.
MAX_PLAYLIST_ITEMS = int(os.getenv("MEDIAFORGE_MAX_PLAYLIST_ITEMS", "200"))

# Where MediaForge keeps its own small files: settings and the download history.
DATA_DIR = Path(
    os.getenv(
        "MEDIAFORGE_DATA_DIR",
        Path(__file__).resolve().parents[2] / "data",
    )
)
