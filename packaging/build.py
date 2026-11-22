"""Build the MediaForge app folder and zip it.

    python packaging/build.py

Needs: pip install -r backend/requirements.txt pyinstaller
Writes dist/MediaForge/ and dist/MediaForge-<version>-<system>.zip.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    from app import __version__
    from yt_dlp.version import __version__ as ytdlp_version

    (ROOT / "packaging" / "ytdlp_bundled.txt").write_text(
        ytdlp_version + "\n", encoding="utf-8"
    )
    dist = ROOT / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", str(dist), "--workpath", str(ROOT / "build"),
            str(ROOT / "packaging" / "mediaforge.spec"),
        ],
        check=True,
        cwd=ROOT,
    )  # fmt: skip
    system = "windows" if sys.platform == "win32" else sys.platform
    archive = shutil.make_archive(
        str(dist / f"MediaForge-{__version__}-{system}"), "zip", dist, "MediaForge"
    )
    print(f"Built {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
