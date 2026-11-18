"""Unfinished downloads, kept in a JSON file so they can be resumed later.

An entry is created when a playlist job that saves to a folder starts. Each finished video
is removed from it, and the entry disappears when nothing is left. If MediaForge is closed or
the connection is lost for good, what remains is listed in the page with a Resume button.
"""

import json
import threading
import time

from . import config

_lock = threading.Lock()


def _path():
    return config.DATA_DIR / "pending.json"


def _read() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(entries: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = _path().with_suffix(".tmp")
    temporary.write_text(json.dumps(entries), encoding="utf-8")
    temporary.replace(_path())


def _safely(change) -> None:
    """Run `change(entries)` under the lock. Never raises: this list is a convenience."""
    try:
        with _lock:
            entries = _read()
            change(entries)
            _write(entries)
    except OSError:
        pass


def save(job_id: str, entry: dict) -> None:
    entry = {**entry, "created": int(time.time())}
    _safely(lambda entries: entries.__setitem__(job_id, entry))


def set_folder(job_id: str, folder: str) -> None:
    def change(entries):
        if job_id in entries:
            entries[job_id]["folder"] = folder

    _safely(change)


def mark_done(job_id: str, number: int) -> None:
    def change(entries):
        entry = entries.get(job_id)
        if entry is None:
            return
        entry["items"] = [item for item in entry["items"] if item.get("number") != number]
        if not entry["items"]:
            del entries[job_id]

    _safely(change)


def remove(job_id: str) -> None:
    _safely(lambda entries: entries.pop(job_id, None))


def get(job_id: str) -> dict | None:
    with _lock:
        return _read().get(job_id)


def all_entries() -> list[dict]:
    with _lock:
        entries = _read()
    listed = [{"id": job_id, **entry} for job_id, entry in entries.items() if entry.get("items")]
    return sorted(listed, key=lambda entry: entry.get("created", 0), reverse=True)
