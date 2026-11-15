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
        formats.normalize("mp4", "144")


def test_catalogue_lists_every_format():
    catalogue = formats.describe()
    assert {f["id"] for f in catalogue["audio"]} == set(formats.AUDIO_FORMATS)
    assert {f["id"] for f in catalogue["video"]} == set(formats.VIDEO_FORMATS)
