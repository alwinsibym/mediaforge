"""Click through the MediaForge page in a real browser and check that every screen still works.

    pip install playwright && python -m playwright install chromium
    python scripts/ui_smoke.py            # headless
    python scripts/ui_smoke.py --show     # watch it run

It starts the real server with the downloader and converter replaced by fakes, so it needs no
internet and no FFmpeg. It checks the page, not the sites: themes, tabs, preview, renaming,
errors, playlists, retry, settings, history, uploads, the phone layout and the access-token
login. Exit code 0 means every check passed. Run it after any change to the files in
frontend/.
"""

import argparse
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

_TMP = Path(tempfile.mkdtemp(prefix="mediaforge-ui-"))
os.environ["MEDIAFORGE_DOWNLOAD_DIR"] = str(_TMP / "downloads")
os.environ["MEDIAFORGE_DATA_DIR"] = str(_TMP / "data")

import uvicorn  # noqa: E402

from app import config, downloader, jobs, main, transcoder  # noqa: E402
from app.downloader import ConversionError  # noqa: E402

THUMB = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _fake_info(url):
    return {
        "title": "Test Song (Official Video)",
        "duration": 213,
        "uploader": "Test Channel",
        "thumbnail": None,
        "view_count": 1200,
        "upload_date": "20240101",
        "is_live": False,
        "thumbnails": [],
        "qualities": [
            {"id": "1080", "label": "1080p", "height": 1080, "fps": 30, "size": 90_000_000},
            {"id": "720", "label": "720p", "height": 720, "fps": 30, "size": None},
        ],
    }


def _fake_playlist(url):
    names = ["Song One", "Song Two", "Private one", "Song Four", "Song Five"]
    return {
        "title": "Road Trip Mix",
        "uploader": "me",
        "limit": 200,
        "entries": [
            {"index": i, "title": t, "url": f"https://example.com/v{i}", "duration": 200}
            for i, t in enumerate(names, 1)
        ],
    }


def _fake_download(
    url, fmt, quality, workdir, extra=None, notes=None, mute=False, progress=None, features=None
):
    for percent in (0.0, 50.0, 100.0):
        if progress:
            progress({"phase": "downloading", "percent": percent, "speed": 2e6, "eta": 1})
        time.sleep(0.1)
    if url.endswith("v3"):
        raise ConversionError("This video is private.")
    name = features.title if features and features.title else f"Song {url[-1]}"
    out = Path(workdir) / f"{name}.mp3"
    out.write_bytes(b"x" * 2048)
    return out


SEEN_TWEAKS = []


def _fake_convert(
    source,
    fmt,
    quality,
    workdir,
    mute=False,
    progress=None,
    normalize=False,
    tweaks=None,
    audio_file=None,
    subtitle_file=None,
    cover_file=None,
):
    SEEN_TWEAKS.append((fmt, tweaks, subtitle_file is not None))
    out = Path(workdir) / f"{Path(source).stem}.mp3"
    out.write_bytes(b"y" * 1024)
    return out


def _fake_sample(source, fmt, quality, workdir, *args, **kwargs):
    out = Path(workdir) / f"sample.{fmt}"
    out.write_bytes(b"z" * 2048)
    return {
        "path": out,
        "sample_seconds": 10.0,
        "sample_bytes": 2048,
        "estimated_bytes": 38 * 1024 * 1024,
        "estimated_seconds": 41.0,
        "whole_seconds": 240.0,
    }


def _start_server() -> int:
    downloader.fetch_info = _fake_info
    downloader.fetch_playlist = _fake_playlist
    downloader.download_and_convert = _fake_download
    downloader.download_thumbnail = lambda *a, **k: None
    transcoder.convert_file = _fake_convert
    transcoder.make_sample = _fake_sample
    transcoder.ffmpeg_available = lambda: True
    jobs.PACE_MIN = jobs.PACE_MAX = 0
    main._upgrade_ytdlp = lambda: {"before": "1", "after": "1", "changed": False}
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return port


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))
    print(
        f"{'PASS' if condition else 'FAIL'}  {name}"
        + (f"  ({detail})" if detail and not condition else "")
    )


