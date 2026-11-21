import subprocess
from pathlib import Path

import pytest

from app import gpu, settings, transcoder, tweaks


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    gpu.reset()
    yield
    gpu.reset()


def _fake_runner(works: set[str]):
    def run(command, **kwargs):
        if "-c:v" not in command:  # nvidia-smi
            return subprocess.CompletedProcess(command, 0, stdout="NVIDIA Test Card\n", stderr="")
        encoder = command[command.index("-c:v") + 1]
        return subprocess.CompletedProcess(command, 0 if encoder in works else 1, b"", b"")

    return run


def test_detect_tests_each_encoder(monkeypatch):
    monkeypatch.setattr(gpu.ffmpeg_locator, "find_tool", lambda name: "ffmpeg")
    monkeypatch.setattr(gpu.subprocess, "run", _fake_runner({"h264_nvenc"}))
    found = gpu.detect(force=True)
    assert found["h264"] is True and found["h265"] is False
    assert found["name"] == "NVIDIA Test Card"


def test_detect_without_ffmpeg_is_all_false(monkeypatch):
    monkeypatch.setattr(gpu.ffmpeg_locator, "find_tool", lambda name: None)
    assert gpu.detect(force=True) == {"h264": False, "h265": False, "name": None}


def test_card_is_not_used_unless_turned_on(monkeypatch):
    monkeypatch.setattr(gpu, "detect", lambda force=False: {"h264": True, "h265": True})
    monkeypatch.setattr(settings, "load", lambda: {"gpu": False})
    assert gpu.enabled("h264") is False
    monkeypatch.setattr(settings, "load", lambda: {"gpu": True})
    assert gpu.enabled("h264") is True
    assert gpu.enabled("vp9") is False


def test_a_failure_switches_the_card_off_for_the_session(monkeypatch):
    monkeypatch.setattr(gpu, "detect", lambda force=False: {"h264": True, "h265": True})
    monkeypatch.setattr(settings, "load", lambda: {"gpu": True})
    gpu.disable("failed")
    assert gpu.enabled("h264") is False and gpu.disabled_reason() == "failed"
    gpu.reset()
    assert gpu.enabled("h264") is True


def test_arguments_for_quality_and_for_a_size_target():
    quality = gpu.args("h265", "mp4")
    assert quality[:2] == ["-c:v", "hevc_nvenc"] and "-cq" in quality and "hvc1" in quality
    sized = gpu.args("h264", "mkv", 1500)
    assert "-b:v" in sized and "1500k" in sized and "-cq" not in sized and "hvc1" not in sized


def test_commands_use_the_card_only_when_asked(tmp_path):
    plain = transcoder.build_command(Path("a.mp4"), tmp_path / "b.mp4", "mp4", "720")
    assert "libx264" in plain
    on_card = transcoder.build_command(
        Path("a.mp4"), tmp_path / "b.mp4", "mp4", "720", use_gpu=True
    )
    assert "h264_nvenc" in on_card and "libx264" not in on_card
    chosen = tweaks.parse({"video_codec": "h265"}, "mp4")
    assert "hevc_nvenc" in tweaks.video_args("mp4", chosen, "720", None, use_gpu=True)
    assert "libvpx-vp9" in tweaks.video_args(
        "webm", tweaks.parse({}, "webm"), "720", None, use_gpu=True
    )


def test_a_card_failure_falls_back_to_the_processor(monkeypatch, tmp_path, sample_video):
    if not transcoder.ffmpeg_available():
        pytest.skip("no ffmpeg")
    monkeypatch.setattr(gpu, "detect", lambda force=False: {"h264": True, "h265": True})
    monkeypatch.setattr(settings, "load", lambda: {"gpu": True})
    out = transcoder.convert_file(
        sample_video, "mp4", "720", tmp_path
    )  # no NVENC here, so it fails
    assert out.exists() and gpu.disabled_reason()


def test_settings_accept_the_switch():
    assert settings.validate({"gpu": 1}) == {"gpu": True}
    assert settings.DEFAULTS["gpu"] is False


def test_api_reports_and_retests_the_card(client, monkeypatch):
    monkeypatch.setattr(gpu.ffmpeg_locator, "find_tool", lambda name: None)
    body = client.get("/api/settings").json()
    assert body["gpu_card"]["h264"] is False and "turned_off" in body["gpu_card"]
    assert client.post("/api/gpu/test").json()["h264"] is False
