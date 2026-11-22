"""Make the screenshots for docs/INSTALL.md from the running page, with made-up data.

    python scripts/make_guide_images.py          # numbered pictures for docs/INSTALL.md
    python scripts/make_guide_images.py --site   # clean pictures (no numbers) for the website

Nothing is downloaded and no real file or link appears: the page talks to a stand-in for the
downloader and FFmpeg. Needs Playwright (python -m playwright install chromium) and Pillow.
Writes docs/guide/*.png.
"""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
_TMP = Path(tempfile.mkdtemp(prefix="mediaforge-guide-"))
os.environ["MEDIAFORGE_DOWNLOAD_DIR"] = str(_TMP / "downloads")
os.environ["MEDIAFORGE_DATA_DIR"] = str(_TMP / "data")

import uvicorn
from app import downloader, jobs, main, transcoder
from app import tweaks as tweaks_module
from PIL import Image, ImageDraw

SITE = "--site" in sys.argv
OUT = ROOT / "site" / "img" if SITE else ROOT / "docs" / "guide"
AMBER = "#f59e0b"
FAKE_URL = "https://www.example.com/watch?v=sample-song"


def _thumbnail() -> bytes:
    """A plain gradient with a play triangle, so no real picture is shown."""
    image = Image.new("RGB", (640, 360))
    draw = ImageDraw.Draw(image)
    for y in range(360):
        draw.line([(0, y), (640, y)], fill=(40 + y // 6, 60 + y // 5, 150 + y // 4))
    draw.polygon([(270, 130), (270, 230), (370, 180)], fill=(255, 255, 255))
    import io

    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _fake_info(url):
    return {
        "title": "Sample Song (Official Video)",
        "duration": 213,
        "uploader": "Sample Channel",
        "thumbnail": "/guide-thumb.png",
        "view_count": 1_200_000,
        "upload_date": "20240101",
        "is_live": False,
        "thumbnails": [],
        "qualities": [
            {
                "id": "1080",
                "label": "1080p",
                "height": 1080,
                "fps": 30,
                "size": 90_000_000,
            },
            {
                "id": "720",
                "label": "720p",
                "height": 720,
                "fps": 30,
                "size": 48_000_000,
            },
        ],
    }


def _fake_download(
    url,
    fmt,
    quality,
    workdir,
    extra=None,
    notes=None,
    mute=False,
    progress=None,
    features=None,
):
    for percent in (0.0, 40.0, 100.0):
        if progress:
            progress(
                {"phase": "downloading", "percent": percent, "speed": 2e6, "eta": 1}
            )
        time.sleep(0.15)
    out = Path(workdir) / f"Sample Song (Official Video).{fmt}"
    out.write_bytes(b"x" * 2048)
    return out


def _fake_probe(path):
    return {
        "duration": 212.0,
        "bitrate_kbps": 5200,
        "video": [{"codec": "h264", "width": 1920, "height": 1080, "fps": 30.0}],
        "audio": [{"codec": "aac", "channels": "stereo", "sample_rate": 48000}],
        "subtitles": [],
        "metadata": True,
    }


def _fake_sample(source, fmt, quality, workdir, *args, **kwargs):
    out = Path(workdir) / f"sample.{fmt}"
    out.write_bytes(b"z" * 2048)
    return {
        "path": out,
        "sample_seconds": 10.0,
        "sample_bytes": 2048,
        "estimated_bytes": 38 * 1024 * 1024,
        "estimated_seconds": 41.0,
        "whole_seconds": 212.0,
    }


def start_server() -> int:
    downloader.fetch_info = _fake_info
    downloader.download_and_convert = _fake_download
    transcoder.convert_file = lambda source, fmt, quality, workdir, *a, **k: (
        _fake_download("", fmt, quality, workdir)
    )
    transcoder.make_sample = _fake_sample
    transcoder.probe = _fake_probe
    transcoder.ffmpeg_available = lambda: True
    real_caps = tweaks_module.capabilities

    def all_on():
        caps = dict(real_caps())
        caps["spatial"] = {name: True for name in tweaks_module.spatial_mod.PRESETS}
        return caps

    tweaks_module.capabilities = all_on
    jobs.PACE_MIN = jobs.PACE_MAX = 0
    main._upgrade_ytdlp = lambda: {
        "before": "2025.1.1",
        "after": "2025.1.1",
        "changed": False,
    }
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return port


MARK_JS = """
([items]) => {
  document.querySelectorAll('.guide-mark').forEach((e) => e.remove());
  document.querySelectorAll('[data-guide-ring]').forEach((e) => {
    e.style.outline = ''; e.style.outlineOffset = ''; e.removeAttribute('data-guide-ring');
  });
  for (const [selector, number] of items) {
    const el = document.querySelector(selector);
    if (!el) throw new Error('missing ' + selector);
    el.style.outline = '3px solid %s';
    el.style.outlineOffset = '3px';
    el.setAttribute('data-guide-ring', '1');
    const r = el.getBoundingClientRect();
    const dot = document.createElement('div');
    dot.className = 'guide-mark';
    dot.textContent = number;
    dot.style.cssText = 'position:absolute;z-index:99999;width:30px;height:30px;border-radius:50%%;' +
      'background:%s;color:#1b1300;font:700 16px Inter,system-ui,sans-serif;display:flex;' +
      'align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.35);' +
      'left:' + (window.scrollX + r.left - 12) + 'px;top:' + (window.scrollY + r.top - 14) + 'px';
    const host = el.closest('dialog');
    if (host) {
      const h = host.getBoundingClientRect();
      dot.style.left = (r.left - h.left - 12 + host.scrollLeft) + 'px';
      dot.style.top = (r.top - h.top - 14 + host.scrollTop) + 'px';
      host.appendChild(dot);
    } else {
      document.body.appendChild(dot);
    }
  }
}
""" % (AMBER, AMBER)


def shot(page, name, selector=None, pad=24, items=(), clip_to=None, header=False):
    page.evaluate("window.scrollTo(0, 0)")
    page.evaluate(
        "(show) => { document.documentElement.style.setProperty('--guide-header', show ? 'visible' : 'hidden');"
        "document.querySelector('.site-header').style.visibility = show ? '' : 'hidden'; }",
        header,
    )
    page.evaluate(MARK_JS, [[] if SITE else list(items)])
    page.wait_for_timeout(450)
    path = OUT / f"{name}.png"
    if selector:
        box = page.locator(selector).bounding_box()
        page.screenshot(
            path=path,
            clip={
                "x": max(box["x"] - pad, 0),
                "y": box["y"] - pad,
                "width": box["width"] + pad * 2,
                "height": box["height"] + pad * 2,
            },
        )
    else:
        height = clip_to or page.viewport_size["height"]
        page.screenshot(
            path=path,
            clip={
                "x": 0,
                "y": 0,
                "width": page.viewport_size["width"],
                "height": height,
            },
        )
    print("wrote", path.relative_to(ROOT))


def main_run(base: str) -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    png = _thumbnail()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1100, "height": 1700},
            device_scale_factor=2,
            color_scheme="light",
        )
        page = context.new_page()
        page.route(
            "**/guide-thumb.png",
            lambda r: r.fulfill(body=png, content_type="image/png"),
        )
        page.goto(base)
        page.wait_for_selector(".chip")
        page.wait_for_timeout(1500)
        page.evaluate("document.getElementById('settings-btn').hidden = false")

        shot(
            page,
            "01-home",
            header=True,
            clip_to=820,
            items=[("#url-input", 1), ("#tab-file", 2), ("#settings-btn", 3)],
        )

        page.fill("#url-input", FAKE_URL)
        page.click("#preview-btn")
        page.wait_for_selector("#preview:not([hidden])")
        page.wait_for_timeout(600)
        shot(
            page,
            "02-paste-link",
            ".converter",
            items=[("#url-input", 1), ("#preview-btn", 2)],
        )

        page.click(".type-toggle .segment >> nth=0")
        page.click("#format-chips .chip >> nth=0")
        shot(
            page,
            "03-choose-format",
            ".choices",
            items=[(".type-toggle", 1), ("#format-chips", 2), ("#quality-select", 3)],
        )

        page.click("#submit-btn")
        page.wait_for_selector("#status.is-success", timeout=15000)
        page.wait_for_timeout(900)
        shot(page, "04-done", "#status", pad=50, items=[("#status", 1)])

        page.evaluate("window.scrollTo(0, 0)")
        page.click("#tab-file")
        page.set_input_files(
            "#file-input",
            {
                "name": "Holiday-clip.mp4",
                "mimeType": "video/mp4",
                "buffer": b"\x00" * 4096,
            },
        )
        page.wait_for_timeout(600)
        shot(
            page,
            "05-choose-file",
            "#panel-file",
            items=[("#dropzone", 1), ("#tw-info-btn", 2)],
        )

        page.click("#tweaks > summary")
        page.wait_for_timeout(700)
        page.select_option("#tw-spatial", "orbit")
        page.fill("#tw-spatial-speed", "8")
        page.wait_for_timeout(400)
        shot(
            page,
            "06-tweaks",
            "#tweaks",
            items=[("#tw-spatial", 1), ("#tw-spatial-speed", 2)],
        )

        page.set_viewport_size({"width": 1100, "height": 1500})
        page.evaluate("document.getElementById('settings-btn').click()")
        page.wait_for_timeout(900)
        page.evaluate(MARK_JS, [[] if SITE else [("#ytdlp-update", 1)]])
        page.locator("#settings-dialog").scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        page.locator("#settings-dialog").screenshot(path=OUT / "07-settings.png")
        print("wrote", (OUT / "07-settings.png").relative_to(ROOT))
        page.keyboard.press("Escape")

        phone = browser.new_context(
            viewport={"width": 390, "height": 900},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        ).new_page()
        phone.route(
            "**/guide-thumb.png",
            lambda r: r.fulfill(body=png, content_type="image/png"),
        )
        phone.goto(base)
        phone.wait_for_selector(".chip")
        phone.wait_for_timeout(1500)
        phone.fill("#url-input", FAKE_URL)
        phone.click("#preview-btn")
        phone.wait_for_selector("#preview:not([hidden])")
        phone.wait_for_timeout(600)
        shot(phone, "08-phone", header=True, clip_to=900)
        browser.close()


def to_webp() -> None:
    """For the website: keep four pictures as small WebP files and drop the rest."""
    keep = {
        "01-home": ("home", 1400),
        "02-paste-link": ("paste-link", 1400),
        "06-tweaks": ("tweaks", 1200),
        "08-phone": ("phone", 520),
    }
    for png in OUT.glob("*.png"):
        if png.stem in keep:
            name, width = keep[png.stem]
            image = Image.open(png).convert("RGB")
            if image.width > width:
                image = image.resize(
                    (width, round(image.height * width / image.width)), Image.LANCZOS
                )
            image.save(OUT / f"{name}.webp", "WEBP", quality=86)
        png.unlink()


if __name__ == "__main__":
    port = start_server()
    main_run(f"http://127.0.0.1:{port}")
    if SITE:
        to_webp()
