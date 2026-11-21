"""Spatial sound: place a sound around the listener's head, or move it around.

On headphones the brain locates a sound from tiny differences between the ears. FFmpeg's
`sofalizer` filter applies a measured head model (an HRTF, stored in a SOFA file) to do exactly
that. A fixed position is one `sofalizer` pass. A moving sound is several fixed positions faded
in and out of each other over time, which is how a real orbit around the head is made.

Without the SOFA file or the filter, the orbit falls back to a simple left-right sweep
(`apulsator`), the effect used by most "8D audio" videos. The positions need the head model.

Every preset is described by plain data (`PRESETS`), and `filter_graph` turns one into an FFmpeg
audio filter string. Nothing here runs FFmpeg.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

SOFA_FILE = Path(__file__).resolve().parent / "data" / "hrtf.sofa"

MIN_SECONDS = 2.0
MAX_SECONDS = 60.0
DEFAULT_SECONDS = 8.0

# Level (dB) added by the head model. A mono source loses about 3 dB, a 5.1 upmix much more.
_GAIN_POSITION = 3
_GAIN_MOVIE = 12
_GAIN_MOVING = 7  # crossfading positions are a little quieter than one fixed position

# kind: "place" (one fixed spot), "orbit", "sweep", "room", "movie".
# rotation: degrees, 0 = straight ahead, positive = to the left. elevation: degrees above.
PRESETS: dict[str, dict] = {
    "orbit": {
        "label": "Orbit around your head (8D)",
        "hint": "The sound circles you. Set how long one turn takes.",
        "kind": "orbit",
        "speed": True,
    },
    "sweep": {
        "label": "Travel front to back",
        "hint": "The sound passes through your head, from in front to behind and back.",
        "kind": "sweep",
        "speed": True,
    },
    "front": {
        "label": "From the front",
        "hint": "Everything comes from straight ahead.",
        "kind": "place",
        "rotation": 0,
        "elevation": 0,
    },
    "behind": {
        "label": "From behind",
        "hint": "Everything comes from behind you.",
        "kind": "place",
        "rotation": 180,
        "elevation": 0,
    },
    "left": {
        "label": "From the left side",
        "hint": "Everything comes from your left.",
        "kind": "place",
        "rotation": 90,
        "elevation": 0,
    },
    "right": {
        "label": "From the right side",
        "hint": "Everything comes from your right.",
        "kind": "place",
        "rotation": -90,
        "elevation": 0,
    },
    "above": {
        "label": "From above",
        "hint": "Everything comes from above your head.",
        "kind": "place",
        "rotation": 0,
        "elevation": 60,
    },
    "room": {
        "label": "Speakers in a room",
        "hint": "Keeps the stereo picture, but as two speakers placed in front of you.",
        "kind": "room",
    },
    "movie": {
        "label": "Movie-style surround",
        "hint": (
            "A 5.1 film mix keeps its front, side and rear sound. A stereo file is spread into "
            "5.1 first, which is a guess."
        ),
        "kind": "movie",
    },
}

# Presets that work without the head model (a plain left-right sweep).
_WITHOUT_HRTF = {"orbit"}


def sofa_available() -> bool:
    return SOFA_FILE.is_file()


def _filter_path() -> str:
    """The SOFA file as a path FFmpeg's filter parser reads correctly, also on Windows.

    A colon (C:), a quote or a comma in the folder name would end the option early, so the file
    is copied to the temporary folder in that rare case.
    """
    path = SOFA_FILE
    text = path.as_posix()
    if any(ch in text for ch in "',;[]"):
        copy = Path(tempfile.gettempdir()) / "mediaforge-hrtf.sofa"
        if not copy.is_file() or copy.stat().st_size != path.stat().st_size:
            shutil.copyfile(path, copy)
        text = copy.as_posix()
    return "'" + text.replace(":", "\\:") + "'"


def availability(filters: set[str] | None) -> dict[str, bool]:
    """Which presets this FFmpeg can make. `filters` is None when its list could not be read."""
    unknown = not filters
    hrtf = sofa_available() and (unknown or "sofalizer" in filters)
    pulsator = unknown or "apulsator" in filters
    result = {}
    for name in PRESETS:
        ok = hrtf or (name in _WITHOUT_HRTF and pulsator)
        if name == "movie":
            ok = ok and (unknown or {"surround", "alimiter"} <= filters)
        result[name] = ok
    return result


def has_hrtf(filters: set[str] | None) -> bool:
    return sofa_available() and (not filters or "sofalizer" in filters)


def _weight_expr(position: int, count: int, seconds: float) -> str:
    """Volume of one of `count` evenly spaced positions at time t (triangular fade, sums to 1)."""
    return (
        f"max(0,1-abs(mod({count}*t/{seconds:g}-{position}+{count * 1.5:g},{count})-{count / 2:g}))"
    )


def _mono() -> str:
    return "aformat=channel_layouts=stereo,pan=mono|c0=0.5*c0+0.5*c1"


def _sofalizer(rotation: float, elevation: float, gain: float) -> str:
    return (
        f"sofalizer=sofa={_filter_path()}:rotation={rotation:g}:elevation={elevation:g}:"
        f"gain={gain:g}"
    )


def filter_graph(preset: str, seconds: float, channels: str | None, hrtf: bool = True) -> str:
    """The FFmpeg audio filters for one preset. `channels` is the source layout, if known."""
    spec = PRESETS[preset]
    kind = spec["kind"]

    if kind == "place":
        return f"{_mono()},{_sofalizer(spec['rotation'], spec['elevation'], _GAIN_POSITION)}"

    if kind == "room":
        return (
            f"aformat=channel_layouts=stereo,sofalizer=sofa={_filter_path()}:gain={_GAIN_POSITION}"
        )

    if kind == "movie":
        if channels in ("5.1", "7.1"):
            head = ""
        else:
            head = "aformat=channel_layouts=stereo,surround=chl_out=5.1,"
        return f"{head}sofalizer=sofa={_filter_path()}:gain={_GAIN_MOVIE},alimiter=limit=0.95"

    if kind == "orbit" and not hrtf:
        # Plain left-right sweep, like most "8D" videos: the two ears swell in turn.
        return (
            f"{_mono()},apulsator=mode=sine:hz={1 / seconds:g}:offset_l=0:offset_r=0.5:amount=1,"
            "aecho=0.8:0.7:45|70:0.2|0.12"
        )

    if kind == "orbit":
        count = 4
        angles = [0, 90, 180, 270]
        weights = [_weight_expr(i, count, seconds) for i in range(count)]
    else:  # sweep: front and behind, swapping smoothly
        count = 2
        angles = [0, 180]
        phase = f"0.5+0.5*cos(2*PI*t/{seconds:g})"
        weights = [phase, f"1-({phase})"]

    parts = [f"{_mono()},asplit={count}" + "".join(f"[s{i}]" for i in range(count))]
    for i, (angle, weight) in enumerate(zip(angles, weights, strict=True)):
        parts.append(
            f"[s{i}]{_sofalizer(angle, 0, _GAIN_MOVING)},volume='{weight}':eval=frame[p{i}]"
        )
    mix = "".join(f"[p{i}]" for i in range(count)) + f"amix=inputs={count}:normalize=0"
    return ";".join(parts) + ";" + mix + ",aecho=0.8:0.7:45|70:0.2|0.12"
