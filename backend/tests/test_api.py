import shutil
from pathlib import Path

import pytest

from app import config, main
from app.downloader import ConversionError
from tests.conftest import requires_ffmpeg


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["ffmpeg"], bool)


def test_formats_endpoint(client):
    body = client.get("/api/formats").json()
    assert "mp3" in {f["id"] for f in body["audio"]}
    assert "mp4" in {f["id"] for f in body["video"]}
    assert body["limits"]["max_upload_mb"] == config.MAX_UPLOAD_MB


def test_info_returns_metadata(client, monkeypatch):
    monkeypatch.setattr(
        main.downloader,
        "fetch_info",
        lambda url: {
            "title": "Demo",
            "duration": 61,
            "uploader": "Me",
            "thumbnail": None,
            "is_live": False,
        },
    )
    response = client.post("/api/info", json={"url": "https://example.com/v"})
    assert response.status_code == 200
    assert response.json()["title"] == "Demo"


def test_info_rejects_bad_url(client):
    response = client.post("/api/info", json={"url": "ftp://example.com"})
    assert response.status_code == 400


def test_convert_url_streams_file_and_cleans_up(client, monkeypatch):
    workdirs = []

    def fake_download(url, fmt, quality, workdir):
        workdirs.append(workdir)
        output = workdir / f"Demo.{fmt}"
        output.write_bytes(b"fake-audio")
        return output

    monkeypatch.setattr(main.downloader, "download_and_convert", fake_download)
    response = client.post("/api/convert", json={"url": "https://example.com/v", "format": "mp3"})

    assert response.status_code == 200
    assert response.content == b"fake-audio"
    assert 'filename="Demo.mp3"' in response.headers["content-disposition"]
    assert not Path(workdirs[0]).exists()


def test_convert_url_reports_downloader_errors(client, monkeypatch):
    workdirs = []

    def failing_download(url, fmt, quality, workdir):
        workdirs.append(workdir)
        raise ConversionError("This video is longer than the 60-minute limit.")

    monkeypatch.setattr(main.downloader, "download_and_convert", failing_download)
    response = client.post("/api/convert", json={"url": "https://example.com/v", "format": "mp3"})

    assert response.status_code == 400
    assert "60-minute" in response.json()["detail"]
    assert not Path(workdirs[0]).exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "nope", "format": "mp3"},
        {"url": "https://example.com/v", "format": "exe"},
        {"url": "https://example.com/v", "format": "mp3", "quality": "9999"},
    ],
)
def test_convert_url_validates_input(client, payload):
    assert client.post("/api/convert", json=payload).status_code == 400


def test_convert_file_to_mp3(client, sample_video):
    with sample_video.open("rb") as handle:
        response = client.post(
            "/api/convert-file",
            files={"file": ("clip.mp4", handle, "video/mp4")},
            data={"format": "mp3", "quality": "128"},
        )
    assert response.status_code == 200
    assert 'filename="clip.mp3"' in response.headers["content-disposition"]
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content[:3] == b"ID3" or response.content[0] == 0xFF


@pytest.mark.parametrize("fmt", ["wav", "flac", "ogg", "opus", "m4a", "mp4", "webm", "mkv"])
def test_convert_file_other_formats(client, sample_video, fmt):
    with sample_video.open("rb") as handle:
        response = client.post(
            "/api/convert-file",
            files={"file": ("clip.mp4", handle, "video/mp4")},
            data={"format": fmt, "quality": "360" if fmt in {"mp4", "webm", "mkv"} else ""},
        )
    assert response.status_code == 200, response.text
    assert len(response.content) > 1000


def test_convert_file_rejects_empty_upload(client):
    response = client.post(
        "/api/convert-file",
        files={"file": ("empty.mp3", b"", "audio/mpeg")},
        data={"format": "wav"},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_convert_file_rejects_unknown_format(client):
    response = client.post(
        "/api/convert-file",
        files={"file": ("a.mp3", b"data", "audio/mpeg")},
        data={"format": "exe"},
    )
    assert response.status_code == 400


def test_convert_file_enforces_size_limit(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    response = client.post(
        "/api/convert-file",
        files={"file": ("a.mp3", b"some bytes", "audio/mpeg")},
        data={"format": "wav"},
    )
    assert response.status_code == 400
    assert "limit" in response.json()["detail"]


def test_convert_file_reports_ffmpeg_failure(client):
    response = client.post(
        "/api/convert-file",
        files={"file": ("notmedia.mp3", b"this is not audio at all", "audio/mpeg")},
        data={"format": "wav"},
    )
    assert response.status_code == 400
    assert "ffmpeg" in response.json()["detail"].lower()


def test_convert_url_explains_missing_ffmpeg(client, monkeypatch):
    monkeypatch.setattr(main.downloader.shutil, "which", lambda *args, **kwargs: None)
    response = client.post("/api/convert", json={"url": "https://example.com/v", "format": "mp4"})
    assert response.status_code == 400
    assert "FFmpeg was not found" in response.json()["detail"]


def _probe(path):
    """Describe the first video and audio streams using ffprobe."""
    import json
    import subprocess

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(result.stdout)["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    audio = next(s for s in streams if s["codec_type"] == "audio")
    return video, audio


@requires_ffmpeg
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is not installed")
@pytest.mark.parametrize(
    ("fmt", "suffix", "audio_codec"),
    [("sony_mp4", ".mp4", "aac"), ("sony_avi", ".avi", "mp3")],
)
def test_sony_presets_produce_playable_files(
    client, sample_video, tmp_path, fmt, suffix, audio_codec
):
    with sample_video.open("rb") as handle:
        response = client.post(
            "/api/convert-file", files={"file": ("clip.mp4", handle)}, data={"format": fmt}
        )
    assert response.status_code == 200
    output = tmp_path / f"out{suffix}"
    output.write_bytes(response.content)

    video, audio = _probe(output)
    assert video["codec_name"] == "mpeg4"
    assert video["profile"] == "Simple Profile"
    assert int(video["width"]) <= 720 and int(video["height"]) <= 576
    assert video["r_frame_rate"] == "30/1"
    assert audio["codec_name"] == audio_codec
    assert int(audio["channels"]) == 2
