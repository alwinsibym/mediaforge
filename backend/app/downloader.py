"""Download media from a URL with yt-dlp and convert it with FFmpeg."""

import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path

import yt_dlp
from yt_dlp.postprocessor.metadataparser import MetadataParserPP
from yt_dlp.utils import DownloadError

from . import config, ffmpeg_locator, formats

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class ConversionError(Exception):
    """A problem the user can understand (bad URL, too long, unsupported...)."""


def _clean_error(exc: Exception) -> str:
    message = _ANSI_RE.sub("", str(exc)).strip()
    message = re.sub(r"^ERROR:\s*", "", message)
    # yt-dlp appends a bug-report hint that isn't useful to end users.
    message = message.split("; please report this issue")[0]
    return message[:300] or "The download failed."


FFMPEG_HELP = (
    "FFmpeg was not found on this computer. It is needed to merge video and audio and to "
    "convert formats. Install it (Windows: winget install Gyan.FFmpeg), open a new terminal, "
    "and restart MediaForge. If it is installed but still not found, set the "
    "MEDIAFORGE_FFMPEG_DIR environment variable to the folder that contains ffmpeg.exe, "
    'then check that /api/health shows "ffmpeg": true.'
)


def ffmpeg_ready() -> bool:
    """True when ffmpeg can be found (on the PATH or in a known install folder)."""
    return ffmpeg_locator.ready()


# yt-dlp needs a JavaScript runtime to read YouTube. name -> executable.
_JS_RUNTIME_BINARIES = (
    ("deno", "deno"),
    ("node", "node"),
    ("bun", "bun"),
    ("quickjs", "qjs"),
)


def js_runtimes() -> dict:
    """Find installed JavaScript runtimes, including ones in the active venv."""
    search_path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    found = {}
    for name, binary in _JS_RUNTIME_BINARIES:
        path = shutil.which(binary, path=search_path)
        if path:
            found[name] = {"path": path}
    return found


def _base_options() -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "windowsfilenames": True,
    }
    runtimes = js_runtimes()
    if runtimes:
        options["js_runtimes"] = runtimes
    location = ffmpeg_locator.ytdlp_location()
    if location:
        options["ffmpeg_location"] = location
    return options


