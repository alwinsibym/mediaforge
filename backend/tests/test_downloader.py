from pathlib import Path

from app import downloader


def test_js_runtimes_finds_binaries_next_to_python(tmp_path, monkeypatch):
    fake = tmp_path / "deno"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(downloader.sys, "executable", str(tmp_path / "python"))
    monkeypatch.setenv("PATH", "")

    found = downloader.js_runtimes()

    assert found == {"deno": {"path": str(fake)}}


def test_js_runtimes_empty_when_nothing_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader.sys, "executable", str(tmp_path / "python"))
    monkeypatch.setenv("PATH", "")
    assert downloader.js_runtimes() == {}


def test_base_options_pass_runtimes_to_ytdlp(monkeypatch):
    monkeypatch.setattr(downloader, "js_runtimes", lambda: {"node": {"path": "/usr/bin/node"}})
    assert downloader._base_options()["js_runtimes"] == {"node": {"path": "/usr/bin/node"}}


def test_audio_options_use_extract_audio():
    options = downloader._build_options("mp3", "192", Path("/tmp/x"))
    assert options["postprocessors"][0]["preferredcodec"] == "mp3"
    assert options["postprocessors"][0]["preferredquality"] == "192"


def test_lossless_audio_has_no_bitrate():
    options = downloader._build_options("flac", "192", Path("/tmp/x"))
    assert "preferredquality" not in options["postprocessors"][0]


def test_video_selector_caps_height():
    assert "[height<=720]" in downloader._video_selector("mp4", "720")
    assert "height" not in downloader._video_selector("mkv", "best")


def test_error_cleaning_strips_noise():
    raw = (
        "\x1b[0;31mERROR:\x1b[0m [youtube] abc: Video unavailable; "
        "please report this issue on github"
    )
    assert downloader._clean_error(Exception(raw)) == "[youtube] abc: Video unavailable"
