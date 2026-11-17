import time

import pytest
import yt_dlp
from yt_dlp.utils import DownloadError

from app import config, downloader, jobs, transcoder
from app.downloader import Cancelled, ConversionError
from tests.conftest import requires_ffmpeg
from tests.test_playlist import _items, _wait


def test_progress_combines_video_and_audio_into_one_figure():
    updates = []
    tracker = downloader._DownloadProgress(updates.append)
    streams = [{"filesize": 800}, {"filesize": 200}]

    tracker.download_hook(
        {
            "status": "downloading",
            "downloaded_bytes": 400,
            "total_bytes": 800,
            "speed": 100,
            "info_dict": {"requested_formats": streams},
        }
    )
    tracker.download_hook({"status": "finished", "downloaded_bytes": 800, "total_bytes": 800})
    tracker.download_hook(
        {
            "status": "downloading",
            "downloaded_bytes": 100,
            "total_bytes": 200,
            "speed": 50,
            "info_dict": {"requested_formats": streams},
        }
    )

    assert updates[0]["percent"] == pytest.approx(40)
    assert updates[0]["eta"] == pytest.approx(6)
    assert updates[1]["percent"] == pytest.approx(90)
    assert updates[1]["eta"] == pytest.approx(2)
    assert updates[1]["speed"] == 50


def test_progress_without_a_known_total_has_no_percent():
    updates = []
    tracker = downloader._DownloadProgress(updates.append)
    tracker.download_hook({"status": "downloading", "downloaded_bytes": 10, "eta": 5})
    assert updates == [{"phase": "downloading", "percent": None, "speed": None, "eta": 5}]


def test_cancelling_inside_a_hook_stops_yt_dlp():
    def stop(update):
        raise Cancelled()

    tracker = downloader._DownloadProgress(stop)
    with pytest.raises(yt_dlp.utils.DownloadCancelled):
        tracker.download_hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2})


class _FlakyYDL:
    failures: list[str] = []
    calls = 0

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        type(self).calls += 1
        if type(self).failures:
            raise DownloadError(type(self).failures.pop(0))
        (self.options["_dir"] / "Song.mp3").write_bytes(b"audio")
        return {}


