"""Start the built app, check that it answers, and (optionally) that a yt-dlp update wins.

python packaging/smoke.py dist/MediaForge/MediaForge[.exe]
"""

import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def get(port: int, path: str) -> bytes:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as reply:
        return reply.read()


def run_app(exe: Path, work: Path) -> tuple[subprocess.Popen, int]:
    port = free_port()
    process = subprocess.Popen([str(exe), "--port", str(port)], cwd=work)
    for _ in range(120):
        try:
            get(port, "/api/health")
            return process, port
        except OSError:
            if process.poll() is not None:
                raise SystemExit(
                    f"The app exited early with code {process.returncode}."
                ) from None
            time.sleep(0.5)
    process.kill()
    raise SystemExit("The app did not start within 60 seconds.")


def stop(process: subprocess.Popen, port: int) -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", method="POST"),
            timeout=10,
        )
    except OSError:
        pass
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


def check(name: str, condition: bool) -> None:
    print(("PASS  " if condition else "FAIL  ") + name)
    if not condition:
        raise SystemExit(1)


def main() -> int:
    exe = Path(sys.argv[1]).resolve()
    app_folder = exe.parent
    shutil.rmtree(app_folder / "data", ignore_errors=True)

    process, port = run_app(exe, app_folder)
    try:
        health = json.loads(get(port, "/api/health"))
        check("health says ok", health["status"] == "ok")
        check("it knows it is the packaged app", health.get("packaged") is True)
        check("yt-dlp is present", bool(re.match(r"\d{4}\.\d+", health["yt_dlp"])))
        check("a JavaScript runtime (deno) is bundled", "deno" in health["js_runtimes"])
        check("the page is served", b"MediaForge" in get(port, "/"))
        check("the format list loads", "audio" in json.loads(get(port, "/api/formats")))
        tweaks_info = json.loads(get(port, "/api/formats"))["tweaks"]
        check("spatial sound is listed", len(tweaks_info["spatial"]) == 9)
        bundled = health["yt_dlp"]
    finally:
        stop(process, port)

    if (
        len(sys.argv) > 2
    ):  # a copy of the installed yt_dlp folder, to act as a downloaded update
        update = app_folder / "data" / "updates"
        shutil.rmtree(update, ignore_errors=True)
        shutil.copytree(sys.argv[2], update / "yt_dlp")
        version_file = update / "yt_dlp" / "version.py"
        text = version_file.read_text(encoding="utf-8")
        version_file.write_text(
            re.sub(r"__version__\s*=\s*'[^']+'", "__version__ = '2099.01.01'", text),
            encoding="utf-8",
        )
        process, port = run_app(exe, app_folder)
        try:
            after = json.loads(get(port, "/api/health"))["yt_dlp"]
            check(
                f"a newer downloaded yt-dlp is used ({bundled} -> {after})",
                after == "2099.01.01",
            )
        finally:
            stop(process, port)
        # An update older than the bundled copy is removed, not used.
        version_file.write_text(
            re.sub(r"__version__\s*=\s*'[^']+'", "__version__ = '2000.01.01'", text),
            encoding="utf-8",
        )
        process, port = run_app(exe, app_folder)
        try:
            after = json.loads(get(port, "/api/health"))["yt_dlp"]
            check("an older update is ignored", after == bundled)
            check("and its folder is deleted", not update.exists())
        finally:
            stop(process, port)
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
