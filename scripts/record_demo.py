"""Record the README demo GIF: paste a link, pick a format, convert, download.

    python scripts/record_demo.py https://youtu.be/VIDEO_ID           # real download
    python scripts/record_demo.py --sample                            # fake data, no internet

Needs Playwright (python -m playwright install chromium) and FFmpeg. Writes docs/demo.gif
and docs/demo.mp4. Use a video you own or that is licensed for copying.
"""

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

_TMP = Path(tempfile.mkdtemp(prefix="mediaforge-demo-"))
os.environ.setdefault("MEDIAFORGE_DOWNLOAD_DIR", str(_TMP / "downloads"))
os.environ.setdefault("MEDIAFORGE_DATA_DIR", str(_TMP / "data"))

SIZE = {"width": 960, "height": 620}


def start_real_server() -> int:
    import uvicorn

    from app import main

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return port


def record(base: str, url: str, headless: bool) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        launch = {"headless": headless}
        chrome = Path("/usr/bin/google-chrome")
        if chrome.exists():
            launch.update(executable_path=str(chrome), args=["--no-sandbox"])
        browser = p.chromium.launch(**launch)
        context = browser.new_context(
            viewport=SIZE,
            record_video_dir=str(_TMP / "video"),
            record_video_size=SIZE,
            accept_downloads=True,
            color_scheme="light",
        )
        page = context.new_page()
        page.goto(base)
        page.wait_for_selector(".chip")
        page.wait_for_timeout(1200)
        page.click("#url-input")
        page.keyboard.type(url, delay=35)
        page.wait_for_selector("#preview:not([hidden])", timeout=60000)
        page.wait_for_timeout(1800)
        page.evaluate("window.scrollTo({top: 260, behavior: 'smooth'})")
        page.wait_for_timeout(1200)
        page.click("#format-chips .chip >> nth=0")
        page.wait_for_timeout(900)
        with page.expect_download(timeout=600000) as download:
            page.click("#submit-btn")
            page.wait_for_selector("#progress:not([hidden])", timeout=30000)
        download.value.save_as(_TMP / "result")
        page.wait_for_timeout(2500)
        video = page.video.path()
        context.close()
        browser.close()
    return Path(video)


def encode(video: Path, out_dir: Path) -> None:
    out_dir.mkdir(exist_ok=True)
    mp4 = out_dir / "demo.mp4"
    gif = out_dir / "demo.gif"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "26",
            "-movflags",
            "+faststart",
            str(mp4),
        ],
        check=True,
    )
    palette = _TMP / "palette.png"
    scale = "fps=10,scale=800:-1:flags=lanczos"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            f"{scale},palettegen=stats_mode=diff",
            str(palette),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-i",
            str(palette),
            "-lavfi",
            f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5",
            str(gif),
        ],
        check=True,
    )
    print(f"Wrote {gif} ({gif.stat().st_size // 1024} KB) and {mp4}")


def main_cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("url", nargs="?", help="a link to a video you may copy")
    parser.add_argument("--sample", action="store_true", help="use made-up data, no internet")
    parser.add_argument("--show", action="store_true", help="watch the browser")
    args = parser.parse_args()
    if args.sample:
        import ui_smoke

        port = ui_smoke._start_server()
        url = "https://www.youtube.com/watch?v=sample"
    elif args.url:
        port, url = start_real_server(), args.url
    else:
        parser.error("give a link, or use --sample")
    video = record(f"http://127.0.0.1:{port}", url, not args.show)
    encode(video, ROOT / "docs")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
