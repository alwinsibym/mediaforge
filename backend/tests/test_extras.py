"""Optional extras, settings, history, parallel playlists and the sign-in check handling."""

import threading
import time
from pathlib import Path

import pytest

from app import config, downloader, features, history, jobs, settings, transcoder
from app.downloader import BotCheckError, ConversionError

# ---------- features ----------


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("80", 80), ("1:20", 80), ("1:02:03", 3723), ("0:05.5", 5.5), ("", None), (None, None)],
)
def test_timestamps(text, seconds):
    assert features.parse_timestamp(text) == seconds


@pytest.mark.parametrize("text", ["abc", "1:2:3:4", "-5", "1:xx"])
def test_bad_timestamps(text):
    with pytest.raises(ValueError, match="not a time"):
        features.parse_timestamp(text)


def test_trim_needs_a_later_end_and_one_video():
    with pytest.raises(ValueError, match="after the start"):
        features.parse({"trim_start": "2:00", "trim_end": "1:00"}, "mp3", single=True)
    with pytest.raises(ValueError, match="one video at a time"):
        features.parse({"trim_start": "0:10"}, "mp3", single=False)
    with pytest.raises(ValueError, match="one video at a time"):
        features.parse({"split_chapters": True}, "mp3", single=False)
    with pytest.raises(ValueError, match="car presets"):
        features.parse({"split_chapters": True}, "sony_mp4", single=True)


def test_subtitles_only_apply_to_normal_video():
    assert features.parse({"subtitles": True}, "mp3", single=True).subtitles is False
    assert features.parse({"subtitles": True}, "sony_mp4", single=True).subtitles is False
    wanted = features.parse({"subtitles": True, "subtitle_langs": "en, es"}, "mp4", single=True)
    assert wanted.subtitles and wanted.subtitle_langs == ("en", "es")


def test_subtitle_languages_are_checked():
    with pytest.raises(ValueError, match="language code"):
        features.parse({"subtitles": True, "subtitle_langs": "en;rm -rf"}, "mp4", single=True)


def test_default_features():
    assert features.parse({}, "mp3", single=True).is_default
    assert features.parse(None, "mp4", single=False).is_default


# ---------- settings and history ----------


def test_settings_defaults_and_save():
    assert settings.load()["parallel"] == 2
    saved = settings.save({"parallel": 3, "cookies_browser": "Firefox"})
    assert saved["parallel"] == 3 and saved["cookies_browser"] == "firefox"
    assert settings.load()["parallel"] == 3


def test_settings_reject_bad_values(tmp_path):
    with pytest.raises(ValueError, match="1 to 3"):
        settings.save({"parallel": 9})
    with pytest.raises(ValueError, match="listed browsers"):
        settings.save({"cookies_browser": "netscape"})
    with pytest.raises(ValueError, match="not found"):
        settings.save({"cookies_file": str(tmp_path / "missing.txt")})


def test_a_damaged_settings_file_gives_defaults():
    config.DATA_DIR.mkdir(parents=True)
    (config.DATA_DIR / "settings.json").write_text("{not json")
    assert settings.load()["parallel"] == 2


def test_history_keeps_newest_first_and_can_be_cleared():
    history.add("One", "https://e.com/1", "mp3", "192", "01 - One.mp3")
    history.add("Two", "https://e.com/2", "mp4", "1080", "02 - Two.mp4")
    titles = [entry["title"] for entry in history.recent()]
    assert titles == ["Two", "One"]
    history.clear()
    assert history.recent() == []


# ---------- download options ----------


def test_m4a_and_opus_prefer_a_source_that_can_be_copied():
    assert downloader._audio_selector("m4a").startswith("bestaudio[ext=m4a]")
    assert downloader._audio_selector("aac").startswith("bestaudio[ext=m4a]")
    assert downloader._audio_selector("opus").startswith("bestaudio[acodec=opus]")
    assert downloader._audio_selector("mp3") == "bestaudio/best"


def test_fragments_download_in_parallel():
    options = downloader._build_options("mp3", "192", Path("/tmp/x"))
    assert options["concurrent_fragment_downloads"] == 4
    assert "external_downloader" not in options


