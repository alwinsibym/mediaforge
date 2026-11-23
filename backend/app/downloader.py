"""Download media from a URL with yt-dlp and convert it with FFmpeg."""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import yt_dlp
from yt_dlp.postprocessor.metadataparser import MetadataParserPP

from . import config, cover, errors, ffmpeg_locator, formats, paths, settings, validators
from . import features as features_mod

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class ConversionError(Exception):
    """A problem the user can understand (bad URL, too long, unsupported...).

    `code` is an error code from `errors.CATALOG`, and `technical` the original message.
    """

    def __init__(self, message: str = "", code: str | None = None, technical: str | None = None):
        super().__init__(message)
        self.code = code
        self.technical = technical


class BotCheckError(ConversionError):
    """The site asked for proof that this is a person (YouTube's 'confirm you're not a bot')."""


class NetworkError(ConversionError):
    """This computer could not reach the site (DNS or connection trouble)."""


class Cancelled(Exception):
    """The person stopped the job."""


def _is_transient(message: str) -> bool:
    """Errors that usually go away when the download is simply tried again."""
    text = message.lower()
    return any(
        hint in text
        for hint in (
            "403",
            "forbidden",
            "timed out",
            "timeout",
            "http error 5",
            "connection reset",
            "connectionreset",
            "forcibly closed",
            "connection aborted",
        )
    )


def is_bot_check(message: str) -> bool:
    text = message.lower()
    return "not a bot" in text or ("sign in" in text and "confirm" in text)


_NETWORK_HINTS = (
    "getaddrinfo failed",
    "errno 11001",
    "name or service not known",
    "temporary failure in name resolution",
    "nodename nor servname",
    "failed to resolve",
    "network is unreachable",
)
_TIMEOUT_HINTS = ("connect timeout", "timed out")
_SIGN_IN_HINTS = ("sign in", "log in", "login required", "logged in", "authentication", "cookies")

BOT_CHECK_HELP = (
    'YouTube is asking for a sign-in check ("confirm you\'re not a bot"). Open Settings and '
    "choose the browser where you are signed in to YouTube (Firefox is the most reliable), "
    "then try again. Waiting a while also helps."
)
SIGN_IN_HELP = (
    "This site wants you to be signed in. Open Settings and choose the browser where you are "
    "signed in to it, then try again."
)
NETWORK_HELP = (
    "This computer could not reach that site (a network or DNS problem, not a MediaForge "
    "problem). Check your internet connection, VPN or firewall, and try opening the site in "
    "your browser. Some networks block certain sites."
)


CONNECTION_CLOSED_HELP = (
    "The site closed the connection while MediaForge was loading its page. This usually means "
    "the site blocks automated downloads, or something on your network (a VPN, antivirus "
    "web protection, firewall or your internet provider) is cutting the connection. Try again "
    "with the VPN or antivirus web shield turned off, or turned on if the site is blocked in "
    "your country."
)


COOKIES_HELP = (
    "MediaForge could not read the sign-in from your browser. Chrome and Edge lock their "
    "cookie file while they run, and recent versions also encrypt it so other programs cannot "
    "read it. Use Firefox in Settings instead, or export a cookies.txt file from your browser "
    "(for example with the 'Get cookies.txt LOCALLY' extension) and choose that file in Settings."
)


TIMEOUT_HELP = (
    "The site did not answer in time (the connection timed out). The site may be down or slow, "
    "or your network, VPN or firewall may be blocking it. Check that the site opens in your "
    "browser, then try again."
)
NO_VIDEO_HELP = (
    "No video was found in that post. It may only have text or pictures (MediaForge saves "
    "videos and audio, not images), the video may belong to a quoted or replied-to post (paste "
    "that post's link instead), or the site hides it from visitors who are not signed in "
    "(choose your browser in Settings)."
)


