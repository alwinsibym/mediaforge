"""Input validation helpers."""

import re
from urllib.parse import urlparse

MAX_URL_LENGTH = 2048


def validate_url(url: str | None) -> str:
    """Return a cleaned http(s) URL or raise ValueError."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Please enter a URL.")
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("That URL is too long.")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Enter a valid http:// or https:// URL.")
    return url


def safe_filename(name: str | None, default: str = "media", max_length: int = 80) -> str:
    """Strip characters that are unsafe in file names."""
    name = (name or "").strip()
    # Drop any directory part and control characters.
    name = re.split(r"[\\/]", name)[-1]
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "", name).strip(" .")
    return name[:max_length] or default
