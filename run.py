#!/usr/bin/env python3
"""Start MediaForge.

    python run.py              open it on this computer only (http://localhost:8000)
    python run.py --lan        also let phones and tablets on your Wi-Fi open it
    python run.py --port 9000  use another port
    python run.py --open       open the browser too, and reuse a copy that is already running
                               (this is what the desktop shortcut runs)

Run it from any folder, after installing the requirements in backend/requirements.txt.
"""

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))


def lan_address() -> str | None:
    """This computer's address on the local network, if it has one."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No data is sent. Connecting a UDP socket only picks the outgoing interface.
        probe.connect(("10.255.255.255", 1))
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith("127.") else address


def open_when_ready(server, url: str) -> None:
    """Open the browser once the server accepts connections."""
    for _ in range(200):
        if server.started:
            webbrowser.open(url)
            return
        time.sleep(0.1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start MediaForge.")
    parser.add_argument("--lan", action="store_true", help="allow other devices on your network")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default 8000)")
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the browser, and reuse a MediaForge that is already running",
    )
    args = parser.parse_args()

    from app import config, launcher, paths

    if paths.FROZEN:
        args.open = True  # the Windows app always opens the page, like the desktop shortcut

    log = launcher.redirect_output_if_no_console(config.DATA_DIR)

    try:
        import uvicorn
    except ImportError:
        launcher.alert(
            "MediaForge",
            "The required packages are not installed in this Python.\n"
            "Open a terminal in the MediaForge folder and run:\n"
            "pip install -r backend/requirements.txt",
        )
        return 1

    port = args.port
    if args.open:
        try:
            port, running = launcher.choose_port(args.port)
        except OSError as exc:
            launcher.alert("MediaForge", str(exc))
            return 1
        if running:
            webbrowser.open(f"http://localhost:{port}")
            return 0

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"\nMediaForge is starting. On this computer open http://localhost:{port}")
    if args.lan:
        address = lan_address()
        if address:
            print(f"On a phone or tablet on the same Wi-Fi open http://{address}:{port}")
        print("Anyone on this network can use it while it runs. Only do this on a network you trust.")
    if log:
        print(f"Running without a console. Messages go to {log}")
    else:
        print("Press Ctrl+C to stop, or use Quit in the page.\n")

    from app import runtime

    if paths.FROZEN:
        from app.main import app as application  # a string import cannot find it in a bundle

        config_ = uvicorn.Config(application, host=host, port=port, log_config=None)
    else:
        config_ = uvicorn.Config("app.main:app", host=host, port=port)
    server = uvicorn.Server(config_)
    runtime.SERVER = server
    if args.open:
        threading.Thread(
            target=open_when_ready, args=(server, f"http://localhost:{port}"), daemon=True
        ).start()
    try:
        server.run()
    except Exception as exc:
        launcher.alert("MediaForge", f"MediaForge stopped: {exc}")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
