import shutil
import subprocess
from pathlib import Path

import pytest

from app import spatial, tweaks

ALL = {"sweep", "orbit", "front", "behind", "left", "right", "above", "room", "movie"}


def _filters(*names):
    return set(names)


def test_all_presets_exist():
    assert set(spatial.PRESETS) == ALL
    assert spatial.sofa_available()


def test_each_preset_builds_a_graph():
    for name in ALL:
        graph = spatial.filter_graph(name, 8, "stereo")
        assert graph
        assert "sofalizer" in graph


def test_orbit_has_four_positions_and_loops_by_seconds():
    graph = spatial.filter_graph("orbit", 6, "stereo")
    assert graph.count("sofalizer") == 4
    assert "asplit=4" in graph and "amix=inputs=4:normalize=0" in graph
    for angle in (0, 90, 180, 270):
        assert f"rotation={angle}:" in graph
    assert "4*t/6" in graph


def test_sweep_has_front_and_behind():
    graph = spatial.filter_graph("sweep", 10, "stereo")
    assert graph.count("sofalizer") == 2
    assert "rotation=0:" in graph and "rotation=180:" in graph
    assert "cos(2*PI*t/10)" in graph


def test_places_point_the_right_way():
    assert "rotation=90:" in spatial.filter_graph("left", 8, None)
    assert "rotation=-90:" in spatial.filter_graph("right", 8, None)
    assert "rotation=180:" in spatial.filter_graph("behind", 8, None)
    assert "elevation=60:" in spatial.filter_graph("above", 8, None)


def test_movie_keeps_a_5_1_source_and_upmixes_stereo():
    from_5_1 = spatial.filter_graph("movie", 8, "5.1")
    from_stereo = spatial.filter_graph("movie", 8, "stereo")
    assert "surround=" not in from_5_1
    assert "surround=chl_out=5.1" in from_stereo
    assert "surround=chl_out=5.1" in spatial.filter_graph("movie", 8, None)


def test_orbit_falls_back_to_a_plain_sweep_without_the_head_model():
    graph = spatial.filter_graph("orbit", 8, "stereo", hrtf=False)
    assert "apulsator" in graph and "sofalizer" not in graph
    assert "hz=0.125" in graph


def test_availability_follows_the_filters():
    assert all(spatial.availability({"sofalizer", "surround", "alimiter", "apulsator"}).values())
    only_pulsator = spatial.availability({"apulsator"})
    assert only_pulsator["orbit"] and not only_pulsator["front"]
    assert not spatial.availability({"sofalizer"})["movie"]
    assert all(spatial.availability(set()).values())  # list unreadable: nothing is hidden


def test_missing_sofa_file_blocks_positions(monkeypatch):
    monkeypatch.setattr(spatial, "SOFA_FILE", Path("/nonexistent/hrtf.sofa"))
    assert not spatial.availability({"sofalizer", "apulsator"})["front"]
    assert spatial.availability({"sofalizer", "apulsator"})["orbit"]
    with pytest.raises(ValueError, match="head model"):
        tweaks.parse({"spatial": "front"}, "mp3")


def test_windows_paths_are_escaped(monkeypatch):
    monkeypatch.setattr(spatial, "SOFA_FILE", Path("C:/Users/alwin/mediaforge/hrtf.sofa"))
    # Path.is_file is not called by _filter_path when no copy is needed
    assert spatial._filter_path() == "'C\\:/Users/alwin/mediaforge/hrtf.sofa'"


def test_parse_accepts_and_checks():
    t = tweaks.parse({"spatial": "orbit", "spatial_seconds": "12"}, "mp3")
    assert t.spatial == "orbit" and t.spatial_seconds == 12 and t.changes_sound
    assert tweaks.parse({"spatial": "front", "spatial_seconds": "12"}, "mp3").spatial_seconds == 8
    with pytest.raises(ValueError, match="Unknown spatial"):
        tweaks.parse({"spatial": "nope"}, "mp3")
    with pytest.raises(ValueError, match="Seconds per turn"):
        tweaks.parse({"spatial": "orbit", "spatial_seconds": "1"}, "mp3")
    with pytest.raises(ValueError, match="no sound"):
        tweaks.parse({"spatial": "orbit", "animated": "gif"}, "mp4")


def test_capabilities_and_description_list_spatial():
    desc = tweaks.describe()
    assert {p["id"] for p in desc["spatial"]} == ALL
    assert set(desc["capabilities"]["spatial"]) == ALL
    assert desc["spatial_seconds"]["default"] == 8.0


def test_the_command_carries_the_filters_and_channels():
    t = tweaks.parse({"spatial": "movie"}, "mp3")
    cmd = tweaks.build_command(
        Path("a.mkv"), Path("a.mp3"), "mp3", "192", t, ffmpeg="ffmpeg", duration=60, channels="5.1"
    )
    af = cmd[cmd.index("-af") + 1]
    assert "sofalizer" in af and "surround=" not in af


@pytest.mark.skipif(
    not shutil.which("ffmpeg")
    or "sofalizer"
    not in subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True
    ).stdout,
    reason="this FFmpeg has no sofalizer",
)
@pytest.mark.parametrize("name", sorted(ALL))
def test_real_ffmpeg_accepts_every_preset(name, tmp_path):
    source = tmp_path / "in.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=d=2",
            "-ac",
            "2",
            str(source),
        ],
        check=True,
    )
    t = tweaks.parse({"spatial": name, "spatial_seconds": "4"}, "wav")
    out = tmp_path / "out.wav"
    cmd = tweaks.build_command(
        source, out, "wav", "192", t, ffmpeg="ffmpeg", duration=2, channels="stereo"
    )
    run = subprocess.run(cmd, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert out.stat().st_size > 1000
