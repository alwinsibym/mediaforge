import subprocess
from pathlib import Path

import pytest
import yt_dlp

from app import downloader, transcoder
from tests.conftest import requires_ffmpeg


def _video(fid, height, fps, codec, ext):
    return {
        "format_id": fid,
        "url": f"http://example.com/{fid}",
        "ext": ext,
        "height": height,
        "width": int(height * 16 / 9),
        "fps": fps,
        "vcodec": codec,
        "acodec": "none",
        "protocol": "https",
        "filesize": 100 * height,
    }


def _audio(fid, codec, ext):
    return {
        "format_id": fid,
        "url": f"http://example.com/{fid}",
        "ext": ext,
        "vcodec": "none",
        "acodec": codec,
        "abr": 128,
        "protocol": "https",
        "filesize": 5000,
    }


# A made-up video that offers the same mix as a typical 4K YouTube upload.
FORMATS = [
    _video("h1080-30", 1080, 30, "avc1.640028", "mp4"),
    _video("h1080-60", 1080, 60, "avc1.64002a", "mp4"),
    _video("vp1080-60", 1080, 60, "vp09.00", "webm"),
    _video("vp1440-60", 1440, 60, "vp09.00", "webm"),
    _video("vp1440-30", 1440, 30, "vp09.00", "webm"),
    _video("av1440-30", 1440, 30, "av01.0", "mp4"),
    _video("vp2160-60", 2160, 60, "vp09.00", "webm"),
    _video("av2160-60", 2160, 60, "av01.0", "mp4"),
    _video("h720-30", 720, 30, "avc1.4d401f", "mp4"),
    _audio("a-m4a", "mp4a.40.2", "m4a"),
    _audio("a-opus", "opus", "webm"),
]


def _pick(fmt, quality, mute=False):
    options = downloader._build_options(fmt, quality, Path("/tmp/x"), None, mute)
    options = {k: v for k, v in options.items() if k in ("format", "format_sort")}
    options["quiet"] = True
    info = {
        "id": "x",
        "title": "t",
        "extractor": "generic",
        "extractor_key": "Generic",
        "_type": "video",
        "formats": [dict(f) for f in FORMATS],
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.process_ie_result(info, download=False)
    return [f["format_id"] for f in result.get("requested_formats") or [result]]


@pytest.mark.parametrize(
    ("fmt", "quality", "expected"),
    [
        ("mp4", "best", ["vp2160-60", "a-m4a"]),
        ("mp4", "2160", ["vp2160-60", "a-m4a"]),
        ("mp4", "1440", ["vp1440-60", "a-m4a"]),
        ("mp4", "1440@30", ["vp1440-30", "a-m4a"]),
        ("mp4", "1080", ["h1080-60", "a-m4a"]),
        ("mp4", "1080@30", ["h1080-30", "a-m4a"]),
        ("mp4", "720", ["h720-30", "a-m4a"]),
        ("mkv", "2160", ["vp2160-60", "a-opus"]),
        ("webm", "1440", ["vp1440-60", "a-opus"]),
    ],
)
def test_the_chosen_quality_picks_the_right_streams(fmt, quality, expected):
    assert _pick(fmt, quality) == expected


def test_a_cap_above_what_exists_never_upscales():
    assert _pick("mkv", "4320") == ["vp2160-60", "a-opus"]


@pytest.mark.parametrize(
    ("fmt", "quality", "expected"),
    [
        ("mp4", "1080", ["h1080-60"]),
        ("mp4", "2160", ["vp2160-60"]),
        ("webm", "1440", ["vp1440-60"]),
    ],
)
def test_video_only_downloads_skip_the_audio_stream(fmt, quality, expected):
    assert _pick(fmt, quality, mute=True) == expected


def test_qualities_list_what_the_video_really_offers():
    qualities = downloader._video_qualities(FORMATS)
    assert [q["id"] for q in qualities] == ["2160", "1440", "1440@30", "1080", "1080@30", "720"]
    assert qualities[0]["label"] == "2160p60 (4K)"
    assert qualities[2]["label"] == "1440p30 (2K)"
    assert qualities[-1]["label"] == "720p"
    assert qualities[0]["size"] == 100 * 2160 + 5000


def _sized(fid, width, height, fps=24):
    return {**_video(fid, height, fps, "vp9", "webm"), "width": width, "height": height}


def test_wide_film_frames_are_named_like_the_site_names_them():
    # A 2.39:1 film upload: YouTube lists these as 1080p, 1440p and 2160p (4K).
    formats = [_sized("a", 1920, 804), _sized("b", 2560, 1072), _sized("c", 3840, 1608)]
    qualities = downloader._video_qualities(formats)
    assert [q["label"] for q in qualities] == ["2160p (4K)", "1440p (2K)", "1080p"]
    # The id still follows the real height, so choosing it picks exactly that stream.
    assert [q["id"] for q in qualities] == ["1608", "1072", "804"]


def test_tall_videos_are_named_by_their_short_side():
    qualities = downloader._video_qualities([_sized("a", 1080, 1920, 30)])
    assert qualities[0]["label"] == "1080p"


def test_qualities_are_empty_without_video_streams():
    assert downloader._video_qualities([_audio("m4a", "aac", "m4a")]) == []


def test_thumbnail_options_list_each_size_once_largest_first():
    info = {
        "thumbnails": [
            {"id": "0", "url": "https://i.example/a.jpg", "width": 1280, "height": 720},
            {"id": "1", "url": "https://i.example/a.webp", "width": 1280, "height": 720},
            {"id": "2", "url": "https://i.example/b.jpg", "width": 640, "height": 480},
            {"id": "3", "url": "https://i.example/c.jpg"},
        ]
    }
    options = downloader._thumbnail_options(info)
    assert [o["label"] for o in options] == ["1280 x 720", "640 x 480"]


def test_thumbnail_options_fall_back_to_the_default_thumbnail():
    assert downloader._thumbnail_options({"thumbnail": "https://i.example/t.jpg"}) == [
        {"id": "default", "width": None, "height": None, "label": "Default size"}
    ]


def test_conversion_without_sound_drops_the_audio_options():
    command = transcoder.build_command(Path("in.mp4"), Path("out.mp4"), "mp4", "720", mute=True)
    assert "-an" in command and "aac" not in command
    sony = transcoder.build_command(Path("in.mp4"), Path("out.mp4"), "sony_mp4", "preset", True)
    assert "-an" in sony and "-b:a" not in sony and "0:a:0?" not in sony


@requires_ffmpeg
def test_strip_audio_keeps_the_picture(sample_video, tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(sample_video.read_bytes())
    transcoder.strip_audio(target)
    info = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(target)], capture_output=True, text=True
    ).stderr
    assert "Video:" in info and "Audio:" not in info


@requires_ffmpeg
def test_file_conversion_can_remove_the_sound(sample_video, tmp_path):
    output = transcoder.convert_file(sample_video, "sony_mp4", "preset", tmp_path, mute=True)
    info = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(output)], capture_output=True, text=True
    ).stderr
    assert "Video: mpeg4" in info and "Audio:" not in info
