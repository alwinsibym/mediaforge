"""Make the promo video for the website: site/media/promo.mp4 and site/media/poster.jpg.

    python scripts/make_promo.py

The scenes are filmed from the real page with made-up data (no internet, nothing is downloaded),
the same way scripts/make_guide_images.py works. A caption bar and a mouse pointer are drawn on
top. Needs Playwright (python -m playwright install chromium), FFmpeg and Pillow.
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

import make_guide_images as guide
from app import downloader

OUT = ROOT / "site" / "media"
PROMO = ROOT / "scripts" / "promo"
WORK = Path(tempfile.mkdtemp(prefix="mediaforge-promo-"))
W, H, FPS = 1280, 720, 30
URL = guide.FAKE_URL

# A pointer and a caption bar, drawn inside every page that is filmed.
OVERLAY_JS = """
(() => {
  let cur, rip, cap;
  window.__cap = (text) => {
    if (!cap) return;
    cap.classList.remove('on');
    if (!text) return;
    setTimeout(() => { cap.textContent = text; cap.classList.add('on'); }, 220);
  };
  const boot = () => {
    const css = document.createElement('style');
    css.textContent = `
      #mf-cursor{position:fixed;z-index:2147483647;left:0;top:0;width:26px;height:26px;pointer-events:none;
        transform:translate(-100px,-100px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
      #mf-ripple{position:fixed;z-index:2147483646;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
        border:3px solid #2d45e6;pointer-events:none;opacity:0}
      #mf-ripple.go{animation:mfr .5s ease-out}
      @keyframes mfr{from{opacity:.9;transform:scale(.6)}to{opacity:0;transform:scale(3.2)}}
      #mf-cap{position:fixed;z-index:2147483647;left:50%;bottom:34px;transform:translate(-50%,14px);opacity:0;
        padding:14px 26px;border-radius:16px;background:rgba(13,17,32,.86);color:#fff;
        font:600 26px/1.2 Archivo,"Segoe UI",system-ui,sans-serif;letter-spacing:-.01em;white-space:nowrap;
        transition:opacity .35s,transform .35s;box-shadow:0 12px 30px -10px rgba(0,0,0,.5)}
      #mf-cap.on{opacity:1;transform:translate(-50%,0)}`;
    document.head.appendChild(css);
    cur = document.createElement('div'); cur.id = 'mf-cursor';
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l15 9-6.5 1.6L9.4 19z" fill="#fff" stroke="#171c2e" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    rip = document.createElement('div'); rip.id = 'mf-ripple';
    cap = document.createElement('div'); cap.id = 'mf-cap';
    document.body.append(cur, rip, cap);
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


class Film:
    """Records a page as a list of timed JPEG frames, then encodes one MP4 for the scene."""

    def __init__(self, page, name):
        self.page, self.name = page, name
        self.frames = []
        self.cdp = None

    async def start(self):
        self.cdp = await self.page.context.new_cdp_session(self.page)

        async def on_frame(params):
            self.frames.append(
                (params["metadata"]["timestamp"], base64.b64decode(params["data"]))
            )
            await self.cdp.send(
                "Page.screencastFrameAck", {"sessionId": params["sessionId"]}
            )

        self.cdp.on(
            "Page.screencastFrame", lambda p: asyncio.ensure_future(on_frame(p))
        )
        await self.cdp.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 92,
                "maxWidth": W,
                "maxHeight": H,
                "everyNthFrame": 1,
            },
        )

    async def stop(self, fade_in=0.0, fade_out=0.0):
        end = time.time()
        await self.cdp.send("Page.stopScreencast")
        await asyncio.sleep(0.2)
        folder = WORK / self.name
        folder.mkdir()
        lines = []
        for i, (t, data) in enumerate(self.frames):
            (folder / f"{i:05d}.jpg").write_bytes(data)
            nxt = (
                self.frames[i + 1][0]
                if i + 1 < len(self.frames)
                else max(end, t + 0.04)
            )
            lines.append(
                f"file '{folder / f'{i:05d}.jpg'}'\nduration {max(nxt - t, 0.001):.4f}"
            )
        lines.append(f"file '{folder / f'{len(self.frames) - 1:05d}.jpg'}'")
        listing = folder / "list.txt"
        listing.write_text("\n".join(lines))
        seconds = self.frames[-1][0] - self.frames[0][0] + 0.04
        filters = [f"fps={FPS}", f"scale={W}:{H}:flags=lanczos", "format=yuv420p"]
        if fade_in:
            filters.append(f"fade=t=in:st=0:d={fade_in}:color=0d1120")
        if fade_out:
            filters.append(
                f"fade=t=out:st={max(seconds - fade_out, 0):.2f}:d={fade_out}:color=0d1120"
            )
        target = WORK / f"{self.name}.mp4"
        temp = WORK / f"{self.name}.part.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-vf",
                ",".join(filters),
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(FPS),
                "-an",
                str(temp),
            ],
            check=True,
        )
        temp.rename(target)
        print(f"scene {self.name}: {len(self.frames)} frames, {seconds:.1f}s")
        return target


