"""Make the promo video for the website: site/media/promo.mp4, poster.jpg and og.jpg.

    python scripts/make_promo.py

Opening, headlines and closing are small HTML pages in scripts/promo/. The app scenes show the
real MediaForge page, running here with made-up data (nothing is downloaded), inside a floating
window. A pointer is drawn on top. The pictures are filmed at 1920 x 1080, cut on the beats of
the score from scripts/make_score.py, dip through black between scenes, and the score is added.
Needs Playwright (python -m playwright install chromium), FFmpeg, numpy, scipy and Pillow.
"""

import asyncio
import base64
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import make_guide_images as guide  # noqa: E402
import make_score as score  # noqa: E402
from app import downloader  # noqa: E402

OUT = ROOT / "site" / "media"
PROMO = ROOT / "scripts" / "promo"
WORK = Path(tempfile.mkdtemp(prefix="mediaforge-promo-"))
W, H, FPS = 1920, 1080, 30
BEAT = score.BEAT
URL = guide.FAKE_URL
STAGE_BG = "05070f"

# Their lengths come from the beat numbers in make_score.py.
CARDS = {
    "what": ("~Meet MediaForge.", "A free converter for audio and video, on your own computer."),
}


def seconds(name):
    start = score.SCENES[name]
    later = [v for v in score.SCENES.values() if v > start]
    return ((min(later) if later else score.TOTAL_BEATS) - start) * BEAT


# A pointer, drawn inside every page that is filmed.
OVERLAY_JS = """
(() => {
  let cur, rip;
  const boot = () => {
    const css = document.createElement('style');
    css.textContent = `
      #mf-cursor{position:fixed;z-index:2147483647;left:0;top:0;width:30px;height:30px;pointer-events:none;
        transform:translate(-100px,-100px);filter:drop-shadow(0 3px 5px rgba(0,0,0,.4))}
      #mf-ripple{position:fixed;z-index:2147483646;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;
        border:3px solid #8a9bff;pointer-events:none;opacity:0}
      #mf-ripple.go{animation:mfr .55s ease-out}
      @keyframes mfr{from{opacity:.9;transform:scale(.6)}to{opacity:0;transform:scale(3.4)}}`;
    document.head.appendChild(css);
    if (window.top !== window) {
      // The app inside the floating window: hold its drifting background still, so the film stays smooth.
      const still = document.createElement('style');
      still.textContent = 'body::before,body::after,html::before{animation:none!important}*{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}';
      document.head.appendChild(still);
    }
    cur = document.createElement('div'); cur.id = 'mf-cursor';
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="30" height="30"><path d="M4 2l15 9-6.5 1.6L9.4 19z" fill="#fff" stroke="#171c2e" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    rip = document.createElement('div'); rip.id = 'mf-ripple';
    document.body.append(cur, rip);
    addEventListener('mousemove', (e) => { cur.style.transform = `translate(${e.clientX - 4}px,${e.clientY - 2}px)`; }, true);
    addEventListener('mousedown', (e) => {
      rip.style.left = e.clientX + 'px'; rip.style.top = e.clientY + 'px';
      rip.classList.remove('go'); void rip.offsetWidth; rip.classList.add('go');
    }, true);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', boot);
  else boot();
})();
"""
HIDE_CURSOR = "#mf-cursor{display:none!important}"


class Film:
    """Records a page as timed JPEG frames, then encodes one exact-length MP4 for the scene."""

    def __init__(self, page, name, length):
        self.page, self.name, self.length = page, name, length
        self.folder = WORK / name
        self.folder.mkdir()
        self.frames = []  # (timestamp, file)
        self.t0 = 0.0

    async def start(self):
        cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp = cdp

        async def on_frame(params):
            index = len(self.frames)
            path = self.folder / f"{index:05d}.jpg"
            path.write_bytes(base64.b64decode(params["data"]))
            self.frames.append((params["metadata"]["timestamp"], path))
            await cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

        cdp.on("Page.screencastFrame", lambda p: asyncio.ensure_future(on_frame(p)))
        await cdp.send(
            "Page.startScreencast",
            {"format": "jpeg", "quality": 85, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1},
        )
        await asyncio.sleep(0.3)
        await self.page.evaluate("document.body.classList.add('go')")
        self.t0 = time.time()

    def log(self, label):
        print(f"    {self.name} {time.time() - self.t0:5.2f}s  {label}")

    async def at(self, secs):
        """Wait until `secs` seconds after the scene's start."""
        delay = self.t0 + secs - time.time()
        if delay > 0:
            await asyncio.sleep(delay)

    async def stop(self, fade_in=0.4, fade_out=0.45, outro=True):
        if outro:  # the scene's words and pictures lift away just before the cut
            await self.at(self.length - 0.6)
            await self.page.evaluate("document.body.classList.add('out')")
        await self.at(self.length)
        await self.cdp.send("Page.stopScreencast")
        await asyncio.sleep(0.2)
        end = self.t0 + self.length
        before = [f for f in self.frames if f[0] <= self.t0]
        kept = ([(self.t0, before[-1][1])] if before else []) + [
            f for f in self.frames if self.t0 < f[0] < end
        ]
        lines = []
        for i, (t, path) in enumerate(kept):
            nxt = kept[i + 1][0] if i + 1 < len(kept) else end
            lines.append(f"file '{path}'\nduration {max(nxt - t, 0.001):.4f}")
        lines.append(f"file '{kept[-1][1]}'")
        listing = self.folder / "list.txt"
        listing.write_text("\n".join(lines))
        filters = [
            f"fps={FPS}",
            "format=yuv420p",
            f"fade=t=in:st=0:d={fade_in}:color=0x{STAGE_BG}",
            f"fade=t=out:st={self.length - fade_out:.3f}:d={fade_out}:color=0x{STAGE_BG}",
        ]
        target = WORK / f"{self.name}.mp4"
        temp = WORK / f"{self.name}.part.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-vf", ",".join(filters), "-t", f"{self.length:.4f}", "-c:v", "libx264", "-crf", "20",
             "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", str(temp)],
            check=True,
        )
        temp.rename(target)
        early = len([f for f in kept if f[0] < self.t0 + 1.5])
        print(f"scene {self.name}: {len(kept)} frames, {self.length:.2f}s ({early} in the first 1.5 s)")
        return target


