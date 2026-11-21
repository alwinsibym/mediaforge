import json
import subprocess
import time

import pytest

from app import jobs, transcoder, tweaks
from tests.conftest import requires_ffmpeg

# ---------------------------------------------------------------- validation


def test_defaults_mean_no_tweaks():
    assert tweaks.parse({}, "mp4").is_default
    assert tweaks.parse(None, "mp3").is_default


@pytest.mark.parametrize(
    ("data", "fmt", "message"),
    [
        ({"video_codec": "h265"}, "mp3", "only applies"),
        ({"video_codec": "vp9"}, "mp4", "can be stored"),
        ({"video_codec": "nope"}, "mp4", "Unknown video codec"),
        ({"resize": "999"}, "mp4", "Resize to"),
        ({"resize": "720"}, "mp3", "only applies"),
        ({"volume": "900"}, "mp3", "between"),
        ({"fade_in": "abc"}, "mp3", "number"),
        ({"effect": "echo"}, "mp3", "Unknown sound effect"),
        ({"target_mb": "0.01"}, "mp4", "between"),
        ({"target_mb": "5"}, "wav", "lossless"),
        ({"subtitles": "burn"}, "mp4", "Choose a subtitle file"),
        ({"replace_audio": True}, "mp4", "Choose the audio file"),
        ({"strip_metadata": True, "title": "x"}, "mp4", "cannot be combined"),
        ({"start": "10", "end": "5"}, "mp4", "after the start"),
        ({"animated": "apng"}, "mp4", "GIF or WebP"),
        ({"resize": "720"}, "sony_avi", "Sony presets"),
    ],
)
def test_bad_choices_are_explained(data, fmt, message):
    with pytest.raises(ValueError, match=message):
        tweaks.parse(data, fmt)


def test_subtitle_file_defaults_to_a_soft_track():
    assert tweaks.parse({}, "mkv", subtitle_file=True).subtitles == "soft"


def test_audio_replacement_needs_a_video_output():
    with pytest.raises(ValueError, match="only applies"):
        tweaks.parse({}, "mp3", audio_file=True)


# ---------------------------------------------------------------- planning


def test_bitrate_plan_fits_the_target():
    video, audio = tweaks.plan_bitrates(100, 600, True)
    assert audio == 128
    assert (video + audio) * 600 / 8 / 1024 < 100


def test_bitrate_plan_refuses_a_hopeless_target():
    with pytest.raises(ValueError, match="too small"):
        tweaks.plan_bitrates(1, 7200, True)


def test_audio_bitrate_for_size():
    assert tweaks.audio_bitrate_for_size(5, 300) <= 320
    with pytest.raises(ValueError, match="too small"):
        tweaks.audio_bitrate_for_size(1, 36000)


def test_audio_filters_run_in_a_sensible_order():
    chain = tweaks.audio_filters(
        tweaks.parse({"effect": "bass", "volume": "150", "fade_in": "2", "fade_out": "3"}, "mp3"),
        True,
        60,
    )
    assert [c.split("=")[0] for c in chain] == ["bass", "volume", "loudnorm", "afade", "afade"]
    assert "st=57" in chain[-1]


def test_fade_out_longer_than_the_file_is_refused():
    with pytest.raises(ValueError, match="longer than the file"):
        tweaks.audio_filters(tweaks.parse({"fade_out": "30"}, "mp3"), False, 10)


def test_subtitle_names_never_reach_the_filter_from_the_person(tmp_path):
    command = tweaks.build_command(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        "mp4",
        "720",
        tweaks.parse({"subtitles": "burn"}, "mp4", subtitle_file=True),
        ffmpeg="ffmpeg",
        duration=10,
        subtitle_name="subtitles.srt",
    )
    assert "subtitles=subtitles.srt" in " ".join(command)


def test_capabilities_have_every_key():
    caps = tweaks.capabilities()
    assert set(caps) == {
        "video_codecs",
        "effects",
        "spatial",
        "spatial_hrtf",
        "subtitles_burn",
        "animated",
    }
    assert set(caps["video_codecs"]) == set(tweaks.VIDEO_CODECS)