def test_aria2c_is_used_only_when_asked_and_installed(monkeypatch):
    settings.save({"aria2c": True})
    monkeypatch.setattr(downloader, "aria2c_available", lambda: False)
    assert "external_downloader" not in downloader._build_options("mp3", "192", Path("/tmp/x"))
    monkeypatch.setattr(downloader, "aria2c_available", lambda: True)
    options = downloader._build_options("mp3", "192", Path("/tmp/x"))
    assert options["external_downloader"] == {"default": "aria2c"}


def test_cookies_come_from_settings():
    assert "cookiesfrombrowser" not in downloader._base_options()
    settings.save({"cookies_browser": "firefox"})
    assert downloader._base_options()["cookiesfrombrowser"] == ("firefox",)
    cookie_file = config.DATA_DIR / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    settings.save({"cookies_file": str(cookie_file)})
    options = downloader._base_options()
    assert options["cookiefile"] == str(cookie_file) and "cookiesfrombrowser" not in options


def test_trim_sets_a_download_range_with_exact_cuts():
    extras = features.Features(trim_start=80, trim_end=225)
    options = downloader._build_options("mp3", "192", Path("/tmp/x"), features=extras)
    assert callable(options["download_ranges"])
    assert options["force_keyframes_at_cuts"] is True


def test_sponsorblock_runs_before_metadata_is_written():
    extras = features.Features(sponsorblock=True)
    keys = [
        pp["key"]
        for pp in downloader._build_options("mp3", "192", Path("/tmp/x"), features=extras)[
            "postprocessors"
        ]
    ]
    assert keys.index("ModifyChapters") < keys.index("FFmpegMetadata")
    assert keys.index("ModifyChapters") > keys.index("FFmpegExtractAudio")
    assert "SponsorBlock" in keys


def test_subtitles_are_embedded_for_video_only():
    extras = features.Features(subtitles=True, subtitle_langs=("en", "es"))
    video = downloader._build_options("mp4", "720", Path("/tmp/x"), features=extras)
    assert video["writesubtitles"] and video["subtitleslangs"] == ["en", "es"]
    assert any(pp["key"] == "FFmpegEmbedSubtitle" for pp in video["postprocessors"])
    audio = downloader._build_options("mp3", "192", Path("/tmp/x"), features=extras)
    assert "writesubtitles" not in audio


def test_chapter_splitting_adds_the_splitter_last():
    extras = features.Features(split_chapters=True)
    options = downloader._build_options("mp3", "192", Path("/tmp/x"), features=extras)
    assert options["postprocessors"][-1]["key"] == "FFmpegSplitChapters"
    assert downloader.CHAPTER_PREFIX in options["outtmpl"]["chapter"]


def test_chapter_files_are_zipped(tmp_path):
    (tmp_path / "Chapter 01 - A.mp3").write_bytes(b"a")
    (tmp_path / "Chapter 02 - B.mp3").write_bytes(b"b")
    (tmp_path / "Whole.mp3").write_bytes(b"w")
    archive = downloader._package_chapters(tmp_path, "My Mix")
    assert archive.name == "My Mix (chapters).zip"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["My Mix (chapters).zip"]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert downloader._package_chapters(empty, "x") is None


def test_trimmed_start_past_the_end_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader, "ffmpeg_ready", lambda: True)
    monkeypatch.setattr(
        downloader, "fetch_info", lambda url: {"is_live": False, "duration": 60, "title": "t"}
    )
    with pytest.raises(ConversionError, match="after the end"):
        downloader.download_and_convert(
            "https://e.com/v", "mp3", "192", tmp_path, features=features.Features(trim_start=90)
        )


def test_loudness_filter_is_added_unless_muted(tmp_path):
    source, target = tmp_path / "a.mp4", tmp_path / "b.mp3"
    loud = transcoder.build_command(source, target, "mp3", "192", normalize=True)
    assert transcoder.LOUDNORM in loud
    assert transcoder.LOUDNORM not in transcoder.build_command(source, target, "mp3", "192")
    muted = transcoder.build_command(source, tmp_path / "c.mp4", "mp4", "720", True, True)
    assert transcoder.LOUDNORM not in muted
    sony = transcoder.build_command(source, tmp_path / "d.mp4", "sony_mp4", "preset", False, True)
    assert transcoder.LOUDNORM in sony


# ---------- friendly errors ----------


