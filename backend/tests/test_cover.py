import subprocess

import pytest

from app import cover, downloader
from tests.conftest import requires_ffmpeg


def _make_audio(path):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=2"]
        + ["-metadata", "title=Test Song", "-metadata", "artist=Test Artist", str(path)],
        check=True,
    )


def _make_image(path, size="640x360"):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size={size}"]
        + ["-frames:v", "1", str(path)],
        check=True,
    )


def _streams(path):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path)], capture_output=True, text=True
    )
    return result.stderr


@requires_ffmpeg
@pytest.mark.parametrize("suffix", [".mp3", ".m4a"])
def test_embed_cover_adds_a_square_picture_and_keeps_tags(tmp_path, suffix):
    audio = tmp_path / f"song{suffix}"
    image = tmp_path / "thumb.png"
    _make_audio(audio)
    _make_image(image)

    cover.embed_cover(audio, image)

    info = _streams(audio)
    assert "Video: mjpeg" in info
    assert "360x360" in info
    assert "Test Artist" in info and "Test Song" in info
    assert not list(tmp_path.glob("*.cover.jpg")) and not list(tmp_path.glob("*.tagged*"))


@requires_ffmpeg
def test_mp3_cover_uses_id3_version_2_3(tmp_path):
    audio = tmp_path / "song.mp3"
    image = tmp_path / "thumb.png"
    _make_audio(audio)
    _make_image(image)
    cover.embed_cover(audio, image)
    assert audio.read_bytes()[:4] == b"ID3\x03"


@requires_ffmpeg
def test_small_images_are_not_enlarged(tmp_path):
    audio = tmp_path / "song.mp3"
    image = tmp_path / "thumb.png"
    _make_audio(audio)
    _make_image(image, "160x90")
    cover.embed_cover(audio, image)
    assert "90x90" in _streams(audio)


def test_embed_cover_rejects_unsupported_files(tmp_path):
    target = tmp_path / "song.flac"
    target.write_bytes(b"x")
    with pytest.raises(cover.CoverError):
        cover.embed_cover(target, tmp_path / "missing.jpg")


def test_find_image_picks_the_largest(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"1")
    (tmp_path / "b.png").write_bytes(b"123")
    (tmp_path / "song.mp3").write_bytes(b"12345")
    assert cover.find_image(tmp_path).name == "b.png"


def test_missing_thumbnail_becomes_a_note(tmp_path):
    output = tmp_path / "song.mp3"
    output.write_bytes(b"x")
    notes = []
    downloader._add_cover(output, tmp_path, notes)
    assert notes and "thumbnail" in notes[0]
    assert output.exists()


@requires_ffmpeg
def test_add_cover_removes_leftover_images(tmp_path):
    audio = tmp_path / "song.mp3"
    image = tmp_path / "song.jpg"
    _make_audio(audio)
    _make_image(image)
    notes = []
    downloader._add_cover(audio, tmp_path, notes)
    assert notes == []
    assert [p.name for p in tmp_path.iterdir()] == ["song.mp3"]