# ---------------------------------------------------------------- real files


def _wait(job_id):
    job = jobs.get_job(job_id)
    for _ in range(300):
        if job.status in ("done", "cancelled"):
            break
        time.sleep(0.1)
    return job


def _info(path):
    return transcoder.probe(path)


@requires_ffmpeg
@pytest.mark.parametrize(
    ("fmt", "options", "codec"),
    [
        ("mp4", {"video_codec": "h265"}, "hevc"),
        ("webm", {"video_codec": "vp9"}, "vp9"),
        ("mkv", {"video_codec": "h264", "resize": "360"}, "h264"),
    ],
)
def test_codec_choices_are_used(tmp_path, sample_video, fmt, options, codec):
    if not tweaks.capabilities()["video_codecs"].get({"hevc": "h265"}.get(codec, codec), True):
        pytest.skip("encoder missing")
    out = transcoder.convert_file(
        sample_video, fmt, "720", tmp_path, tweaks=tweaks.parse(options, fmt)
    )
    assert _info(out)["video"][0]["codec"] == codec


@requires_ffmpeg
def test_resize_up(tmp_path, sample_video):
    out = transcoder.convert_file(
        sample_video, "mp4", "720", tmp_path, tweaks=tweaks.parse({"resize": "480"}, "mp4")
    )
    assert _info(out)["video"][0]["height"] == 480


@requires_ffmpeg
def test_audio_tweaks_make_an_mp3(tmp_path, sample_video):
    chosen = tweaks.parse(
        {"effect": "bass", "volume": "120", "fade_in": "0.5", "fade_out": "0.5"}, "mp3"
    )
    out = transcoder.convert_file(sample_video, "mp3", "192", tmp_path, tweaks=chosen)
    assert out.suffix == ".mp3" and _info(out)["audio"]


@requires_ffmpeg
def test_gif_and_webp(tmp_path, sample_video):
    gif = transcoder.convert_file(
        sample_video, "mp4", "720", tmp_path, tweaks=tweaks.parse({"animated": "gif"}, "mp4")
    )
    assert gif.suffix == ".gif" and _info(gif)["video"][0]["codec"] == "gif"
    if tweaks.capabilities()["animated"]["webp"]:
        webp = transcoder.convert_file(
            sample_video, "mp4", "720", tmp_path, tweaks=tweaks.parse({"animated": "webp"}, "mp4")
        )
        assert webp.suffix == ".webp"


@requires_ffmpeg
def test_long_clips_are_refused_for_gif(tmp_path, sample_video):
    long_clip = tmp_path / "long.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-stream_loop",
            "40",
            "-i",
            str(sample_video),
            "-c",
            "copy",
            str(long_clip),
        ],
        check=True,
    )
    with pytest.raises(Exception, match="short clips"):
        transcoder.convert_file(
            long_clip, "mp4", "720", tmp_path / "o", tweaks=tweaks.parse({"animated": "gif"}, "mp4")
        ) if (tmp_path / "o").mkdir() is None else None


@requires_ffmpeg
def test_size_target_is_met(tmp_path, sample_video):
    out = transcoder.convert_file(
        sample_video, "mp4", "720", tmp_path, tweaks=tweaks.parse({"target_mb": "0.5"}, "mp4")
    )
    assert out.stat().st_size <= 0.5 * 1024 * 1024


@requires_ffmpeg
def test_metadata_can_be_removed(tmp_path, sample_video):
    tagged = tmp_path / "tagged.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(sample_video),
            "-c",
            "copy",
            "-metadata",
            "title=Secret",
            "-metadata",
            "location=+10.0+20.0/",
            str(tagged),
        ],
        check=True,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = transcoder.convert_file(
        tagged, "mp4", "720", out_dir, tweaks=tweaks.parse({"strip_metadata": True}, "mp4")
    )
    text = subprocess.run(["ffmpeg", "-i", str(out)], capture_output=True, text=True).stderr
    assert "Secret" not in text and "location" not in text


