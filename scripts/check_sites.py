"""Check which sites MediaForge can read, without downloading anything.

Put one link per line in a text file (blank lines and lines starting with # are ignored), then:

    python scripts/check_sites.py sites.txt            # writes site-report.md
    python scripts/check_sites.py sites.txt --download # also fetches the first 5 seconds

It uses the same yt-dlp options as the app, so your Settings (browser sign-in, proxy) apply.
Run it from the repository folder, with the virtual environment active. Use only links you may
copy. The report shows the error code and the technical text of each failure.
"""

import argparse
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import yt_dlp  # noqa: E402

from app import downloader, errors, validators  # noqa: E402


def check(url: str, fetch: bool) -> tuple[str, str, float]:
    start = time.time()
    try:
        validators.validate_url(url)
        options = downloader._base_options()
        if fetch:
            options.update(
                {
                    "outtmpl": str(Path(tempfile.mkdtemp()) / "%(id)s.%(ext)s"),
                    "download_ranges": yt_dlp.utils.download_range_func([], [(0, 5)]),
                    "format": "worst",
                }
            )
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=fetch) or {}
        title = str(info.get("title") or "")[:50]
        return "Works", title, time.time() - start
    except Exception as exc:  # report every kind of failure
        message = (
            downloader._clean_error(exc)
            if isinstance(exc, yt_dlp.utils.YoutubeDLError)
            else str(exc)
        )
        code = getattr(exc, "code", None) or errors.classify(message)
        return f"Fails ({code})", message[:140], time.time() - start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("file", help="text file with one link per line")
    parser.add_argument("--download", action="store_true", help="also fetch 5 seconds of media")
    parser.add_argument("--out", default="site-report.md")
    args = parser.parse_args()

    urls = [
        line.strip()
        for line in Path(args.file).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not urls:
        print(
            f"No links found in {args.file}. Lines that start with # are ignored: put a real "
            "video link on its own line and remove the # in front of it."
        )
        return 2
    rows = []
    for url in urls:
        result, note, seconds = check(url, args.download)
        print(f"{result:<22} {seconds:5.1f}s  {url}")
        rows.append((url, result, note.replace("|", "/"), seconds))

    lines = [
        f"# Site check, {date.today()}",
        "",
        f"yt-dlp {yt_dlp.version.__version__}. Mode: "
        + ("fetched 5 seconds" if args.download else "read only"),
        "",
        "| Link | Result | Seconds | Notes |",
        "| --- | --- | --- | --- |",
    ]
    lines += [f"| {u} | {r} | {s:.1f} | {n} |" for u, r, n, s in rows]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0 if all(r.startswith("Works") for _, r, _, _ in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
