#!/usr/bin/env python3
"""Start MediaForge.

    python run.py              open it on this computer only (http://localhost:8000)
    python run.py --lan        also let phones and tablets on your Wi-Fi open it
    python run.py --port 9000  use another port

Run it from any folder, after installing the requirements in backend/requirements.txt.
"""

import argparse
import socket
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Start MediaForge.")
    parser.add_argument("--lan", action="store_true", help="allow other devices on your network")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default 8000)")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed. Run: pip install -r backend/requirements.txt")
        return 1

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"\nMediaForge is starting. On this computer open http://localhost:{args.port}")
    if args.lan:
        address = lan_address()
        if address:
            print(f"On a phone or tablet on the same Wi-Fi open http://{address}:{args.port}")
        print("Anyone on this network can use it while it runs. Only do this on a network you trust.")
    print("Press Ctrl+C to stop.\n")

    uvicorn.run("app.main:app", host=host, port=args.port, app_dir=str(BACKEND))
    return 0


if __name__ == "__main__":
    sys.exit(main())