@requires_ffmpeg
def test_subtitles_burn_and_soft(tmp_path, sample_video):
    srt = tmp_path / "x.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,500\nHello\n")
    for fmt, mode in (("mp4", "burn"), ("mkv", "soft")):
        out_dir = tmp_path / mode
        out_dir.mkdir()
        chosen = tweaks.parse({"subtitles": mode}, fmt, subtitle_file=True)
        out = transcoder.convert_file(
            sample_video, fmt, "720", out_dir, tweaks=chosen, subtitle_file=srt
        )
        assert out.exists()
        if mode == "soft":
            assert _info(out)["subtitles"]


@requires_ffmpeg
def test_audio_can_be_replaced(tmp_path, sample_video):
    other = tmp_path / "other.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=1",
            str(other),
        ],
        check=True,
    )
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    out = transcoder.convert_file(
        sample_video,
        "mp4",
        "720",
        out_dir,
        tweaks=tweaks.parse({}, "mp4", audio_file=True),
        audio_file=other,
    )
    assert _info(out)["audio"][0]["codec"] == "aac"


@requires_ffmpeg
def test_probe_reads_streams(sample_video):
    info = transcoder.probe(sample_video)
    assert info["video"][0]["codec"] == "h264" and info["video"][0]["width"] == 320
    assert info["audio"][0]["codec"] == "aac" and info["duration"] > 1


# ---------------------------------------------------------------- the API


@requires_ffmpeg
def test_api_upload_with_tweaks(client, sample_video):
    with sample_video.open("rb") as handle:
        created = client.post(
            "/api/jobs/upload",
            files={"file": ("clip.mp4", handle)},
            data={"format": "mp4", "options": json.dumps({"resize": "360", "volume": "80"})},
        )
    assert created.status_code == 200
    job = _wait(created.json()["id"])
    assert jobs.snapshot(job)["items"][0]["status"] == "done"


def test_api_rejects_bad_tweaks(client):
    for options in ("{not json", json.dumps({"video_codec": "h265"}), "[1]"):
        response = client.post(
            "/api/jobs/upload",
            files={"file": ("a.mp3", b"x")},
            data={"format": "mp3", "options": options},
        )
        assert response.status_code == 400


def test_api_rejects_a_wrong_subtitle_type(client):
    response = client.post(
        "/api/jobs/upload",
        files={"file": ("a.mp4", b"x"), "subtitle_file": ("s.exe", b"x")},
        data={"format": "mp4"},
    )
    assert response.status_code == 400


@requires_ffmpeg
def test_api_probe(client, sample_video):
    with sample_video.open("rb") as handle:
        response = client.post("/api/probe", files={"file": ("clip.mp4", handle)})
    body = response.json()
    assert response.status_code == 200 and body["video"] and body["size_bytes"] > 0


def test_formats_lists_tweaks(client):
    body = client.get("/api/formats").json()["tweaks"]
    assert 2160 in body["resize_heights"] and body["capabilities"]


def test_mute_and_replacement_audio_conflict():
    with pytest.raises(ValueError, match="not both"):
        tweaks.parse({"mute": True}, "mp4", audio_file=True)


def test_unreadable_ffmpeg_lists_keep_choices_enabled(monkeypatch):
    monkeypatch.setattr(tweaks, "_CAPS_CACHE", None)
    monkeypatch.setattr(tweaks.ffmpeg_locator, "find_tool", lambda name: "ffmpeg")
    monkeypatch.setattr(tweaks, "_listing", lambda ffmpeg, flag: "")
    caps = tweaks.capabilities()
    assert all(caps["effects"].values()) and all(caps["video_codecs"].values())
    assert tweaks._CAPS_CACHE is None  # not remembered, so the next request tries again