async def glide(page, x, y, steps=10):
    await page.mouse.move(x, y, steps=steps)


async def centre(locator):
    box = await locator.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


async def click(page, locator, steps=10, pause=0.15):
    x, y = await centre(locator)
    await glide(page, x, y, steps=steps)
    await asyncio.sleep(0.1)
    await page.mouse.down()
    await asyncio.sleep(0.07)
    await page.mouse.up()
    await asyncio.sleep(pause)


def slow_download(url, fmt, quality, workdir, extra=None, notes=None, mute=False,
                  progress=None, features=None):
    """A stand-in download that takes a couple of seconds, so the progress bar can be seen."""
    for percent in range(0, 101, 5):
        if progress:
            progress({"phase": "downloading", "percent": float(percent), "speed": 3.1e6, "eta": 2})
        time.sleep(0.06)
    out = Path(workdir) / f"Sample Song (Official Video).{fmt}"
    out.write_bytes(b"x" * 2048)
    return out


async def open_page(browser, thumb, path, cursor=False):
    context = await browser.new_context(
        viewport={"width": W, "height": H}, color_scheme="dark", device_scale_factor=1
    )
    await context.add_init_script(OVERLAY_JS)
    await context.route("**/guide-thumb.png", lambda r: r.fulfill(body=thumb, content_type="image/png"))
    page = await context.new_page()
    await page.goto(path)
    if not cursor:
        await page.add_style_tag(content=HIDE_CURSOR)
    return context, page


def card_url(name):
    from urllib.parse import quote

    title, sub = CARDS[name]
    return (PROMO / "card.html").as_uri() + f"?t={quote(title)}&s={quote(sub)}"


async def show_for_setup(page):
    """Show the stage while the scene is being set up (the page needs to be visible to click)."""
    await page.evaluate("document.body.classList.add('go')")
    await asyncio.sleep(2.2)


async def hide_after_setup(page):
    """Back to the hidden start, so the window rises into view when the film starts."""
    await page.evaluate("document.body.classList.remove('go')")
    await asyncio.sleep(0.3)


async def silent_preview(frame):
    """Fill the link and press Preview without anyone watching, so a scene can start from there."""
    await frame.locator("#url-input").fill(URL)
    await frame.locator("#preview-btn").click()
    await frame.locator("#preview:not([hidden])").wait_for()
    await asyncio.sleep(0.5)


