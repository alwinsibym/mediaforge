import time
import zipfile
from pathlib import Path

import pytest

from app import config, downloader, jobs
from app.downloader import ConversionError


def _wait(job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get_job(job_id)
        if job.status in ("done", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


@pytest.fixture
def fake_download(monkeypatch, tmp_path):
    """Replace the real download with one that writes a small file."""
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "downloads")
    calls = []

    def fake(url, fmt, quality, workdir, extra=None, notes=None, mute=False):
        calls.append((url, fmt, quality, extra, mute))
        if "bad" in url:
            raise ConversionError("This video is private.")
        output = workdir / f"Song {url[-1]}.mp3"
        output.write_bytes(b"audio")
        return output

    monkeypatch.setattr(downloader, "download_and_convert", fake)
    return calls


def _items(*urls):
    return [{"title": f"Video {i}", "url": url} for i, url in enumerate(urls, start=1)]


def test_job_saves_files_to_a_folder_with_track_numbers(fake_download, tmp_path):
    job = jobs.start_job(
        "Road Trip", _items("https://e.com/a1", "https://e.com/a2"), "mp3", "192", True, False
    )
    job = _wait(job.id)

    assert job.status == "done"
    assert sorted(p.name for p in (tmp_path / "downloads" / "Road Trip").iterdir()) == [
        "01 - Song 1.mp3",
        "02 - Song 2.mp3",
    ]
    assert fake_download[0][3] == {"album": "Road Trip", "track": 1}
    assert fake_download[1][3] == {"album": "Road Trip", "track": 2}
    assert jobs.snapshot(job)["folder"].endswith("Road Trip")
    assert jobs.snapshot(job)["zip_ready"] is False


def test_job_can_make_a_zip_and_keep_the_folder(fake_download):
    job = jobs.start_job("Mix", _items("https://e.com/a1"), "mp3", "192", True, True)
    job = _wait(job.id)

    assert jobs.snapshot(job)["zip_ready"] is True
    with zipfile.ZipFile(job.zip_path) as bundle:
        assert bundle.namelist() == ["01 - Song 1.mp3"]
    assert (job.folder / "01 - Song 1.mp3").exists()


def test_zip_only_job_leaves_no_folder_behind(fake_download, tmp_path):
    job = jobs.start_job("Only Zip", _items("https://e.com/a1"), "mp3", "192", False, True)
    job = _wait(job.id)

    assert job.folder is None
    assert not (tmp_path / "downloads").exists()
    assert jobs.snapshot(job)["zip_ready"] is True
    assert not (job.staging / "files").exists()


def test_failed_videos_do_not_stop_the_rest(fake_download):
    job = jobs.start_job(
        "Mixed", _items("https://e.com/bad", "https://e.com/a2"), "mp3", "192", True, False
    )
    job = _wait(job.id)

    states = [item.status for item in job.items]
    assert states == ["failed", "done"]
    assert job.items[0].error == "This video is private."
    assert jobs.snapshot(job)["done"] == 1
    assert jobs.snapshot(job)["failed"] == 1


def test_existing_folder_is_not_overwritten(fake_download, tmp_path):
    (tmp_path / "downloads" / "Same").mkdir(parents=True)
    job = jobs.start_job("Same", _items("https://e.com/a1"), "mp3", "192", True, False)
    job = _wait(job.id)
    assert job.folder.name == "Same (2)"


def test_cancel_skips_the_remaining_videos(monkeypatch, fake_download):
    original = downloader.download_and_convert

    def slow(*args, **kwargs):
        time.sleep(0.3)
        return original(*args, **kwargs)

    monkeypatch.setattr(downloader, "download_and_convert", slow)
    job = jobs.start_job(
        "Cancel",
        _items("https://e.com/a1", "https://e.com/a2", "https://e.com/a3"),
        "mp3",
        "192",
        True,
        False,
    )
    jobs.cancel_job(job)
    job = _wait(job.id)

    assert job.status == "cancelled"
    assert "skipped" in [item.status for item in job.items]


@pytest.mark.parametrize(
    ("items", "folder", "zip_", "message"),
    [
        (_items("https://e.com/a"), False, False, "at least one way"),
        ([], True, False, "at least one video"),
    ],
)
def test_job_requests_are_validated(items, folder, zip_, message):
    with pytest.raises(ValueError, match=message):
        jobs.start_job("x", items, "mp3", "192", folder, zip_)


def test_job_rejects_bad_urls():
    with pytest.raises(ValueError):
        jobs.start_job(
            "x", [{"title": "t", "url": "file:///etc/passwd"}], "mp3", "192", True, False
        )


class _FakeYDL:
    info: dict = {}

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return self.info


def test_fetch_playlist_lists_playable_videos(monkeypatch):
    _FakeYDL.info = {
        "_type": "playlist",
        "title": "Favourites",
        "uploader": "Me",
        "entries": [
            {
                "id": "abc",
                "title": "One",
                "url": "https://www.youtube.com/watch?v=abc",
                "duration": 90,
            },
            {"id": "def", "title": "Two", "url": "def"},
            {"id": "ghi", "title": "[Private video]", "url": None},
            None,
        ],
    }
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", _FakeYDL)

    result = downloader.fetch_playlist("https://www.youtube.com/playlist?list=PL1")

    assert result["title"] == "Favourites"
    assert [e["index"] for e in result["entries"]] == [1, 2]
    assert result["entries"][1]["url"] == "https://www.youtube.com/watch?v=def"


def test_fetch_playlist_rejects_single_videos(monkeypatch):
    _FakeYDL.info = {"_type": "video", "title": "Solo"}
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", _FakeYDL)
    with pytest.raises(ConversionError, match="not a playlist"):
        downloader.fetch_playlist("https://www.youtube.com/watch?v=abc")


def test_playlist_endpoints(client, fake_download, monkeypatch):
    monkeypatch.setattr(
        downloader,
        "fetch_playlist",
        lambda url: {
            "title": "PL",
            "entries": [{"index": 1, "title": "t", "url": "https://e.com/a1"}],
        },
    )
    assert (
        client.post("/api/playlist/info", json={"url": "https://e.com/pl"}).json()["title"] == "PL"
    )
    assert client.post("/api/playlist/info", json={"url": "nope"}).status_code == 400

    body = {
        "title": "PL",
        "items": [{"title": "t", "url": "https://e.com/a1"}],
        "format": "sony_mp4",
        "mute": True,
        "save_to_folder": False,
        "make_zip": True,
    }
    created = client.post("/api/jobs", json=body)
    assert created.status_code == 200
    job_id = created.json()["id"]
    _wait(job_id)

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "done" and status["zip_ready"] is True
    assert fake_download[0][1:3] == ("sony_mp4", "preset")
    assert fake_download[0][4] is True
    assert client.get(f"/api/jobs/{job_id}/zip").status_code == 200
    assert client.get("/api/jobs/missing").status_code == 404
    assert (
        client.post(
            "/api/jobs", json={**body, "save_to_folder": False, "make_zip": False}
        ).status_code
        == 400
    )
    assert Path(status["items"][0]["filename"]).suffix == ".mp3"


def test_open_folder_is_refused_for_other_devices(fake_download):
    from fastapi.testclient import TestClient

    from app import main

    job = jobs.start_job("Away", _items("https://e.com/a1"), "mp3", "192", True, False)
    _wait(job.id)
    remote = TestClient(main.app, client=("192.168.1.50", 5000))
    response = remote.post(f"/api/jobs/{job.id}/open-folder")
    assert response.status_code == 403
    assert "computer running MediaForge" in response.json()["detail"]
