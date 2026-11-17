"""Settings the person can change in the page, saved in a small JSON file."""

import json
import os
import threading
from pathlib import Path

from . import config

COOKIE_BROWSERS = ("chrome", "firefox", "edge", "brave", "chromium", "opera", "vivaldi", "safari")
MAX_PARALLEL = 3

DEFAULTS = {
    "cookies_browser": "",  # sign-in taken from this browser, or "" for none
    "cookies_file": "",  # or a cookies.txt file
    "parallel": 2,  # playlist videos downloaded at the same time
    "aria2c": False,  # use aria2c (if installed) for more connections per file
}

_lock = threading.Lock()


def _path() -> Path:
    return config.DATA_DIR / "settings.json"


def load() -> dict:
    """The saved settings, with defaults filled in. A missing or damaged file gives defaults."""
    with _lock:
        try:
            saved = json.loads(_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
    if not isinstance(saved, dict):
        saved = {}
    merged = {**DEFAULTS}
    for key in DEFAULTS:
        if key in saved and type(saved[key]) is type(DEFAULTS[key]):
            merged[key] = saved[key]
    merged["parallel"] = min(MAX_PARALLEL, max(1, merged["parallel"]))
    return merged


def validate(update: dict) -> dict:
    """Check the values the person sent. Raises ValueError with a readable message."""
    clean: dict = {}
    if "cookies_browser" in update:
        browser = str(update["cookies_browser"] or "").lower().strip()
        if browser and browser not in COOKIE_BROWSERS:
            raise ValueError("Choose one of the listed browsers.")
        clean["cookies_browser"] = browser
    if "cookies_file" in update:
        raw = str(update["cookies_file"] or "").strip().strip('"')
        if raw and not os.path.isfile(raw):
            raise ValueError("That cookies file was not found. Check the path.")
        clean["cookies_file"] = raw
    if "parallel" in update:
        try:
            value = int(update["parallel"])
        except (TypeError, ValueError):
            raise ValueError("Parallel downloads must be a number from 1 to 3.") from None
        if not 1 <= value <= MAX_PARALLEL:
            raise ValueError(f"Parallel downloads must be from 1 to {MAX_PARALLEL}.")
        clean["parallel"] = value
    if "aria2c" in update:
        clean["aria2c"] = bool(update["aria2c"])
    return clean


def save(update: dict) -> dict:
    clean = validate(update)
    current = load()
    current.update(clean)
    with _lock:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary = _path().with_suffix(".tmp")
        temporary.write_text(json.dumps(current, indent=2), encoding="utf-8")
        temporary.replace(_path())
    return current
