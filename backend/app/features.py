"""Optional extras for one conversion: subtitles, trimming, loudness and so on."""

import re
from dataclasses import dataclass

from . import formats

_TIME_RE = re.compile(r"^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)$")
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?$")
MAX_SUBTITLE_LANGUAGES = 5
MAX_TITLE_LENGTH = 150


def parse_timestamp(text: str | None) -> float | None:
    """Turn '80', '1:20' or '1:02:03' into seconds. Empty text gives None."""
    text = (text or "").strip()
    if not text:
        return None
    match = _TIME_RE.match(text)
    if not match:
        raise ValueError(f"'{text}' is not a time. Use minutes and seconds, such as 1:20.")
    parts = [p for p in text.split(":")]
    if len(parts) > 3:
        raise ValueError(f"'{text}' is not a time. Use minutes and seconds, such as 1:20.")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


@dataclass(frozen=True)
class Features:
    normalize: bool = False  # even out the volume
    sponsorblock: bool = False  # cut sponsor and self-promotion segments
    subtitles: bool = False  # embed subtitles in the video
    subtitle_langs: tuple[str, ...] = ("en",)
    trim_start: float | None = None
    trim_end: float | None = None
    split_chapters: bool = False  # one file per chapter, delivered as a ZIP
    title: str | None = None  # a name of the person's own, for single links

    @property
    def trimmed(self) -> bool:
        return self.trim_start is not None or self.trim_end is not None

    @property
    def is_default(self) -> bool:
        return self == Features()


def _languages(value) -> tuple[str, ...]:
    if isinstance(value, str):
        value = value.split(",")
    langs = [str(v).strip() for v in (value or []) if str(v).strip()]
    if not langs:
        return ("en",)
    if len(langs) > MAX_SUBTITLE_LANGUAGES:
        raise ValueError(f"Choose at most {MAX_SUBTITLE_LANGUAGES} subtitle languages.")
    for lang in langs:
        if not _LANG_RE.match(lang):
            raise ValueError(f"'{lang}' is not a language code. Use codes such as en or es.")
    return tuple(langs)


def parse(data: dict | None, fmt: str, single: bool) -> Features:
    """Check the extras sent with a request. `single` is True for one link, False for playlists."""
    data = data or {}
    video = formats.is_video(fmt)
    preset = formats.is_preset(fmt)

    start = parse_timestamp(data.get("trim_start"))
    end = parse_timestamp(data.get("trim_end"))
    if (start is not None or end is not None) and not single:
        raise ValueError("Trimming works on one video at a time.")
    if start is not None and end is not None and end <= start:
        raise ValueError("The end time must be after the start time.")

    split = bool(data.get("split_chapters"))
    if split and not single:
        raise ValueError("Splitting by chapter works on one video at a time.")
    if split and preset:
        raise ValueError("Splitting by chapter is not available for the car presets.")

    title = re.sub(r"[\x00-\x1f\x7f]", " ", str(data.get("title") or "")).strip()
    if title and not single:
        raise ValueError("Renaming works on one video at a time.")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"Keep the title under {MAX_TITLE_LENGTH} characters.")

    wants_subtitles = bool(data.get("subtitles")) and video and not preset
    return Features(
        normalize=bool(data.get("normalize")),
        sponsorblock=bool(data.get("sponsorblock")),
        subtitles=wants_subtitles,
        subtitle_langs=_languages(data.get("subtitle_langs")) if wants_subtitles else ("en",),
        trim_start=start,
        trim_end=end,
        split_chapters=split,
        title=title or None,
    )