def _friendly(message: str) -> str:
    text = message.lower()
    if "no video could be found" in text or "no video formats found" in text:
        return NO_VIDEO_HELP
    if "cookie database" in text or "decrypt" in text and "cookie" in text:
        return COOKIES_HELP
    if any(hint in text for hint in ("connectionreset", "forcibly closed", "connection aborted")):
        return CONNECTION_CLOSED_HELP
    if is_bot_check(message):
        return BOT_CHECK_HELP
    if any(hint in text for hint in _NETWORK_HINTS):
        return NETWORK_HELP
    if any(hint in text for hint in _TIMEOUT_HINTS):
        return TIMEOUT_HELP
    if "403" in message or "forbidden" in text:
        return (
            "The site refused the download (HTTP 403) even after retrying. Try again in a "
            'moment. If it keeps happening, update yt-dlp with: pip install -U "yt-dlp[default]"'
        )
    if any(hint in text for hint in _SIGN_IN_HINTS) and "private" not in text:
        return f"{SIGN_IN_HELP} ({message[:120]})"
    return message


def is_network_problem(message: str) -> bool:
    text = message.lower()
    return any(hint in text for hint in _NETWORK_HINTS + _TIMEOUT_HINTS)


def _to_error(exc: Exception) -> ConversionError:
    """Turn a yt-dlp error into an error with a message a person can act on."""
    message = _clean_error(exc)
    code = errors.classify(message)
    friendly = _friendly(message)
    if is_bot_check(message):
        return BotCheckError(friendly, code, message)
    if is_network_problem(message):
        return NetworkError(friendly, code, message)
    return ConversionError(friendly, code, message)


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
    folders = [str(Path(sys.executable).parent), os.environ.get("PATH", "")]
    if paths.FROZEN:
        folders.insert(0, str(paths.bundle_dir()))  # the Windows app carries its own deno
    search_path = os.pathsep.join(folders)
    found = {}
    for name, binary in _JS_RUNTIME_BINARIES:
        path = shutil.which(binary, path=search_path)
        if path:
            found[name] = {"path": path}
    return found


