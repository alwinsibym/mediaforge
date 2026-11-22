"""Update yt-dlp without pip, for the Windows app.

yt-dlp is published on PyPI as a wheel, which is a zip file. This downloads the newest wheel,
checks its SHA-256 against the value PyPI lists, and unpacks the `yt_dlp` folder into the updates
folder. The next start of the app uses it (see paths.use_updated_packages).
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from . import paths

PYPI_URL = "https://pypi.org/pypi/{project}/json"
# PyPI project -> the folder inside its wheel. The second one holds the scripts yt-dlp needs to
# read YouTube, so it must be updated together with yt-dlp.
PROJECTS = {"yt-dlp": "yt_dlp", "yt-dlp-ejs": "yt_dlp_ejs"}
MAX_WHEEL_BYTES = 40 * 1024 * 1024


class UpdateError(Exception):
    """The update could not be downloaded or unpacked."""


Fetch = Callable[[str], bytes]


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MediaForge-updater"})
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:  # noqa: S310
            data = reply.read(MAX_WHEEL_BYTES + 1)
    except OSError as exc:
        raise UpdateError(f"Could not reach PyPI: {exc}") from exc
    if len(data) > MAX_WHEEL_BYTES:
        raise UpdateError("The download is larger than expected.")
    return data


def latest_wheel(project: str, fetch: Fetch = _fetch) -> tuple[str, str, str]:
    """(version, wheel url, sha256) of the newest release of `project`."""
    try:
        info = json.loads(fetch(PYPI_URL.format(project=project)))
        version = info["info"]["version"]
        for item in info["urls"]:
            if item.get("packagetype") == "bdist_wheel" and item["filename"].endswith(
                "-none-any.whl"
            ):
                return version, item["url"], item["digests"]["sha256"]
    except (KeyError, ValueError, TypeError) as exc:
        raise UpdateError(f"PyPI sent an unexpected answer for {project}.") from exc
    raise UpdateError(f"No universal wheel was found for {project}.")


def _unpack(wheel: bytes, folder_name: str, into: Path) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(wheel))
    except zipfile.BadZipFile as exc:
        raise UpdateError("The downloaded file is not a valid wheel.") from exc
    root = into.resolve()
    members = [m for m in archive.namelist() if m.startswith(folder_name + "/")]
    if not members:
        raise UpdateError(f"The wheel has no {folder_name} folder.")
    for name in members:
        target = (into / name).resolve()
        if root not in target.parents and target != root:
            raise UpdateError("The wheel contains an unsafe path.")
        if name.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))


def install_latest(
    destination: Path | None = None, current: str | None = None, fetch: Fetch = _fetch
) -> dict:
    """Download and unpack the newest yt-dlp. Returns {"before", "after", "changed"}."""
    destination = destination or paths.updates_dir()
    before = current or paths.updated_ytdlp_version(destination) or paths.bundled_ytdlp_version()
    version, url, digest = latest_wheel("yt-dlp", fetch)
    if before and paths.version_tuple(version) <= paths.version_tuple(before):
        return {"before": before, "after": before, "changed": False}

    staging = destination.with_name(destination.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        for project, folder in PROJECTS.items():
            if project == "yt-dlp":
                wheel_url, wheel_digest = url, digest
            else:
                try:
                    _, wheel_url, wheel_digest = latest_wheel(project, fetch)
                except UpdateError:
                    continue  # the helper scripts are optional
            data = fetch(wheel_url)
            if hashlib.sha256(data).hexdigest() != wheel_digest:
                raise UpdateError("The download did not match its checksum, so it was discarded.")
            _unpack(data, folder, staging)
        if paths.updated_ytdlp_version(staging) != version:
            raise UpdateError("The unpacked update does not match the version PyPI listed.")
        old = destination.with_name(destination.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        if destination.exists():
            destination.rename(old)
        staging.rename(destination)
        shutil.rmtree(old, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"before": before or "unknown", "after": version, "changed": True}