def run(playwright, base: str, show: bool) -> None:
    browser = playwright.chromium.launch(headless=not show)
    page_errors: list[str] = []

    def new_page(width=1100, scheme="light", **kw):
        context = browser.new_context(
            viewport={"width": width, "height": 900},
            color_scheme=scheme,
            accept_downloads=True,
            **kw,
        )
        page = context.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        return page

    page = new_page()
    page.goto(base)
    page.wait_for_selector(".chip")
    check("page loads and lists formats", page.locator(".chip").count() >= 7)

    # theme
    page.click("[data-theme-choice=dark]")
    dark = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.click("[data-theme-choice=light]")
    light = page.evaluate("getComputedStyle(document.body).backgroundColor")
    check("theme switch changes the page", dark != light)
    page.reload()
    page.wait_for_selector(".chip")
    check(
        "theme choice survives a reload",
        page.get_attribute("[data-theme-choice=light]", "aria-checked") == "true",
    )

    # tabs and formats
    page.click("#tab-file")
    file_shown = page.is_visible("#panel-file")
    page.click("#tab-playlist")
    playlist_shown = page.is_visible("#panel-playlist")
    page.click("#tab-url")
    check("tabs switch panels", file_shown and playlist_shown and page.is_visible("#panel-url"))
    page.check("input[name=kind][value=video]")
    check("video kind shows video formats", "MP4" in page.inner_text("#format-chips"))
    page.check("input[name=kind][value=audio]")

    # preview, rename, download
    page.fill("#url-input", "https://example.com/watch?v=abc")
    page.wait_for_selector("#preview:not([hidden])")
    check("preview shows the title", "Test Song" in page.inner_text("#preview-title"))
    page.fill("#title-input", "My Road Song")
    bodies = []
    page.on(
        "request",
        lambda r: bodies.append(r.post_data or "") if r.url.endswith("/api/jobs") else None,
    )
    with page.expect_download(timeout=15000) as download:
        page.click("#submit-btn")
    check(
        "rename sent and used for the file",
        "My Road Song" in " ".join(bodies) and "My Road Song" in download.value.suggested_filename,
        download.value.suggested_filename,
    )
    page.wait_for_selector("#status:not(:empty)")
    check("done message appears", "Done" in page.inner_text("#status"))
    page.fill("#url-input", "https://example.com/watch?v=other")
    check("old result clears on a new link", page.inner_text("#status").strip() == "")

    # error card
    page.fill("#url-input", "https://example.com/v3")
    page.wait_for_selector("#preview:not([hidden])")
    page.click("#submit-btn")
    page.wait_for_selector(".err-card", timeout=15000)
    code = page.inner_text(".err-code")
    page.click(".err-more summary")
    page.wait_for_function(
        "document.querySelector('#status').innerText.includes('What to do now')", timeout=5000
    )
    check(
        "error card shows a code and an explanation",
        code.startswith("MF-") and "What to do now" in page.inner_text("#status"),
        code,
    )

    # playlist
    page.click("#tab-playlist")
    page.fill("#playlist-input", "https://example.com/playlist?list=1")
    page.click("#playlist-load")
    page.wait_for_selector("#playlist-box:not([hidden])")
    check("playlist lists its videos", page.locator("#playlist-list li").count() == 5)
    page.uncheck("#playlist-list li:nth-child(4) input")
    page.click("#submit-btn")
    page.wait_for_selector("#job-items li.is-failed", timeout=20000)
    page.wait_for_selector("#job-retry:not([hidden])", timeout=20000)
    states = page.locator("#job-items li").evaluate_all("els => els.map(e => e.className)")
    check(
        "playlist finishes with the private video failed",
        sum("is-done" in s for s in states) == 3 and sum("is-failed" in s for s in states) == 1,
        str(states),
    )
    check(
        "failed video has an expandable explanation",
        page.locator("#job-items .err-row").count() == 1,
    )
    page.click("#job-retry")
    page.wait_for_timeout(300)
    page.wait_for_selector("#job-cancel", state="hidden", timeout=20000)
    page.wait_for_selector("#job-retry:not([hidden])", timeout=20000)
    check("retry runs again without errors", page.locator("#job-items li").count() >= 1)

    # settings
    page.click("#settings-btn")
    page.wait_for_selector("#set-proxy")
    page.fill("#set-proxy", "bad")
    page.click("#settings-form button[type=submit]")
    page.wait_for_function("document.querySelector('#settings-status').textContent.length > 0")
    check(
        "bad proxy is refused with a message",
        "proxy" in page.inner_text("#settings-status").lower(),
    )
    page.fill("#set-proxy", "socks5://127.0.0.1:1080")
    page.click("#settings-form button[type=submit]")
    page.wait_for_selector("#settings-dialog", state="hidden")
    page.click("#settings-btn")
    page.wait_for_selector("#set-proxy")
    check(
        "settings are saved and reloaded",
        page.input_value("#set-proxy") == "socks5://127.0.0.1:1080",
    )
    page.fill("#set-proxy", "")
    page.click("#settings-form button[type=submit]")
    page.wait_for_selector("#settings-dialog", state="hidden")

    # history
    page.click("#history-btn")
    page.wait_for_selector("#history-dialog[open]")
    check("history lists finished downloads", page.locator("#history-list li").count() >= 1)
    page.keyboard.press("Escape")

    # upload
    page.click("#tab-file")
    sample = _TMP / "clip.wav"
    sample.write_bytes(b"RIFF....WAVEfmt ")
    page.set_input_files("#file-input", str(sample))
    page.fill("#file-title-input", "Renamed clip")
    try:
        with page.expect_download(timeout=15000) as upload:
            page.click("#submit-btn")
    except Exception:
        print(
            "DEBUG status:",
            page.inner_text("#status"),
            "| button:",
            page.inner_text("#submit-btn"),
            "| disabled:",
            page.is_disabled("#submit-btn"),
        )
        raise
    check(
        "file upload converts and downloads",
        upload.value.suggested_filename.endswith(".mp3"),
        upload.value.suggested_filename,
    )
    check(
        "uploaded file uses the new name",
        "Renamed clip" in upload.value.suggested_filename,
        upload.value.suggested_filename,
    )

    # tweaks on the File tab
    check("tweaks section is on the File tab", page.is_visible("#tweaks"))
    page.click("#tweaks summary")
    check(
        "audio output hides the video-only tweaks",
        not page.is_visible("#tw-codec-field") and not page.is_visible("#tw-animated-group"),
    )
    page.check("input[name=kind][value=video]")
    page.wait_for_selector("#tw-codec-field", state="visible")
    check(
        "video output shows codec, resize and GIF tweaks",
        page.is_visible("#tw-resize-field") and page.is_visible("#tw-animated-group"),
    )
    check(
        "codecs that do not fit the container are disabled",
        page.eval_on_selector('#tw-codec option[value="vp9"]', "o => o.disabled"),
    )
    page.select_option("#tw-resize", "480")
    page.fill("#tw-volume", "150")
    page.check("#tw-meta")
    srt = _TMP / "x.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
    page.set_input_files("#tw-subs-file", str(srt))
    check("subtitle mode appears once a file is chosen", page.is_visible("#tw-subs-mode"))
    check("cover picture field shows for MP4", page.is_visible("#tw-cover-field"))
    check("sample box is shown with a file chosen", page.is_enabled("#sample-btn"))
    page.click("#sample-btn")
    page.wait_for_selector("#sample-result:not([hidden])")
    estimate = page.inner_text("#sample-estimate")
    check("sample shows a size and time estimate", "38" in estimate and "MB" in estimate, estimate)
    check("sample shows a player", page.locator("#sample-player video").count() == 1)
    page.select_option("#tw-resize", "720")
    check(
        "changing a choice marks the sample as out of date",
        page.locator("#sample-result.is-stale").count() == 1,
    )
    SEEN_TWEAKS.clear()
    page.click("#submit-btn")
    for _ in range(100):
        if SEEN_TWEAKS:
            break
        time.sleep(0.1)
    seen = SEEN_TWEAKS[-1] if SEEN_TWEAKS else None
    tw = seen[1] if seen else None
    check(
        "tweaks reach the server",
        bool(tw)
        and tw.resize == 720
        and tw.volume == 150
        and tw.strip_metadata
        and tw.subtitles == "soft"
        and seen[2],
        repr(seen),
    )
    page.check("input[name=kind][value=audio]")

    # phone layout
    phone = new_page(width=375)
    phone.goto(base)
    phone.wait_for_selector(".chip")
    check(
        "phone layout has no sideways scrolling",
        not phone.evaluate("document.documentElement.scrollWidth > innerWidth"),
    )

    check("no JavaScript errors", not page_errors, "; ".join(page_errors))

    # access token login: pretend this computer is a remote device
    config.ACCESS_TOKEN = "letmein"
    main._LOCAL_CLIENTS.clear()
    remote = new_page()
    remote.goto(base)
    remote.wait_for_selector("#login-dialog[open]")
    check("remote device is asked for the token", True)
    remote.fill("#login-token", "wrong")
    remote.click("#login-form button[type=submit]")
    remote.wait_for_function("document.querySelector('#login-status').textContent.length > 0")
    check("wrong token is refused", "not correct" in remote.inner_text("#login-status"))
    remote.fill("#login-token", "letmein")
    remote.click("#login-form button[type=submit]")
    remote.wait_for_selector(".chip", timeout=10000)
    check("right token opens the app", remote.is_hidden("#login-dialog"))
    browser.close()


def main_cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--show", action="store_true", help="show the browser window")
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Install Playwright first:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )
        return 2
    port = _start_server()
    with sync_playwright() as playwright:
        run(playwright, f"http://127.0.0.1:{port}", args.show)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
