import subprocess

import pytest

from app import downloader, main
from app.downloader import ConversionError
from tests.conftest import requires_ffmpeg


def _png(path, size="640x360"):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size={size}"]
        + ["-frames:v", "1", str(path)],
        check=True,
    )


class _Response:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


def _fake_ydl(monkeypatch, image_bytes, link="https://i.example/maxres.png"):
    info = {
        "title": "My: Video?",
        "thumbnails": [
            {"id": "big", "url": link, "width": 640, "height": 360},
            {"id": "small", "url": "https://i.example/small.jpg", "width": 320, "height": 180},
        ],
    }

    class FakeYDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            return info

        def urlopen(self, url):
            return _Response(image_bytes)

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)


def _size(path):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path)], capture_output=True, text=True
    )
    return result.stderr


@requires_ffmpeg
@pytest.mark.parametrize(("fmt", "codec"), [("jpg", "mjpeg"), ("png", "png"), ("webp", "webp")])
def test_thumbnail_can_be_saved_in_each_format(monkeypatch, tmp_path, fmt, codec):
    source = tmp_path / "src.png"
    _png(source)
    _fake_ydl(monkeypatch, source.read_bytes())
    work = tmp_path / "work"
    work.mkdir()

    output = downloader.download_thumbnail("https://e.com/v", "big", fmt, False, work)

    assert output.suffix == f".{fmt}"
    assert output.name.startswith("My Video - 640x360")
    assert f"Video: {codec}" in _size(output)
    assert [p.name for p in work.iterdir()] == [output.name]


@requires_ffmpeg
def test_thumbnail_can_be_cropped_to_a_square(monkeypatch, tmp_path):
    source = tmp_path / "src.png"
    _png(source)
    _fake_ydl(monkeypatch, source.read_bytes())
    work = tmp_path / "work"
    work.mkdir()

    output = downloader.download_thumbnail("https://e.com/v", "big", "jpg", True, work)

    assert "360x360" in _size(output)
    assert output.name.endswith("-square.jpg")


def test_same_format_is_saved_without_re_encoding(monkeypatch, tmp_path):
    _fake_ydl(monkeypatch, b"raw-bytes")
    output = downloader.download_thumbnail("https://e.com/v", "big", "png", False, tmp_path)
    assert output.read_bytes() == b"raw-bytes"


def test_unknown_size_or_format_is_rejected(monkeypatch, tmp_path):
    _fake_ydl(monkeypatch, b"x")
    with pytest.raises(ConversionError, match="not available"):
        downloader.download_thumbnail("https://e.com/v", "nope", "jpg", False, tmp_path)
    with pytest.raises(ValueError, match="Unsupported image format"):
        downloader.download_thumbnail("https://e.com/v", "big", "gif", False, tmp_path)


def test_thumbnail_endpoint(client, monkeypatch):
    def fake(url, thumb_id, fmt, square, workdir):
        output = workdir / f"Thumb.{fmt}"
        output.write_bytes(b"img")
        return output

    monkeypatch.setattr(main.downloader, "download_thumbnail", fake)
    response = client.post(
        "/api/thumbnail", json={"url": "https://e.com/v", "id": "big", "format": "png"}
    )
    assert response.status_code == 200
    assert response.content == b"img"
    assert 'filename="Thumb.png"' in response.headers["content-disposition"]
    assert client.post("/api/thumbnail", json={"url": "bad", "id": "x"}).status_code == 400