def test_errors_are_explained():
    bot = downloader._friendly("Sign in to confirm you're not a bot")
    assert "Settings" in bot and "bot" in bot
    network = downloader._friendly("[Errno 11001] getaddrinfo failed")
    assert "could not reach that site" in network
    reddit = downloader._friendly("[Reddit] Account authentication is required")
    assert "signed in" in reddit
    assert "private" in downloader._friendly("Video is private")  # left as it was
    assert isinstance(
        downloader._to_error(Exception("Sign in to confirm you're not a bot")), BotCheckError
    )
    assert not isinstance(downloader._to_error(Exception("Video unavailable")), BotCheckError)


# ---------- playlists: parallel work and the sign-in check ----------


def _wait(job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get_job(job_id)
        if job.status in ("done", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _entries(count):
    return [{"title": f"Song {i}", "url": f"https://example.com/v{i}"} for i in range(1, count + 1)]


def _fake(monkeypatch, behaviour):
    def fake(
        url, fmt, quality, workdir, extra=None, notes=None, mute=False, progress=None, features=None
    ):
        behaviour(url)
        out = workdir / f"{url.rsplit('/', 1)[-1]}.mp3"
        out.write_bytes(b"x")
        return out

    monkeypatch.setattr(downloader, "download_and_convert", fake)


def test_playlist_items_download_at_the_same_time(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "dl")
    settings.save({"parallel": 3})
    running, peak, guard = 0, 0, threading.Lock()

    def behaviour(url):
        nonlocal running, peak
        with guard:
            running += 1
            peak = max(peak, running)
        time.sleep(0.15)
        with guard:
            running -= 1

    _fake(monkeypatch, behaviour)
    job = jobs.start_job("Mix", _entries(6), "mp3", "192", True, False)
    done = _wait(job.id)
    assert peak == 3
    assert all(item.status == "done" for item in done.items)
    names = sorted(p.name for p in done.folder.iterdir())
    assert [n[:2] for n in names] == ["01", "02", "03", "04", "05", "06"]


def test_one_at_a_time_when_set_to_one(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "dl")
    settings.save({"parallel": 1})
    running, peak = [0], [0]

    def behaviour(url):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        time.sleep(0.03)
        running[0] -= 1

    _fake(monkeypatch, behaviour)
    _wait(jobs.start_job("Mix", _entries(4), "mp3", "192", True, False).id)
    assert peak[0] == 1


def test_a_sign_in_check_is_waited_out_and_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "dl")
    monkeypatch.setattr(jobs, "BOT_CHECK_WAITS", (0, 0))
    attempts = {"n": 0}

    def behaviour(url):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise BotCheckError("YouTube is asking for a sign-in check")

    _fake(monkeypatch, behaviour)
    job = _wait(jobs.start_job("Mix", _entries(1), "mp3", "192", True, False).id)
    assert job.items[0].status == "done" and attempts["n"] == 2
    assert not job.blocked


def test_repeated_sign_in_checks_stop_the_job_for_a_later_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "dl")
    monkeypatch.setattr(jobs, "BOT_CHECK_WAITS", (0,))
    settings.save({"parallel": 1})

    def behaviour(url):
        raise BotCheckError("YouTube is asking for a sign-in check")

    _fake(monkeypatch, behaviour)
    job = _wait(jobs.start_job("Mix", _entries(6), "mp3", "192", True, False).id)
    statuses = [item.status for item in job.items]
    assert job.blocked
    assert statuses == ["failed", "failed", "skipped", "skipped", "skipped", "skipped"]
    assert "Retry" in job.items[3].error
    assert jobs.snapshot(job)["blocked"] is True


def test_retry_keeps_numbers_and_the_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "dl")
    _fake(monkeypatch, lambda url: None)
    first = _wait(jobs.start_job("Mix", _entries(2), "mp3", "192", True, False).id)
    retry_items = [{"title": "Song 7", "url": "https://example.com/v7", "number": 7}]
    again = _wait(
        jobs.start_job("Mix", retry_items, "mp3", "192", True, False, folder=first.folder).id
    )
    assert again.folder == first.folder
    assert any(p.name.startswith("07 - ") for p in first.folder.iterdir())


def test_finished_downloads_are_added_to_the_history(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "dl")
    _fake(monkeypatch, lambda url: None)
    _wait(jobs.start_job("Mix", _entries(2), "mp3", "192", True, False).id)
    assert {entry["url"] for entry in history.recent()} == {
        "https://example.com/v1",
        "https://example.com/v2",
    }


# ---------- API ----------


