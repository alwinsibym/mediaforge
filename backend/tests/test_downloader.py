from pathlib import Path

import pytest

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


def test_download_fails_early_without_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader.shutil, "which", lambda *args, **kwargs: None)
    # fetch_info must not be reached (no network needed to report the problem).
    monkeypatch.setattr(
        downloader, "fetch_info", lambda url: pytest.fail("should fail before any network call")
    )
    with pytest.raises(downloader.ConversionError, match="FFmpeg was not found"):
        downloader.download_and_convert("https://example.com/v", "mp4", "1080", tmp_path)


def test_preset_downloads_small_and_merges_to_mkv():
    options = downloader._build_options("sony_mp4", "preset", Path("/tmp/x"))
    assert "height<=576" in options["format"]
    assert options["merge_output_format"] == "mkv"
    assert "postprocessors" not in options or not any(
        pp.get("key") == "FFmpegVideoConvertor" for pp in options["postprocessors"]
    )


def test_preset_output_is_reencoded_for_the_car(monkeypatch, tmp_path):
    calls = {}

    class FakeYDL:
        def __init__(self, options):
            calls["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def download(self, urls):
            (tmp_path / "Song.mkv").write_bytes(b"video")

    def fake_convert(source, fmt, quality, workdir):
        calls["convert"] = (source.name, fmt, quality)
        target = workdir / "Song.mp4"
        target.write_bytes(b"car")
        return target

    from app import transcoder

    monkeypatch.setattr(downloader, "ffmpeg_ready", lambda: True)
    monkeypatch.setattr(downloader, "fetch_info", lambda url: {"is_live": False, "duration": 10})
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(transcoder, "convert_file", fake_convert)

    output = downloader.download_and_convert("https://e.com/v", "sony_mp4", "preset", tmp_path)

    assert output.name == "Song.mp4"
    assert calls["convert"] == ("Song.mkv", "sony_mp4", "preset")
    assert not (tmp_path / "Song.mkv").exists()


def _keys(options):
    return [pp["key"] for pp in options.get("postprocessors", [])]


def test_mp3_gets_metadata_and_cover_art():
    options = downloader._build_options("mp3", "192", Path("/tmp/x"))
    assert _keys(options) == [
        "FFmpegExtractAudio",
        "FFmpegMetadata",
        "FFmpegThumbnailsConvertor",
        "EmbedThumbnail",
    ]
    assert options["writethumbnail"] is True


def test_formats_that_cannot_hold_a_cover_skip_it():
    for fmt in ("wav", "aac"):
        options = downloader._build_options(fmt, "192", Path("/tmp/x"))
        assert "EmbedThumbnail" not in _keys(options)
        assert "FFmpegMetadata" in _keys(options)
        assert not options.get("writethumbnail")


def test_video_keeps_metadata_but_presets_skip_the_cover():
    assert "EmbedThumbnail" in _keys(downloader._build_options("mp4", "720", Path("/tmp/x")))
    preset = downloader._build_options("sony_mp4", "preset", Path("/tmp/x"))
    assert "EmbedThumbnail" not in _keys(preset)
    assert "FFmpegMetadata" in _keys(preset)


def test_ogg_family_needs_mutagen_for_covers(monkeypatch):
    monkeypatch.setattr(downloader.importlib.util, "find_spec", lambda name: None)
    assert not downloader._can_embed_cover("opus")
    assert downloader._can_embed_cover("mp3")


def test_playlist_name_and_position_become_album_and_track():
    extra = {"album": "Road (Trip) | 2026 %", "track": 4}
    options = downloader._build_options("mp3", "192", Path("/tmp/x"), extra)
    parser = next(pp for pp in options["postprocessors"] if pp["key"] == "MetadataParser")
    templates = [action[1] for action in parser["actions"]]
    assert templates == ["%(album|Road  Trip    2026)s", "%(track_number|4)s"]
    assert [action[2] for action in parser["actions"]] == ["%(album)s", "%(track_number)s"]