def _base_options() -> dict:
    options = {
        "quiet": True,
        "noprogress": True,
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

    saved = settings.load()
    if saved["cookies_file"]:
        options["cookiefile"] = saved["cookies_file"]
    elif saved["cookies_browser"]:
        options["cookiesfrombrowser"] = (saved["cookies_browser"],)
    if saved["proxy"]:
        options["proxy"] = saved["proxy"]
    if saved["impersonate"] and impersonation_available():
        from yt_dlp.networking.impersonate import ImpersonateTarget

        options["impersonate"] = ImpersonateTarget.from_str("chrome")
    return options


def impersonation_available() -> bool:
    """True when the optional curl_cffi package is installed."""
    return importlib.util.find_spec("curl_cffi") is not None


def aria2c_available() -> bool:
    return shutil.which("aria2c") is not None


_RESOLUTION_NAMES = {4320: "8K", 2160: "4K", 1440: "2K"}


def _nominal_height(width: int, height: int) -> int:
    """The "p" number a site would call this picture, so a wide film frame such as 3840 x 1608
    is a 2160p (4K) video, as YouTube lists it. A 16:9 or taller picture keeps its own height."""
    if width >= height:
        return max(height, round(width * 9 / 16))
    return width  # a tall (phone) video is named by its short side


def _format_size(entry: dict) -> int | None:
    return entry.get("filesize") or entry.get("filesize_approx")


def _video_qualities(source_formats: list[dict]) -> list[dict]:
    """The video qualities a video really offers, best first, with no upscaling.

    Each entry has an `id` that can be sent back as the quality: "2160" or "1440@30".
    """
    videos = [
        f
        for f in source_formats
        if f.get("vcodec") not in (None, "none") and f.get("height") and f.get("width")
    ]
    audio_sizes = [
        _format_size(f)
        for f in source_formats
        if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")
    ]
    audio_size = max((size for size in audio_sizes if size), default=0)

    by_height: dict[int, list[dict]] = {}
    for entry in videos:
        by_height.setdefault(int(entry["height"]), []).append(entry)

    qualities = []
    for height in sorted(by_height, reverse=True):
        group = by_height[height]
        smooth = [f for f in group if (f.get("fps") or 30) > 30]
        normal = [f for f in group if (f.get("fps") or 30) <= 30]
        nominal = max(_nominal_height(int(f["width"]), height) for f in group)
        name = _RESOLUTION_NAMES.get(nominal)
        # (id, formats, label suffix); the smooth variant is the default for this height.
        variants = []
        if smooth:
            fps = round(max(f["fps"] for f in smooth))
            variants.append((str(height), smooth, f"p{fps}"))
            if normal:
                variants.append((f"{height}@30", normal, "p30"))
        else:
            variants.append((str(height), normal, "p"))
        for quality_id, members, suffix in variants:
            sizes = [_format_size(f) for f in members if _format_size(f)]
            size = (max(sizes) + audio_size) if sizes else None
            qualities.append(
                {
                    "id": quality_id,
                    "label": f"{nominal}{suffix}" + (f" ({name})" if name else ""),
                    "height": height,
                    "fps": round(max(f.get("fps") or 30 for f in members)),
                    "size": size,
                }
            )
    return qualities


def _thumbnail_sources(info: dict) -> list[dict]:
    """Thumbnail sizes offered by the site, largest first, one per size (with their links)."""
    chosen: dict[tuple[int, int], dict] = {}
    for thumb in info.get("thumbnails") or []:
        width, height, link = thumb.get("width"), thumb.get("height"), thumb.get("url")
        if not (width and height and link and link.startswith("http")):
            continue
        key = (int(width), int(height))
        # Prefer JPEG over WebP when both exist at the same size.
        if key not in chosen or ".jpg" in link.split("?")[0]:
            chosen[key] = {"id": str(thumb.get("id") or len(chosen)), "url": link}
    result = [
        {"id": item["id"], "url": item["url"], "width": w, "height": h, "label": f"{w} x {h}"}
        for (w, h), item in sorted(chosen.items(), key=lambda kv: kv[0][0] * kv[0][1], reverse=True)
    ]
    if not result and info.get("thumbnail"):
        result = [
            {
                "id": "default",
                "url": info["thumbnail"],
                "width": None,
                "height": None,
                "label": "Default size",
            }
        ]
    return result


def _thumbnail_options(info: dict) -> list[dict]:
    """The thumbnail sizes shown to the user (without the links)."""
    return [{k: v for k, v in item.items() if k != "url"} for item in _thumbnail_sources(info)]


THUMBNAIL_FORMATS = {"jpg", "png", "webp"}
_THUMBNAIL_SUFFIXES = {".jpg": "jpg", ".jpeg": "jpg", ".png": "png", ".webp": "webp"}
_THUMBNAIL_ENCODERS = {
    "jpg": ["-q:v", "2", "-pix_fmt", "yuvj420p"],
    "png": [],
    "webp": ["-quality", "90"],
}


def download_thumbnail(url: str, thumb_id: str, fmt: str, square: bool, workdir: Path) -> Path:
    """Save one of a video's thumbnails, optionally cropped to a square and converted."""
    fmt = (fmt or "jpg").lower().strip()
    if fmt not in THUMBNAIL_FORMATS:
        raise ValueError(f"Unsupported image format '{fmt}'.")

    options = {**_base_options(), "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            sources = {item["id"]: item for item in _thumbnail_sources(info)}
            if thumb_id not in sources:
                raise ConversionError("That thumbnail size is not available for this video.")
            chosen = sources[thumb_id]
            data = ydl.urlopen(chosen["url"]).read()
    except yt_dlp.utils.YoutubeDLError as exc:
        raise _to_error(exc) from exc
    except OSError as exc:
        raise ConversionError("The thumbnail could not be downloaded.") from exc

    link_suffix = Path(chosen["url"].split("?")[0]).suffix.lower()
    source_fmt = _THUMBNAIL_SUFFIXES.get(link_suffix, "jpg")
    name = validators.safe_filename(info.get("title"), default="thumbnail", max_length=80)
    size = f" - {chosen['width']}x{chosen['height']}" if chosen["width"] else ""
    suffix = "-square" if square else ""
    target = workdir / f"{name}{size}{suffix}.{fmt}"

    raw = workdir / f"source.{source_fmt}"
    raw.write_bytes(data)
    if source_fmt == fmt and not square:
        raw.replace(target)
        return target

    ffmpeg = ffmpeg_locator.find_tool("ffmpeg")
    if not ffmpeg:
        raise ConversionError(FFMPEG_HELP, "MF-TOOL-01")
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw)]
    if square:
        command += ["-vf", "crop='min(iw,ih)':'min(iw,ih)'"]
    command += ["-frames:v", "1", *_THUMBNAIL_ENCODERS[fmt], str(target)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    raw.unlink(missing_ok=True)
    if result.returncode != 0 or not target.exists():
        raise ConversionError("The thumbnail could not be converted.")
    return target


def fetch_info(url: str) -> dict:
    """Return metadata for a URL without downloading it."""
    options = {**_base_options(), "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.YoutubeDLError as exc:
        raise _to_error(exc) from exc

    return {
        "title": info.get("title") or "Untitled",
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "thumbnail": info.get("thumbnail"),
        "thumbnails": _thumbnail_options(info),
        "view_count": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "is_live": bool(info.get("is_live")),
        "qualities": _video_qualities(info.get("formats") or []),
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
    except yt_dlp.utils.YoutubeDLError as exc:
        raise _to_error(exc) from exc

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


def _video_selector(fmt: str, quality: str, mute: bool = False) -> str:
    """Build the yt-dlp format selector for a video format and quality."""
    if formats.is_preset(fmt):
        # Car presets are re-encoded at 720x576 or less, so skip bigger downloads.
        return "bestvideo[height<=?576]+bestaudio/best[height<=?576]/bestvideo+bestaudio/best"

    height, fps = formats.parse_quality(quality)
    cap = (f"[height<=?{height}]" if height else "") + (f"[fps<=?{fps}]" if fps else "")
    # H.264 plays on almost everything but YouTube stops offering it above 1080p.
    plays_everywhere = bool(height and height <= 1080)

    if mute:
        if fmt == "mp4" and plays_everywhere:
            return f"bestvideo[vcodec^=avc1]{cap}/bestvideo{cap}/best{cap}"
        if fmt == "webm":
            return f"bestvideo[ext=webm]{cap}/bestvideo{cap}/best{cap}"
        return f"bestvideo{cap}/best{cap}"

    if fmt == "mp4":
        if plays_everywhere:
            return (
                f"bestvideo[vcodec^=avc1]{cap}+bestaudio[ext=m4a]"
                f"/best[ext=mp4][vcodec^=avc1]{cap}/bestvideo{cap}+bestaudio/best{cap}"
            )
        return f"bestvideo{cap}+bestaudio[ext=m4a]/bestvideo{cap}+bestaudio/best{cap}"
    if fmt == "webm":
        return (
            f"bestvideo[ext=webm]{cap}+bestaudio[ext=webm]"
            f"/best[ext=webm]{cap}/bestvideo{cap}+bestaudio/best{cap}"
        )
    return f"bestvideo{cap}+bestaudio/best{cap}"  # mkv


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


class _SetTitlePP(yt_dlp.postprocessor.PostProcessor):
    """Replaces the video's title with the person's own, before the file is named and tagged."""

    def __init__(self, title: str) -> None:
        super().__init__(None)
        self._title = title

    def run(self, info):
        info["title"] = self._title
        return [], info


def _template_text(value: str) -> str:
    """Make text safe to use as the default value inside a yt-dlp template."""
    return re.sub(r"[()|%\r\n]", " ", value).strip()


def _metadata_postprocessors(fmt: str, extra: dict | None, title: str | None = None) -> list[dict]:
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
        # MP3 and M4A covers are added afterwards by app.cover, which writes square art in
        # the ID3 version that car head units and Windows read.
        if fmt not in cover.COVER_FORMATS:
            processors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    return processors


_SPONSOR_CATEGORIES = {"sponsor", "selfpromo", "interaction"}
CHAPTER_PREFIX = "Chapter "


def _audio_selector(fmt: str) -> str:
    """Prefer a source that already is in the requested codec, so it can be copied unchanged."""
    if fmt in ("m4a", "aac"):
        return "bestaudio[ext=m4a]/bestaudio/best"
    if fmt == "opus":
        return "bestaudio[acodec=opus]/bestaudio/best"
    return "bestaudio/best"


def _build_options(
    fmt: str,
    quality: str,
    workdir: Path,
    extra: dict | None = None,
    mute: bool = False,
    features: features_mod.Features | None = None,
) -> dict:
    features = features or features_mod.Features()
    settings_now = settings.load()
    options = _base_options()
    options["outtmpl"] = str(workdir / "%(title).80s.%(ext)s")
    # Network hiccups are common (YouTube sometimes answers 403 for a moment), so retry.
    options["retries"] = 10
    options["fragment_retries"] = 10
    options["extractor_retries"] = 3
    # Fetch several pieces of a fragmented video (DASH or HLS) at the same time.
    options["concurrent_fragment_downloads"] = 4
    if settings_now["aria2c"] and aria2c_available() and not features.trimmed:
        options["external_downloader"] = {"default": "aria2c"}
        options["external_downloader_args"] = {
            "aria2c": ["-x", "8", "-s", "8", "-k", "1M", "--disable-ipv6=true"]
        }

    postprocessors: list[dict] = []
    if features.sponsorblock:
        postprocessors.append(
            {
                "key": "SponsorBlock",
                "categories": set(_SPONSOR_CATEGORIES),
                "when": "after_filter",
            }
        )

    if formats.is_audio(fmt):
        options["format"] = _audio_selector(fmt)
        convert = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": formats.AUDIO_FORMATS[fmt]["ytdlp_codec"],
        }
        if fmt not in formats.LOSSLESS_AUDIO:
            convert["preferredquality"] = quality
        postprocessors.append(convert)
    else:
        options["format"] = _video_selector(fmt, quality, mute)
        # Highest resolution, then frame rate. VP9 beats AV1 on a tie because it plays on more
        # devices.
        options["format_sort"] = ["res", "fps", "vcodec:vp9", "acodec"]
        if formats.is_preset(fmt):
            # Download into MKV (holds any codec); FFmpeg re-encodes it afterwards.
            options["merge_output_format"] = "mkv"
        else:
            options["merge_output_format"] = fmt
            # Re-mux only when the downloaded container differs from the request.
            postprocessors.append({"key": "FFmpegVideoConvertor", "preferedformat": fmt})
        if features.subtitles:
            options["writesubtitles"] = True
            options["writeautomaticsub"] = True
            options["subtitleslangs"] = list(features.subtitle_langs)
            postprocessors.append({"key": "FFmpegEmbedSubtitle"})

    if features.sponsorblock:
        postprocessors.append(
            {
                "key": "ModifyChapters",
                "remove_chapters_patterns": [],
                "remove_sponsor_segments": set(_SPONSOR_CATEGORIES),
                "remove_ranges": [],
                "force_keyframes": False,
            }
        )
    postprocessors += _metadata_postprocessors(fmt, extra)

    if features.split_chapters:
        options["outtmpl"] = {
            "default": str(workdir / "%(title).80s.%(ext)s"),
            "chapter": str(
                workdir / f"{CHAPTER_PREFIX}%(section_number)02d - %(section_title).80s.%(ext)s"
            ),
        }
        postprocessors.append({"key": "FFmpegSplitChapters", "force_keyframes": False})

    if features.trimmed:
        end = features.trim_end if features.trim_end is not None else float("inf")
        options["download_ranges"] = yt_dlp.utils.download_range_func(
            [], [(features.trim_start or 0.0, end)]
        )
        # Cut exactly where asked, not at the nearest keyframe.
        options["force_keyframes_at_cuts"] = True

    options["postprocessors"] = postprocessors
    if any(pp["key"] in ("EmbedThumbnail", "FFmpegThumbnailsConvertor") for pp in postprocessors):
        options["writethumbnail"] = True
    return options


ProgressCallback = Callable[[dict], None]


class _DownloadProgress:
    """Turns yt-dlp's per-stream progress into one percent, speed and time-left figure."""

    def __init__(self, callback: ProgressCallback) -> None:
        self.callback = callback
        self.finished_bytes = 0

    def download_hook(self, data: dict) -> None:
        try:
            self._handle(data)
        except Cancelled as exc:
            raise yt_dlp.utils.DownloadCancelled("Cancelled") from exc

    def _handle(self, data: dict) -> None:
        status = data.get("status")
        done = data.get("downloaded_bytes") or 0
        if status == "finished":
            self.finished_bytes += data.get("total_bytes") or done
            return
        if status != "downloading":
            return

        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        streams = (data.get("info_dict") or {}).get("requested_formats") or []
        sizes = [f.get("filesize") or f.get("filesize_approx") for f in streams]
        if streams and all(sizes):
            # Video and audio arrive as separate files: count both toward one total.
            grand_total, current = sum(sizes), self.finished_bytes + done
        else:
            grand_total, current = total, done

        speed = data.get("speed")
        percent = min(99.9, current / grand_total * 100) if grand_total else None
        if speed and grand_total:
            eta = max(0.0, (grand_total - current) / speed)
        else:
            eta = data.get("eta")
        self.callback({"phase": "downloading", "percent": percent, "speed": speed, "eta": eta})

    def processing_hook(self, data: dict) -> None:
        if data.get("status") == "started":
            try:
                self.callback({"phase": "processing", "percent": None})
            except Cancelled as exc:
                raise yt_dlp.utils.DownloadCancelled("Cancelled") from exc


def _find_output(workdir: Path, extension: str) -> Path:
    files = [
        p for p in workdir.iterdir() if p.is_file() and p.suffix not in {".part", ".ytdl", ".tmp"}
    ]
    if not files:
        raise ConversionError("Conversion finished but no file was produced.", "MF-TOOL-03")
    preferred = [p for p in files if p.suffix.lower() == f".{extension}"]
    return max(preferred or files, key=lambda p: p.stat().st_size)


DOWNLOAD_ATTEMPTS = 3


def _discard_partial_files(workdir: Path) -> None:
    for leftover in workdir.iterdir():
        if leftover.is_file():
            leftover.unlink(missing_ok=True)


def _add_cover(output: Path, workdir: Path, notes: list[str] | None) -> None:
    """Embed the downloaded thumbnail in an MP3 or M4A file, and report any problem."""
    image = cover.find_image(workdir)
    try:
        if image is None:
            raise cover.CoverError("the site did not provide a thumbnail")
        cover.embed_cover(output, image)
    except cover.CoverError as exc:
        if notes is not None:
            notes.append(f"Cover art could not be added: {exc}.")
    finally:
        for leftover in workdir.iterdir():
            if leftover != output and leftover.suffix.lower() in cover.IMAGE_SUFFIXES:
                leftover.unlink(missing_ok=True)


def _package_chapters(workdir: Path, title: str) -> Path | None:
    """Zip the per-chapter files yt-dlp wrote. Returns None when there were none."""
    pieces = sorted(
        p for p in workdir.iterdir() if p.is_file() and p.name.startswith(CHAPTER_PREFIX)
    )
    if not pieces:
        return None
    archive = workdir / f"{validators.safe_filename(title, default='chapters')} (chapters).zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        for piece in pieces:
            bundle.write(piece, arcname=piece.name)
    for leftover in workdir.iterdir():
        if leftover != archive and leftover.is_file():
            leftover.unlink(missing_ok=True)
    return archive


def download_and_convert(
    url: str,
    fmt: str,
    quality: str,
    workdir: Path,
    extra: dict | None = None,
    notes: list[str] | None = None,
    mute: bool = False,
    progress: ProgressCallback | None = None,
    features: features_mod.Features | None = None,
) -> Path:
    """Download `url`, convert it to `fmt`, and return the output file path.

    `extra` may carry {"album": playlist name, "track": position} for playlist items.
    `features` holds the optional extras (subtitles, trimming, loudness...).
    Problems that do not stop the download (such as missing cover art) are added to `notes`.
    `progress` receives dicts with phase, percent, speed and eta. It may raise `Cancelled`.
    """
    from . import transcoder  # imported here because transcoder imports this module

    features = features or features_mod.Features()
    notes = notes if notes is not None else []
    report = progress or (lambda update: None)
    if not ffmpeg_ready():
        raise ConversionError(FFMPEG_HELP, "MF-TOOL-01")

    report({"phase": "looking up", "percent": None})
    info = fetch_info(url)

    if info["is_live"]:
        raise ConversionError("Live streams can't be converted.", "MF-LIM-01")
    duration = info["duration"]
    if duration and features.trimmed:
        start = features.trim_start or 0.0
        if start >= duration:
            raise ConversionError("The start time is after the end of the video.")
        duration = min(duration, features.trim_end or duration) - start
    if duration and config.MAX_DURATION_SECONDS and duration > config.MAX_DURATION_SECONDS:
        limit_min = config.MAX_DURATION_SECONDS // 60
        raise ConversionError(
            f"This video is longer than the {limit_min}-minute limit.", "MF-LIM-02"
        )

    options = _build_options(fmt, quality, workdir, extra, mute and formats.is_video(fmt), features)
    tracker = _DownloadProgress(report)
    options["progress_hooks"] = [tracker.download_hook]
    options["postprocessor_hooks"] = [tracker.processing_hook]

    result: dict = {}
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        tracker.finished_bytes = 0
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                if features.title:
                    ydl.add_post_processor(_SetTitlePP(features.title), when="pre_process")
                result = ydl.extract_info(url, download=True) or {}
            break
        except yt_dlp.utils.DownloadCancelled as exc:
            raise Cancelled() from exc
        except yt_dlp.utils.YoutubeDLError as exc:
            message = _clean_error(exc)
            if "aria2c" in message.lower() and "external_downloader" in options:
                # aria2c failed (often a network quirk on this computer). The built-in
                # downloader is slower but reliable, so finish the job with it.
                options.pop("external_downloader")
                options.pop("external_downloader_args", None)
                report({"phase": "retrying", "percent": None})
                _discard_partial_files(workdir)
                continue
            if attempt < DOWNLOAD_ATTEMPTS and _is_transient(message):
                report({"phase": "retrying", "percent": None})
                _discard_partial_files(workdir)
                time.sleep(2 * attempt)
                continue
            raise _to_error(exc) from exc

    if features.subtitles and not result.get("requested_subtitles"):
        notes.append("This video has no subtitles in the chosen language.")
    if features.sponsorblock and "youtube" not in str(result.get("extractor", "")).lower():
        notes.append("Skipping sponsor segments only works for YouTube videos.")

    if features.split_chapters:
        if result.get("chapters"):
            archive = _package_chapters(workdir, result.get("title") or info["title"])
            if archive is not None:
                return archive
        notes.append("This video has no chapters, so it was not split.")

    if formats.is_preset(fmt):
        downloaded = _find_output(workdir, "mkv")
        output = transcoder.convert_file(
            downloaded, fmt, quality, workdir, mute, report, normalize=features.normalize
        )
        downloaded.unlink(missing_ok=True)
        return output

    output = _find_output(workdir, fmt)
    if mute and formats.is_video(fmt):
        transcoder.strip_audio(output)
    elif features.normalize:
        transcoder.normalize_loudness(output, fmt, quality, report)
    if fmt in cover.COVER_FORMATS:
        _add_cover(output, workdir, notes)
    return output
