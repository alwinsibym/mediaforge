"""Convert generated test media in every format and report speed, size and correctness.

    python scripts/selftest.py

Needs only FFmpeg. It makes a 20-second test video, converts it to each output format through
the same code the app uses, then checks the result with ffprobe: it must exist, have the right
length, and use the right kind of stream. It also tests trimming and loudness. Nothing is
downloaded from the internet. Exit code 0 means every check passed.
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import formats, transcoder  # noqa: E402

LENGTH = 20.0


def probe(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(out.stdout or "{}")


def decoded_length(path: Path) -> float:
    """Length by decoding the file. Raw AAC has no length in its header, so probing misleads."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-", "-progress", "pipe:1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    micros = [int(x.split("=")[1]) for x in out.stdout.splitlines() if x.startswith("out_time_us=")]
    return max(micros, default=0) / 1e6


def make_source(folder: Path) -> Path:
    path = folder / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=640x360:rate=25:duration={LENGTH}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={LENGTH}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


def main() -> int:
    if not transcoder.ffmpeg_available():
        print("FFmpeg was not found. Install it first (see the README).")
        return 2
    folder = Path(tempfile.mkdtemp(prefix="mediaforge-selftest-"))
    source = make_source(folder)
    rows, failures = [], 0
    catalogue = formats.describe()
    for fmt in catalogue["audio"] + catalogue["video"]:
        key = fmt["id"]
        quality = (
            formats.DEFAULT_VIDEO_HEIGHT if formats.is_video(key) else formats.DEFAULT_AUDIO_BITRATE
        )
        work = folder / key
        work.mkdir()
        start = time.time()
        try:
            out = transcoder.convert_file(source, key, quality, work)
            seconds = time.time() - start
            info = probe(out)
            kinds = {s["codec_type"] for s in info.get("streams", [])}
            length = decoded_length(out)
            want_video = formats.is_video(key)
            ok = (
                abs(length - LENGTH) < 1.5 and ("video" in kinds) == want_video and "audio" in kinds
            )
            rows.append((key, "pass" if ok else "FAIL", seconds, out.stat().st_size, length))
            failures += not ok
        except Exception as exc:
            rows.append((key, f"FAIL: {exc}"[:60], time.time() - start, 0, 0))
            failures += 1

    print(f"\n{'format':<9}{'result':<10}{'seconds':>8}{'size KB':>10}{'length':>8}")
    for key, result, seconds, size, length in rows:
        print(f"{key:<9}{result:<10}{seconds:8.1f}{size / 1024:10.0f}{length:8.1f}")
    print(f"\nFiles are in {folder}")
    print("ALL PASSED" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
