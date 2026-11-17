"""A short list of past downloads, kept in a JSON file so they can be done again."""

import json
import threading
import time

from . import config

MAX_ENTRIES = 300
_lock = threading.Lock()


def _path():
    return config.DATA_DIR / "history.json"


def _read() -> list[dict]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _write(entries: list[dict]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = _path().with_suffix(".tmp")
    temporary.write_text(json.dumps(entries), encoding="utf-8")
    temporary.replace(_path())


def add(title: str, url: str, fmt: str, quality: str, filename: str | None) -> None:
    """Remember one finished download. Never raises: history is a convenience."""
    entry = {
        "title": title[:200],
        "url": url,
        "format": fmt,
        "quality": quality,
        "filename": filename,
        "when": int(time.time()),
    }
    try:
        with _lock:
            entries = _read()
            entries.append(entry)
            _write(entries[-MAX_ENTRIES:])
    except OSError:
        pass


def recent(limit: int = 100) -> list[dict]:
    with _lock:
        entries = _read()
    return list(reversed(entries))[:limit]


def clear() -> None:
    with _lock:
        try:
            _path().unlink(missing_ok=True)
        except OSError:
            pass
