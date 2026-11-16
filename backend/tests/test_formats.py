import pytest

from app import formats


def test_audio_defaults():
    assert formats.normalize("MP3", None) == ("mp3", "192")


def test_video_defaults():
    assert formats.normalize("mp4", None) == ("mp4", "720")


def test_explicit_quality_is_kept():
    assert formats.normalize("flac", "320") == ("flac", "320")
    assert formats.normalize("webm", "best") == ("webm", "best")


@pytest.mark.parametrize("fmt", ["exe", "", "mp5", "../mp3"])
def test_unknown_format_rejected(fmt):
    with pytest.raises(ValueError):
        formats.normalize(fmt, None)


def test_bad_quality_rejected():
    with pytest.raises(ValueError):
        formats.normalize("mp3", "9999")
    with pytest.raises(ValueError):
        formats.normalize("mp4", "100")
    with pytest.raises(ValueError):
        formats.normalize("mp4", "9000")
    with pytest.raises(ValueError):
        formats.normalize("mp4", "1080@")
    with pytest.raises(ValueError):
        formats.normalize("mp4", "abc")


def test_video_quality_can_name_a_height_and_a_frame_rate():
    assert formats.normalize("mp4", "2160") == ("mp4", "2160")
    assert formats.normalize("mkv", "1440@30") == ("mkv", "1440@30")
    assert formats.normalize("webm", "best") == ("webm", "best")
    assert formats.normalize("mp4", "144") == ("mp4", "144")


def test_parse_quality():
    assert formats.parse_quality("1080") == (1080, None)
    assert formats.parse_quality("1440@30") == (1440, 30)
    assert formats.parse_quality("best") == (None, None)
    assert formats.parse_quality(None) == (None, None)


def test_catalogue_lists_every_format():
    catalogue = formats.describe()
    assert {f["id"] for f in catalogue["audio"]} == set(formats.AUDIO_FORMATS)
    assert {f["id"] for f in catalogue["video"]} == set(formats.VIDEO_FORMATS)


def test_sony_presets_have_fixed_quality():
    assert formats.normalize("sony_mp4", None) == ("sony_mp4", "preset")
    assert formats.normalize("sony_avi", "1080") == ("sony_avi", "preset")


def test_sony_presets_use_their_own_extension():
    assert formats.extension("sony_mp4") == "mp4"
    assert formats.extension("sony_avi") == "avi"
    assert formats.extension("mkv") == "mkv"


def test_catalogue_marks_presets():
    video = {item["id"]: item for item in formats.describe()["video"]}
    assert video["sony_mp4"]["preset"] is True
    assert video["mp4"]["preset"] is False