async def make_scenes(base):
    from playwright.async_api import async_playwright

    thumb = guide._thumbnail()
    stage = (PROMO / "stage.html").as_uri() + f"?app={base}"
    scenes = []

    async def static(browser, name, path, outro=True):
        context, page = await open_page(browser, thumb, path)
        film = Film(page, name, seconds(name))
        await film.start()
        scenes.append(await film.stop(outro=outro))
        await context.close()

    page_of = lambda name: (PROMO / f"{name}.html").as_uri()  # noqa: E731

    async with async_playwright() as p:
        browser = await p.chromium.launch()

        await static(browser, "intro", page_of("intro"), outro=False)
        await static(browser, "what", card_url("what"))
        await static(browser, "pipe", page_of("pipe"))

        # The real page: paste a link, preview it, pick a format, convert.
        context, page = await open_page(browser, thumb, stage)
        app = page.frame_locator("#f1")
        await app.locator(".chip").first.wait_for()
        await asyncio.sleep(1.0)
        film = Film(page, "demo", seconds("demo"))
        await film.start()
        await film.at(1.5)
        await click(page, app.locator("#url-input"))
        await page.keyboard.type(URL, delay=22)
        film.log("typed")
        await film.at(3.2)
        await click(page, app.locator("#preview-btn"))
        await app.locator("#preview:not([hidden])").wait_for()
        film.log("preview shown")
        await film.at(4.3)
        await app.locator("#format-chips").evaluate("e => e.scrollIntoView({block:'center', behavior:'smooth'})")
        await film.at(5.2)
        await click(page, app.locator("#format-chips .chip").nth(3))
        film.log("format chosen")
        await film.at(5.9)
        await app.locator("#submit-btn").evaluate("e => e.scrollIntoView({block:'center', behavior:'smooth'})")
        await film.at(6.6)
        await click(page, app.locator("#submit-btn"), pause=0.1)
        film.log("convert clicked")
        await app.locator("#status.is-success").wait_for(timeout=20000)
        film.log("success")
        scenes.append(await film.stop())
        await context.close()

        await static(browser, "tweaks", page_of("tiles"))
        await static(browser, "spatial", page_of("spatial"))
        await static(browser, "local", page_of("local"))

        # Desktop, tablet and phone, side by side.
        context, page = await open_page(browser, thumb, stage + "&mode=devices")
        await show_for_setup(page)
        for frame_id in ("#f1", "#f2"):
            frame = page.frame_locator(frame_id)
            await frame.locator(".chip").first.wait_for()
            await silent_preview(frame)
        for handle in page.frames[1:3]:
            await handle.evaluate(
                "css => document.head.append(Object.assign(document.createElement('style'), {textContent: css}))",
                HIDE_CURSOR,
            )
        phone = page.frame_locator("#f3")
        await phone.locator(".chip").first.wait_for()
        await hide_after_setup(page)
        film = Film(page, "phone", seconds("phone"))
        await film.start()
        await film.at(1.6)
        await click(page, phone.locator("#url-input"))
        await page.keyboard.type(URL, delay=12)
        film.log("typed")
        await film.at(2.9)
        await click(page, phone.locator("#preview-btn"))
        film.log("preview clicked")
        scenes.append(await film.stop())
        await context.close()

        await static(browser, "get", page_of("get"))
        await static(browser, "end", page_of("end"), outro=False)
        await browser.close()
    return scenes


def join(scenes):
    OUT.mkdir(parents=True, exist_ok=True)
    listing = WORK / "scenes.txt"
    listing.write_text("".join(f"file '{s}'\n" for s in scenes))
    silent = WORK / "silent.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", str(silent)],
        check=True,
    )
    wav = WORK / "score.wav"
    from scipy.io import wavfile

    import numpy as np

    wavfile.write(wav, score.SR, (score.compose() * 32767).astype(np.int16))
    temp = OUT / "promo.part.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-af", "loudnorm=I=-18:TP=-2:LRA=7", "-c:a", "aac", "-b:a", "192k",
         "-ar", "44100", "-shortest", "-movflags", "+faststart", str(temp)],
        check=True,
    )
    temp.rename(OUT / "promo.mp4")
    # Poster and share image: the opening, once the name and the line are both on screen.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", "3.9", "-i", str(OUT / "promo.mp4"), "-frames:v", "1",
         "-vf", "scale=1280:-1", "-q:v", "3", str(OUT / "poster.jpg")],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", "3.9", "-i", str(OUT / "promo.mp4"), "-frames:v", "1",
         "-vf", "scale=1200:-1,crop=1200:630", "-q:v", "3", str(OUT / "og.jpg")],
        check=True,
    )


def stamp():
    """Put each media file's content hash into the page's links (media/promo.mp4?v=abcd1234).

    The server tells browsers to keep media files for a year, so a changed file needs a new
    address, or visitors keep seeing the old one. Run again whenever a media file changes.
    """
    import hashlib
    import re

    page = ROOT / "site" / "index.html"
    html = page.read_text(encoding="utf-8")
    for name in ("promo.mp4", "poster.jpg", "og.jpg"):
        digest = hashlib.md5((OUT / name).read_bytes()).hexdigest()[:8]
        html = re.sub(rf"media/{re.escape(name)}(\?v=[0-9a-f]+)?", f"media/{name}?v={digest}", html)
    page.write_text(html, encoding="utf-8")
    print("stamped media links in site/index.html")


if __name__ == "__main__":
    if "--stamp-only" in sys.argv:
        stamp()
        sys.exit(0)
    port = guide.start_server()
    downloader.download_and_convert = slow_download
    scenes = asyncio.run(make_scenes(f"http://127.0.0.1:{port}"))
    join(scenes)
    stamp()
    print("wrote", (OUT / "promo.mp4").relative_to(ROOT))
