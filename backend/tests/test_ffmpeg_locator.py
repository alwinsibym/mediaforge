import os
import shutil
import stat

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import FFmpegMergerPP

from app import downloader, ffmpeg_locator


def _fake_tool(folder, name):
    path = folder / name
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _isolate(monkeypatch, tmp_path):
    """Empty PATH and no installer folders, as on a PC with a stale PATH."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.delenv("MEDIAFORGE_FFMPEG_DIR", raising=False)
    monkeypatch.setattr(ffmpeg_locator, "known_install_dirs", lambda: [])


def test_not_found_when_nothing_installed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert ffmpeg_locator.find_tool("ffmpeg") is None
    assert ffmpeg_locator.ready() is False
    assert ffmpeg_locator.ytdlp_location() is None


def test_environment_variable_folder_is_used(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    tool = _fake_tool(tmp_path, "ffmpeg")
    monkeypatch.setenv("MEDIAFORGE_FFMPEG_DIR", f'"{tmp_path}"')  # quotes are tolerated
    assert ffmpeg_locator.find_tool("ffmpeg") == str(tool)
    assert ffmpeg_locator.ready() is True
    assert ffmpeg_locator.ytdlp_location() == str(tmp_path)


def test_known_install_folder_is_searched(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    bin_dir = tmp_path / "winget" / "bin"
    bin_dir.mkdir(parents=True)
    tool = _fake_tool(bin_dir, "ffmpeg")
    monkeypatch.setattr(ffmpeg_locator, "known_install_dirs", lambda: [bin_dir])
    assert ffmpeg_locator.find_tool("ffmpeg") == str(tool)


def test_ffprobe_is_not_required(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _fake_tool(tmp_path, "ffmpeg")
    monkeypatch.setenv("MEDIAFORGE_FFMPEG_DIR", str(tmp_path))
    assert ffmpeg_locator.ready() is True
    assert ffmpeg_locator.find_tool("ffprobe") is None


def test_winget_folders_are_discovered(monkeypatch, tmp_path):
    local = tmp_path / "Local"
    bin_dir = (
        local
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        / "ffmpeg-7.1-full_build"
        / "bin"
    )
    bin_dir.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    assert bin_dir in ffmpeg_locator.known_install_dirs()


def test_ytdlp_can_merge_when_path_is_stale(monkeypatch, tmp_path):
    """The real fix: yt-dlp gets the folder, so merging works without a PATH entry."""
    real = shutil.which("ffmpeg")  # look before the PATH is emptied
    if real is None:
        pytest.skip("FFmpeg is not installed")
    _isolate(monkeypatch, tmp_path)
    os.symlink(real, tmp_path / "ffmpeg")
    monkeypatch.setenv("MEDIAFORGE_FFMPEG_DIR", str(tmp_path))

    options = downloader._base_options()
    assert options["ffmpeg_location"] == str(tmp_path)
    with YoutubeDL({"quiet": True, **options}) as ydl:
        assert FFmpegMergerPP(ydl).available


def test_health_reports_ffmpeg_path(client, monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    tool = _fake_tool(tmp_path, "ffmpeg")
    monkeypatch.setenv("MEDIAFORGE_FFMPEG_DIR", str(tmp_path))
    body = client.get("/api/health").json()
    assert body["ffmpeg"] is True
    assert body["ffmpeg_path"] == str(tool)
