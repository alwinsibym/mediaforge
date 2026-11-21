import json

import pytest

from app import main, transcoder, tweaks
from tests.conftest import requires_ffmpeg


@requires_ffmpeg
def test_make_sample_estimates_the_whole_file(tmp_path, sample_video):
    result = transcoder.make_sample(sample_video, "mp4", "720", tmp_path)
    full = transcoder.media_duration(sample_video)
    assert result["path"].exists()
    assert result["sample_seconds"] <= transcoder.SAMPLE_SECONDS
    assert result["whole_seconds"] == pytest.approx(full, abs=0.2)
    assert result["estimated_bytes"] > 0 and result["estimated_seconds"] >= 0


@requires_ffmpeg
def test_sample_respects_a_size_target(tmp_path, sample_video):
    chosen = tweaks.parse({"target_mb": "0.5"}, "mp4")
    result = transcoder.make_sample(sample_video, "mp4", "720", tmp_path, tweaks=chosen)
    assert result["estimated_bytes"] == int(0.5 * 1024 * 1024)


@requires_ffmpeg
def test_sample_of_a_trimmed_range(tmp_path, sample_video):
    chosen = tweaks.parse({"start": "0.5", "end": "1.5"}, "mp4")
    result = transcoder.make_sample(sample_video, "mp4", "720", tmp_path, tweaks=chosen)
    assert result["whole_seconds"] == pytest.approx(1, abs=0.2)


@requires_ffmpeg
def test_api_sample_round_trip(client, sample_video):
    with sample_video.open("rb") as handle:
        response = client.post(
            "/api/sample",
            files={"file": ("clip.mp4", handle)},
            data={"format": "mp3", "quality": "128", "options": json.dumps({"volume": "120"})},
        )
    body = response.json()
    assert response.status_code == 200
    assert body["kind"] == "mp3" and body["estimated_bytes"] > 0
    fetched = client.get(body["url"])
    assert fetched.status_code == 200 and len(fetched.content) == body["sample_bytes"]


def test_api_sample_rejects_bad_tweaks(client):
    response = client.post(
        "/api/sample",
        files={"file": ("a.mp3", b"x")},
        data={"format": "mp3", "options": json.dumps({"video_codec": "h265"})},
    )
    assert response.status_code == 400


def test_api_sample_unknown_or_tampered_links_are_404(client):
    assert client.get("/api/sample/nope/x.mp4").status_code == 404
    main._SAMPLES["abc"] = (main.Path("/nonexistent"), 0)
    assert client.get("/api/sample/abc/..%2F..%2Fetc%2Fpasswd").status_code == 404
    main._SAMPLES.clear()


def test_api_sample_refuses_a_second_at_the_same_time(client):
    assert main._SAMPLE_LOCK.acquire(blocking=False)
    try:
        response = client.post(
            "/api/sample", files={"file": ("a.mp3", b"x")}, data={"format": "mp3"}
        )
        assert response.status_code == 400 and "already being made" in response.json()["detail"]
    finally:
        main._SAMPLE_LOCK.release()


def test_old_samples_are_cleaned_up(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()
    main._SAMPLES["old"] = (folder, 0)
    main._forget_old_samples()
    assert "old" not in main._SAMPLES and not folder.exists()
