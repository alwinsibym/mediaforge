"""Input validation helpers."""

import ipaddress
import re
import socket
from urllib.parse import urlparse

from . import config

MAX_URL_LENGTH = 2048


class BlockedAddress(ValueError):
    """A link that points inside the person's own network."""

    code = "MF-SEC-01"


def _is_internal(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified


def _check_host(host: str) -> None:
    """Refuse hosts that lead to this computer or to devices on its network."""
    if config.ALLOW_PRIVATE_URLS:
        return
    name = host.strip("[]").rstrip(".").lower()
    blocked = BlockedAddress(
        "That link points to this computer or to your local network, so it was blocked."
    )
    if name == "localhost" or name.endswith((".localhost", ".local", ".internal")):
        raise blocked
    if _is_internal(name):
        raise blocked
    try:
        ipaddress.ip_address(name)
        return  # a public address
    except ValueError:
        pass
    try:
        found = socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return  # offline or unknown name: the download itself will explain it
    if any(_is_internal(entry[4][0]) for entry in found):
        raise blocked


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
    if parsed.hostname is None:
        raise ValueError("Enter a valid http:// or https:// URL.")
    _check_host(parsed.hostname)
    return url


def safe_filename(name: str | None, default: str = "media", max_length: int = 80) -> str:
    """Strip characters that are unsafe in file names."""
    name = (name or "").strip()
    # Drop any directory part and control characters.
    name = re.split(r"[\\/]", name)[-1]
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "", name).strip(" .")
    return name[:max_length] or default
