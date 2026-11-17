import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import config, jobs
from app.main import app

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="FFmpeg is not installed"
)


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    """A two-second test clip generated with FFmpeg (no external downloads)."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is not installed")
    path = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=15",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch, tmp_path):
    """Keep settings and history out of the real data folder, and skip the playlist pacing."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(jobs, "PACE_MIN", 0.0)
    monkeypatch.setattr(jobs, "PACE_MAX", 0.0)
