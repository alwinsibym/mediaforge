"""Runtime settings, overridable with environment variables."""

import os
from pathlib import Path

# Longest video (in seconds) that the URL converter will accept. 0 means no limit.
MAX_DURATION_SECONDS = int(os.getenv("MEDIAFORGE_MAX_DURATION", "0"))

# Largest file (in megabytes) accepted by the upload converter. 0 means no limit.
MAX_UPLOAD_MB = int(os.getenv("MEDIAFORGE_MAX_UPLOAD_MB", "0"))

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

# Set to 1 only when every client that can reach the server is trusted (the Docker setup binds
# the port to this computer). Settings, history and updates are otherwise limited to loopback.
TRUST_ALL_CLIENTS = os.getenv("MEDIAFORGE_TRUST_CLIENTS") == "1"

# Jobs that may be waiting or running at once. Jobs run one after another, so extra requests
# only queue up and use disk space.
MAX_ACTIVE_JOBS = int(os.getenv("MEDIAFORGE_MAX_ACTIVE_JOBS", "5"))

# Set to 1 to allow links to addresses inside your own network (127.0.0.1, 192.168.x.x ...).
ALLOW_PRIVATE_URLS = os.getenv("MEDIAFORGE_ALLOW_PRIVATE") == "1"

# An access token. When set, every device except this computer must enter it first.
ACCESS_TOKEN = os.getenv("MEDIAFORGE_TOKEN", "")