def test_a_missing_filter_is_greyed_out(monkeypatch):
    monkeypatch.setattr(tweaks, "_CAPS_CACHE", None)
    monkeypatch.setattr(tweaks.ffmpeg_locator, "find_tool", lambda name: "ffmpeg")
    filters = " T.. bass  A->A  Boost\n T. crossfeed  A->A  x\n"
    encoders = " V....D libx264  H.264\n"
    monkeypatch.setattr(
        tweaks, "_listing", lambda ffmpeg, flag: encoders if flag == "-encoders" else filters
    )
    caps = tweaks.capabilities()
    assert caps["effects"]["bass"] and not caps["effects"]["surround"]
    assert caps["video_codecs"]["h264"] and not caps["video_codecs"]["h265"]
    monkeypatch.setattr(tweaks, "_CAPS_CACHE", None)


def test_filter_lists_with_two_or_three_flag_characters_are_read(monkeypatch):
    """FFmpeg 9 prints two flag characters per filter, older builds print three."""
    monkeypatch.setattr(tweaks, "_CAPS_CACHE", None)
    monkeypatch.setattr(tweaks.ffmpeg_locator, "find_tool", lambda name: "ffmpeg")
    filters = (
        "Filters:\n  T.. = Timeline support\n"
        " T. crossfeed         A->A       Apply headphone crossfeed filter.\n"
        " .. earwax            A->A       Widen the stereo image.\n"
        " T.C subtitles        V->V       Render text subtitles.\n"
        " ... palettegen       V->V       Find the optimal palette.\n"
        " ... paletteuse       VV->V      Use a palette.\n"
    )
    encoders = " V....D libx264  H.264\n"
    monkeypatch.setattr(
        tweaks, "_listing", lambda ffmpeg, flag: encoders if flag == "-encoders" else filters
    )
    caps = tweaks.capabilities()
    assert caps["effects"]["crossfeed"] and caps["effects"]["surround"]
    assert not caps["effects"]["bass"]
    assert caps["subtitles_burn"] and caps["animated"]["gif"]
    monkeypatch.setattr(tweaks, "_CAPS_CACHE", None)


def test_cover_picture_rules():
    assert tweaks.parse({}, "mp3", cover_file=True).cover
    assert tweaks.parse({}, "mp4", cover_file=True).cover
    with pytest.raises(ValueError, match="cover picture"):
        tweaks.parse({}, "wav", cover_file=True)
    with pytest.raises(ValueError, match="cover picture"):
        tweaks.parse({"animated": "gif"}, "mp4", cover_file=True)
    with pytest.raises(ValueError, match="Sony presets"):
        tweaks.parse({}, "sony_avi", cover_file=True)


def _cover(tmp_path):
    cover = tmp_path / "cover.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=600x400",
            "-frames:v",
            "1",
            str(cover),
        ],
        check=True,
    )
    return cover


@requires_ffmpeg
@pytest.mark.parametrize("fmt", ["mp3", "m4a", "flac", "mp4", "mkv"])
def test_cover_picture_is_embedded(tmp_path, sample_video, fmt):
    cover = _cover(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = transcoder.convert_file(
        sample_video,
        fmt,
        "192" if fmt in ("mp3", "m4a") else "720",
        out_dir,
        tweaks=tweaks.parse({}, fmt, cover_file=True),
        cover_file=cover,
    )
    text = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(out)], capture_output=True, text=True
    ).stderr
    assert "attached pic" in text
    if fmt == "mp4":
        assert text.count("Video:") == 2  # the film and the cover


def test_api_rejects_a_wrong_cover_type(client):
    response = client.post(
        "/api/jobs/upload",
        files={"file": ("a.mp3", b"x"), "cover_file": ("c.exe", b"x")},
        data={"format": "mp3"},
    )
    assert response.status_code == 400


def test_page_is_not_cached_blindly(client):
    assert client.get("/").headers["cache-control"] == "no-cache"


@requires_ffmpeg
def test_api_upload_with_a_cover_picture(client, sample_video, tmp_path):
    cover = _cover(tmp_path)
    with sample_video.open("rb") as video, cover.open("rb") as picture:
        created = client.post(
            "/api/jobs/upload",
            files={"file": ("clip.mp4", video), "cover_file": ("cover.png", picture)},
            data={"format": "mp3", "quality": "192"},
        )
    assert created.status_code == 200
    job = _wait(created.json()["id"])
    assert jobs.snapshot(job)["items"][0]["status"] == "done"