async def glide(page, x, y, steps=28, pause=0.0):
    await page.mouse.move(x, y, steps=steps)
    if pause:
        await asyncio.sleep(pause)


async def centre(locator):
    box = await locator.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


async def click(page, locator, steps=16, pause=0.25):
    x, y = await centre(locator)
    await glide(page, x, y, steps=steps, pause=0.1)
    await page.mouse.down()
    await asyncio.sleep(0.08)
    await page.mouse.up()
    await asyncio.sleep(pause)


async def caption(page, text, hold):
    await page.evaluate("(t) => window.__cap(t)", text)
    await asyncio.sleep(hold)


def slow_download(
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
    """A stand-in download that takes a few seconds, so the progress bar is visible."""
    for percent in range(0, 101, 5):
        if progress:
            progress(
                {
                    "phase": "downloading",
                    "percent": float(percent),
                    "speed": 3.1e6,
                    "eta": 2,
                }
            )
        time.sleep(0.11)
    out = Path(workdir) / f"Sample Song (Official Video).{fmt}"
    out.write_bytes(b"x" * 2048)
    return out


async def scene_page(browser, base, thumb, scheme="light", path=None, cursor=True):
    context = await browser.new_context(
        viewport={"width": W, "height": H}, color_scheme=scheme, device_scale_factor=1
    )
    await context.add_init_script(OVERLAY_JS)
    await context.route(
        "**/guide-thumb.png", lambda r: r.fulfill(body=thumb, content_type="image/png")
    )
    page = await context.new_page()
    await page.goto(path or base)
    if not cursor:
        await page.add_style_tag(content="#mf-cursor{display:none!important}")
    return context, page


async def make_scenes(base):
    from playwright.async_api import async_playwright

    thumb = guide._thumbnail()
    scenes = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # 1. Title card.
        context, page = await scene_page(
            browser, base, thumb, "dark", (PROMO / "title.html").as_uri(), cursor=False
        )
        film = Film(page, "1-title")
        await film.start()
        await asyncio.sleep(3.6)
        scenes.append(await film.stop(fade_out=0.3))
        await context.close()

        # 2. Paste a link, preview, pick MP3, convert.
        context, page = await scene_page(browser, base, thumb)
        await page.wait_for_selector(".chip")
        await page.evaluate("document.querySelector('.site-header').scrollIntoView()")
        await page.wait_for_timeout(600)
        film = Film(page, "2-convert")
        await film.start()
        await asyncio.sleep(0.6)
        await caption(page, "Paste a link", 0.3)
        await click(page, page.locator("#url-input"))
        await page.keyboard.type(URL, delay=38)
        await asyncio.sleep(0.4)
        await click(page, page.locator("#preview-btn"))
        await page.wait_for_selector("#preview:not([hidden])")
        await page.evaluate("window.scrollTo({top: 250, behavior: 'smooth'})")
        await asyncio.sleep(0.9)
        await caption(page, "Choose a format", 0.3)
        await click(page, page.locator("#format-chips .chip").nth(0))
        await asyncio.sleep(0.6)
        await page.evaluate("window.scrollTo({top: 560, behavior: 'smooth'})")
        await asyncio.sleep(0.8)
        await caption(page, "Convert and download", 0.3)
        await click(page, page.locator("#submit-btn"), pause=0.2)
        await page.wait_for_selector("#status.is-success", timeout=20000)
        await asyncio.sleep(1.6)
        scenes.append(await film.stop(fade_in=0.3, fade_out=0.25))
        await context.close()

        # 3. A local file, and the spatial sound tweak.
        context, page = await scene_page(browser, base, thumb)
        await page.wait_for_selector(".chip")
        await page.wait_for_timeout(1200)
        film = Film(page, "3-tweaks")
        await film.start()
        await asyncio.sleep(0.5)
        await caption(page, "Or choose a file from your computer", 0.2)
        await click(page, page.locator("#tab-file"))
        await page.set_input_files(
            "#file-input",
            {
                "name": "Holiday-clip.mp4",
                "mimeType": "video/mp4",
                "buffer": b"\x00" * 4096,
            },
        )
        await asyncio.sleep(0.6)
        await page.evaluate("window.scrollTo({top: 420, behavior: 'smooth'})")
        await asyncio.sleep(0.8)
        await click(page, page.locator("#tweaks > summary"))
        await page.evaluate(
            "document.querySelector('#tw-spatial').scrollIntoView({block:'center', behavior:'smooth'})"
        )
        await asyncio.sleep(0.9)
        await caption(page, "Tweak the sound, even spatial audio for headphones", 0.3)
        await click(page, page.locator("#tw-spatial"), pause=0.2)
        await page.select_option("#tw-spatial", "orbit")
        await asyncio.sleep(1.5)
        scenes.append(await film.stop(fade_in=0.3, fade_out=0.25))
        await context.close()

        # 4. The phone, in the dark theme.
        context, page = await scene_page(
            browser,
            base,
            thumb,
            "dark",
            (PROMO / "phone.html").as_uri() + f"?app={base}",
            cursor=False,
        )
        frame = page.frame_locator("#app")
        await frame.locator(".chip").first.wait_for()
        await asyncio.sleep(1.4)
        film = Film(page, "4-phone")
        await film.start()
        await asyncio.sleep(0.5)
        await click(page, frame.locator("#url-input"))
        await page.keyboard.type(URL, delay=34)
        await click(page, frame.locator("#preview-btn"))
        await frame.locator("#preview:not([hidden])").wait_for()
        await asyncio.sleep(0.8)
        await page.mouse.wheel(0, 330)
        await asyncio.sleep(2.0)
        scenes.append(await film.stop(fade_in=0.3, fade_out=0.25))
        await context.close()

        # 5. End card.
        context, page = await scene_page(
            browser, base, thumb, "dark", (PROMO / "end.html").as_uri(), cursor=False
        )
        film = Film(page, "5-end")
        await film.start()
        await asyncio.sleep(3.6)
        scenes.append(await film.stop(fade_in=0.3, fade_out=0.6))
        await context.close()
        await browser.close()
    return scenes


def join(scenes):
    OUT.mkdir(parents=True, exist_ok=True)
    listing = WORK / "scenes.txt"
    listing.write_text("".join(f"file '{s}'\n" for s in scenes))
    temp = OUT / "promo.part.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temp),
        ],
        check=True,
    )
    temp.rename(OUT / "promo.mp4")
    # The poster is a still from the title card: clean, and it works as a share image too.
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            "2.3",
            "-i",
            str(OUT / "promo.mp4"),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(OUT / "poster.jpg"),
        ],
        check=True,
    )


if __name__ == "__main__":
    port = guide.start_server()
    downloader.download_and_convert = slow_download
    scenes = asyncio.run(make_scenes(f"http://127.0.0.1:{port}"))
    join(scenes)
    print("wrote", (OUT / "promo.mp4").relative_to(ROOT))