@pytest.fixture
def flaky(monkeypatch, tmp_path):
    _FlakyYDL.calls = 0
    monkeypatch.setattr(downloader.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(downloader, "ffmpeg_ready", lambda: True)
    monkeypatch.setattr(
        downloader, "fetch_info", lambda url: {"is_live": False, "duration": 10, "title": "t"}
    )
    real_build = downloader._build_options

    def build(*args, **kwargs):
        options = real_build(*args, **kwargs)
        options["_dir"] = tmp_path
        return options

    monkeypatch.setattr(downloader, "_build_options", build)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", _FlakyYDL)
    monkeypatch.setattr(downloader, "_add_cover", lambda *args: None)
    return tmp_path


def test_a_403_is_retried_and_then_succeeds(flaky):
    _FlakyYDL.failures = ["ERROR: unable to download video data: HTTP Error 403: Forbidden"] * 2
    phases = []
    output = downloader.download_and_convert(
        "https://e.com/v", "mp3", "192", flaky, progress=phases.append
    )
    assert output.name == "Song.mp3"
    assert _FlakyYDL.calls == 3
    assert {"phase": "retrying", "percent": None} in phases


def test_a_persistent_403_gives_a_helpful_message(flaky):
    _FlakyYDL.failures = ["HTTP Error 403: Forbidden"] * 5
    with pytest.raises(ConversionError, match="update yt-dlp"):
        downloader.download_and_convert("https://e.com/v", "mp3", "192", flaky)
    assert _FlakyYDL.calls == downloader.DOWNLOAD_ATTEMPTS


def test_other_errors_are_not_retried(flaky):
    _FlakyYDL.failures = ["Video unavailable"]
    with pytest.raises(ConversionError, match="Video unavailable"):
        downloader.download_and_convert("https://e.com/v", "mp3", "192", flaky)
    assert _FlakyYDL.calls == 1


@requires_ffmpeg
def test_file_conversion_reports_progress(sample_video, tmp_path):
    updates = []
    transcoder.convert_file(sample_video, "mkv", "best", tmp_path, False, updates.append)
    assert updates[0] == {"phase": "converting", "percent": 0}
    percents = [u["percent"] for u in updates if u.get("percent")]
    assert percents and percents == sorted(percents) and max(percents) <= 99


@requires_ffmpeg
def test_file_conversion_can_be_cancelled(sample_video, tmp_path):
    def stop(update):
        if update.get("percent"):
            raise Cancelled()

    with pytest.raises(Cancelled):
        transcoder.convert_file(sample_video, "mkv", "best", tmp_path, False, stop)


@requires_ffmpeg
def test_media_duration(sample_video):
    assert transcoder.media_duration(sample_video) == pytest.approx(2.0, abs=0.6)


@pytest.fixture
def fake_download(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "downloads")

    def fake(
        url, fmt, quality, workdir, extra=None, notes=None, mute=False, progress=None, features=None
    ):
        progress({"phase": "downloading", "percent": 50.0, "speed": 1000.0, "eta": 3.0})
        if notes is not None:
            notes.append("Cover art could not be added: test.")
        output = workdir / "My Song.mp3"
        output.write_bytes(b"audio")
        return output

    monkeypatch.setattr(downloader, "download_and_convert", fake)


def test_single_link_job_keeps_the_file_for_the_browser(client, fake_download):
    created = client.post(
        "/api/jobs",
        json={
            "title": "My Song",
            "items": _items("https://e.com/a1"),
            "format": "mp3",
            "save_to_folder": False,
            "make_zip": False,
            "deliver_to_browser": True,
        },
    )
    assert created.status_code == 200
    job = _wait(created.json()["id"])

    status = client.get(f"/api/jobs/{job.id}").json()
    item = status["items"][0]
    assert item["status"] == "done" and item["downloadable"] is True
    assert item["note"] == "Cover art could not be added: test."
    assert status["folder"] is None

    first = client.get(f"/api/jobs/{job.id}/items/1/file")
    assert first.status_code == 200 and first.content == b"audio"
    assert "My%20Song.mp3" in first.headers["content-disposition"]
    time.sleep(0.2)  # the file is deleted once it has been sent
    assert client.get(f"/api/jobs/{job.id}/items/1/file").status_code == 404


def test_snapshot_shows_live_progress(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "downloads")
    seen = {}

    def slow(
        url, fmt, quality, workdir, extra=None, notes=None, mute=False, progress=None, features=None
    ):
        progress({"phase": "downloading", "percent": 42.0, "speed": 2e6, "eta": 12.0})
        deadline = time.time() + 3
        while "item" not in seen and time.time() < deadline:
            time.sleep(0.02)
        output = workdir / "x.mp3"
        output.write_bytes(b"a")
        return output

    monkeypatch.setattr(downloader, "download_and_convert", slow)
    job = jobs.start_job("P", _items("https://e.com/a1"), "mp3", "192", True, False)
    deadline = time.time() + 3
    while time.time() < deadline:
        item = jobs.snapshot(job)["items"][0]
        if item["percent"]:
            seen["item"] = item
            break
        time.sleep(0.02)
    _wait(job.id)

    assert seen["item"]["phase"] == "downloading"
    assert seen["item"]["percent"] == 42.0
    assert seen["item"]["speed"] == 2e6
    assert seen["item"]["eta"] == 12.0
    assert jobs.snapshot(job)["items"][0]["percent"] is None  # cleared when finished


def test_cancel_stops_a_running_download(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "downloads")
    started = []

    def endless(
        url, fmt, quality, workdir, extra=None, notes=None, mute=False, progress=None, features=None
    ):
        started.append(True)
        for _ in range(200):
            progress({"phase": "downloading", "percent": 1.0})
            time.sleep(0.02)
        raise AssertionError("was never cancelled")

    monkeypatch.setattr(downloader, "download_and_convert", endless)
    job = jobs.start_job("P", _items("https://e.com/a1"), "mp3", "192", True, False)
    while not started:
        time.sleep(0.01)
    jobs.cancel_job(job)
    job = _wait(job.id)
    assert job.status == "cancelled"
    assert job.items[0].status == "skipped"


@requires_ffmpeg
def test_uploaded_file_converts_in_the_background(client, sample_video):
    with sample_video.open("rb") as handle:
        created = client.post(
            "/api/jobs/upload",
            files={"file": ("clip.mp4", handle)},
            data={"format": "sony_avi", "mute": "true"},
        )
    assert created.status_code == 200
    job = _wait(created.json()["id"])
    item = jobs.snapshot(job)["items"][0]
    assert item["status"] == "done" and item["filename"] == "clip.avi"
    response = client.get(f"/api/jobs/{job.id}/items/1/file")
    assert response.status_code == 200 and len(response.content) > 1000


def test_upload_job_rejects_a_bad_format(client):
    response = client.post(
        "/api/jobs/upload", files={"file": ("a.mp4", b"x")}, data={"format": "exe"}
    )
    assert response.status_code == 400


def test_upload_job_rejects_empty_files(client):
    response = client.post(
        "/api/jobs/upload", files={"file": ("a.mp4", b"")}, data={"format": "mp3"}
    )
    assert response.status_code == 400