def test_settings_endpoints(client):
    body = client.get("/api/settings").json()
    assert body["parallel"] == 2 and "firefox" in body["cookie_browsers"]
    saved = client.post("/api/settings", json={"parallel": 3, "aria2c": True}).json()
    assert saved["parallel"] == 3 and saved["aria2c"] is True
    assert client.post("/api/settings", json={"parallel": 8}).status_code == 400


def test_history_endpoints(client):
    history.add("One", "https://e.com/1", "mp3", "192", "01 - One.mp3")
    assert client.get("/api/history").json()["items"][0]["title"] == "One"
    assert client.delete("/api/history").json()["items"] == []


def test_settings_are_local_only(client):
    from fastapi.testclient import TestClient

    from app.main import app

    remote = TestClient(app, client=("192.168.1.50", 5000))
    assert remote.get("/api/settings").status_code == 403
    assert remote.post("/api/update-ytdlp").status_code == 403
    assert remote.get("/api/history").status_code == 403


def test_update_endpoint(client, monkeypatch):
    from app import main

    class Done:
        returncode, stdout, stderr = 0, "", ""

    versions = iter(["2026.1.1", "2026.2.2"])
    monkeypatch.setattr(main, "_ytdlp_version", lambda: next(versions))
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: Done())
    body = client.post("/api/update-ytdlp").json()
    assert body == {"before": "2026.1.1", "after": "2026.2.2", "changed": True}


def test_update_failure_is_reported(client, monkeypatch):
    from app import main

    class Failed:
        returncode, stdout, stderr = 1, "", "ERROR: No matching distribution"

    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: Failed())
    response = client.post("/api/update-ytdlp")
    assert response.status_code == 400 and "update failed" in response.json()["detail"]


def test_job_request_checks_the_extras(client):
    base = {"items": [{"url": "https://e.com/a"}, {"url": "https://e.com/b"}], "format": "mp3"}
    response = client.post("/api/jobs", json={**base, "options": {"trim_start": "0:10"}})
    assert response.status_code == 400 and "one video" in response.json()["detail"]


# ---------- unreadable program output and lost connections ----------


def test_program_output_that_is_not_valid_text_does_not_break_cover_checks(tmp_path, monkeypatch):
    """FFmpeg can print bytes Windows' default text decoding rejects (seen as cp1252 errors)."""
    from app import cover, ffmpeg_locator

    script = tmp_path / "fake-ffmpeg"
    script.write_text("#!/bin/sh\nprintf 'title \\235 Stream #0:1: Video: mjpeg' >&2\n")
    script.chmod(0o755)
    monkeypatch.setattr(ffmpeg_locator, "find_tool", lambda name: str(script))
    assert cover.has_cover(tmp_path / "x.mp3") is True


def test_dns_failures_are_network_errors():
    error = downloader._to_error(Exception("[Errno 11001] getaddrinfo failed"))
    assert isinstance(error, downloader.NetworkError)
    assert "could not reach that site" in str(error)


def test_a_lost_connection_is_waited_out_and_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "dl")
    monkeypatch.setattr(jobs, "NETWORK_WAITS", (0, 0))
    attempts = {"n": 0}

    def behaviour(url):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise downloader.NetworkError("could not reach that site")

    _fake(monkeypatch, behaviour)
    job = _wait(jobs.start_job("Mix", _entries(1), "mp3", "192", True, False).id)
    assert job.items[0].status == "done" and attempts["n"] == 3
    assert not job.blocked


def test_a_long_outage_stops_the_job_for_a_later_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", tmp_path / "dl")
    monkeypatch.setattr(jobs, "NETWORK_WAITS", (0,))
    settings.save({"parallel": 1})

    def behaviour(url):
        raise downloader.NetworkError("could not reach that site")

    _fake(monkeypatch, behaviour)
    job = _wait(jobs.start_job("Mix", _entries(8), "mp3", "192", True, False).id)
    assert job.blocked and job.blocked_reason == "network"
    assert [item.status for item in job.items].count("failed") == 3
    assert [item.status for item in job.items].count("skipped") == 5
    assert "connection" in job.items[7].error


def test_a_closed_connection_is_retried_and_explained():
    message = "Unable to download webpage: ('Connection aborted.', ConnectionResetError(10054))"
    assert downloader._is_transient(message)
    assert "closed the connection" in downloader._friendly(message)


def test_browser_cookie_problems_are_explained():
    message = (
        "Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271"
    )
    text = downloader._friendly(message)
    assert "Firefox" in text and "cookies.txt" in text