def fetch_info(url: str) -> dict:
    """Return basic metadata for a URL without downloading it."""
    options = {**_base_options(), "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise ConversionError(_clean_error(exc)) from exc

    return {
        "title": info.get("title") or "Untitled",
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "thumbnail": info.get("thumbnail"),
        "is_live": bool(info.get("is_live")),
    }


def fetch_playlist(url: str) -> dict:
    """List the videos in a playlist link without downloading anything."""
    options = {
        **_base_options(),
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
        "playlistend": config.MAX_PLAYLIST_ITEMS,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise ConversionError(_clean_error(exc)) from exc

    raw_entries = [entry for entry in (info.get("entries") or []) if entry]
    if info.get("_type") != "playlist" or not raw_entries:
        raise ConversionError("That link is not a playlist. Use the Link tab for a single video.")

    entries = []
    for entry in raw_entries:
        link = entry.get("url") or entry.get("webpage_url")
        if link and not link.startswith("http") and entry.get("id"):
            link = f"https://www.youtube.com/watch?v={entry['id']}"
        if not link or not link.startswith("http"):
            continue  # private or deleted videos have no link
        entries.append(
            {
                "index": len(entries) + 1,
                "title": entry.get("title") or "Untitled",
                "url": link,
                "duration": entry.get("duration"),
            }
        )
    if not entries:
        raise ConversionError("None of the videos in that playlist can be downloaded.")

    return {
        "title": info.get("title") or "Playlist",
        "uploader": info.get("uploader") or info.get("channel"),
        "entries": entries,
        "limit": config.MAX_PLAYLIST_ITEMS,
    }


def _video_selector(fmt: str, height: str) -> str:
    if formats.is_preset(fmt):
        # Car presets are re-encoded at 720x576 or less, so skip bigger downloads.
        return "bestvideo[height<=576]+bestaudio/best[height<=576]/bestvideo+bestaudio/best"
    h = "" if height == "best" else f"[height<={height}]"
    if fmt == "mp4":
        return (
            f"bestvideo[ext=mp4]{h}+bestaudio[ext=m4a]"
            f"/best[ext=mp4]{h}/bestvideo{h}+bestaudio/best{h}"
        )
    if fmt == "webm":
        return (
            f"bestvideo[ext=webm]{h}+bestaudio[ext=webm]"
            f"/best[ext=webm]{h}/bestvideo{h}+bestaudio/best{h}"
        )
    return f"bestvideo{h}+bestaudio/best{h}"  # mkv


# Output formats that can carry a cover image. Ogg, Opus and FLAC need the mutagen package.
_COVER_FORMATS = {"mp3", "m4a", "mp4", "mkv", "flac", "ogg", "opus"}
_MUTAGEN_COVER_FORMATS = {"flac", "ogg", "opus"}


def _can_embed_cover(fmt: str) -> bool:
    if fmt not in _COVER_FORMATS:
        return False
    if fmt in _MUTAGEN_COVER_FORMATS:
        return importlib.util.find_spec("mutagen") is not None
    if fmt == "mkv":
        # yt-dlp reads the cover's type with ffprobe when attaching it to MKV.
        location = ffmpeg_locator.ytdlp_location()
        return bool(location and shutil.which("ffprobe", path=location))
    return True


def _template_text(value: str) -> str:
    """Make text safe to use as the default value inside a yt-dlp template."""
    return re.sub(r"[()|%\r\n]", " ", value).strip()


def _metadata_postprocessors(fmt: str, extra: dict | None) -> list[dict]:
    """Postprocessors that write title, artist, album and cover art into the file.

    `extra` can hold the playlist name ("album") and position ("track"). They are only
    used when the site did not provide an album or track number of its own.
    """
    processors: list[dict] = []
    actions = []
    if extra and extra.get("album"):
        template = f"%(album|{_template_text(extra['album'])})s"
        actions.append((MetadataParserPP.interpretter, template, "%(album)s"))
    if extra and extra.get("track"):
        template = f"%(track_number|{int(extra['track'])})s"
        actions.append((MetadataParserPP.interpretter, template, "%(track_number)s"))
    if actions:
        processors.append({"key": "MetadataParser", "when": "pre_process", "actions": actions})

    processors.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": False})

    if _can_embed_cover(fmt):
        processors.append(
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}
        )
        processors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    return processors


def _build_options(fmt: str, quality: str, workdir: Path, extra: dict | None = None) -> dict:
    options = _base_options()
    options["outtmpl"] = str(workdir / "%(title).80s.%(ext)s")

    if formats.is_audio(fmt):
        options["format"] = "bestaudio/best"
        postprocessor = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": formats.AUDIO_FORMATS[fmt]["ytdlp_codec"],
        }
        if fmt not in formats.LOSSLESS_AUDIO:
            postprocessor["preferredquality"] = quality
        options["postprocessors"] = [postprocessor]
        options["postprocessors"] += _metadata_postprocessors(fmt, extra)
    else:
        options["format"] = _video_selector(fmt, quality)
        if formats.is_preset(fmt):
            # Download into MKV (holds any codec); FFmpeg re-encodes it afterwards.
            options["merge_output_format"] = "mkv"
            options["postprocessors"] = _metadata_postprocessors(fmt, extra)
        else:
            options["merge_output_format"] = fmt
            # Re-mux only when the downloaded container differs from the request.
            options["postprocessors"] = [{"key": "FFmpegVideoConvertor", "preferedformat": fmt}]
            options["postprocessors"] += _metadata_postprocessors(fmt, extra)
    if any(pp["key"] == "EmbedThumbnail" for pp in options.get("postprocessors", [])):
        options["writethumbnail"] = True
    return options


def _find_output(workdir: Path, extension: str) -> Path:
    files = [
        p for p in workdir.iterdir() if p.is_file() and p.suffix not in {".part", ".ytdl", ".tmp"}
    ]
    if not files:
        raise ConversionError("Conversion finished but no file was produced.")
    preferred = [p for p in files if p.suffix.lower() == f".{extension}"]
    return max(preferred or files, key=lambda p: p.stat().st_size)


def download_and_convert(
    url: str, fmt: str, quality: str, workdir: Path, extra: dict | None = None
) -> Path:
    """Download `url`, convert it to `fmt`, and return the output file path.

    `extra` may carry {"album": playlist name, "track": position} for playlist items.
    """
    if not ffmpeg_ready():
        raise ConversionError(FFMPEG_HELP)

    info = fetch_info(url)

    if info["is_live"]:
        raise ConversionError("Live streams can't be converted.")
    duration = info["duration"]
    if duration and duration > config.MAX_DURATION_SECONDS:
        limit_min = config.MAX_DURATION_SECONDS // 60
        raise ConversionError(f"This video is longer than the {limit_min}-minute limit.")

    options = _build_options(fmt, quality, workdir, extra)
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except DownloadError as exc:
        raise ConversionError(_clean_error(exc)) from exc

    if formats.is_preset(fmt):
        from . import transcoder  # imported here because transcoder imports this module

        downloaded = _find_output(workdir, "mkv")
        output = transcoder.convert_file(downloaded, fmt, quality, workdir)
        downloaded.unlink(missing_ok=True)
        return output

    return _find_output(workdir, fmt)
