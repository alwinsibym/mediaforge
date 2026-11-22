import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from app import main, paths, ytdlp_update
from app.downloader import ConversionError


def make_wheel(folder: str, version: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{folder}/__init__.py", "")
        if version:
            archive.writestr(f"{folder}/version.py", f"__version__ = '{version}'\n")
    return buffer.getvalue()


class FakePyPI:
    def __init__(self, version="2030.01.01", with_ejs=True, corrupt=False):
        self.wheels = {"https://files/yt_dlp.whl": make_wheel("yt_dlp", version)}
        self.pages = {
            "yt-dlp": self._page(version, "https://files/yt_dlp.whl", self.wheels, corrupt)
        }
        if with_ejs:
            self.wheels["https://files/ejs.whl"] = make_wheel("yt_dlp_ejs")
            self.pages["yt-dlp-ejs"] = self._page("0.9", "https://files/ejs.whl", self.wheels)
        self.calls = []

    @staticmethod
    def _page(version, url, wheels, corrupt=False):
        digest = hashlib.sha256(wheels[url]).hexdigest()
        if corrupt:
            digest = "0" * 64
        return {
            "info": {"version": version},
            "urls": [
                {
                    "packagetype": "bdist_wheel",
                    "filename": "x-py3-none-any.whl",
                    "url": url,
                    "digests": {"sha256": digest},
                }
            ],
        }

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self.wheels:
            return self.wheels[url]
        project = url.split("/pypi/")[1].split("/")[0]
        if project not in self.pages:
            raise ytdlp_update.UpdateError("not found")
        return json.dumps(self.pages[project]).encode()


def test_version_tuple_ignores_text():
    assert paths.version_tuple("2025.11.12") == (2025, 11, 12)
    assert paths.version_tuple("2025.11.12.post1") > paths.version_tuple("2025.11.12")
    assert paths.version_tuple("2026.1.1") > paths.version_tuple("2025.12.31")


def test_install_unpacks_both_packages(tmp_path):
    dest = tmp_path / "updates"
    result = ytdlp_update.install_latest(dest, current="2025.01.01", fetch=FakePyPI())
    assert result == {"before": "2025.01.01", "after": "2030.01.01", "changed": True}
    assert (dest / "yt_dlp" / "version.py").is_file()
    assert (dest / "yt_dlp_ejs" / "__init__.py").is_file()
    assert paths.updated_ytdlp_version(dest) == "2030.01.01"
    assert not list(tmp_path.glob("updates.*"))  # no staging or old folder left behind


def test_install_does_nothing_when_already_newest(tmp_path):
    result = ytdlp_update.install_latest(tmp_path / "u", current="2030.01.01", fetch=FakePyPI())
    assert result["changed"] is False
    assert not (tmp_path / "u").exists()


def test_the_helper_package_is_optional(tmp_path):
    ytdlp_update.install_latest(tmp_path / "u", current="2020.1.1", fetch=FakePyPI(with_ejs=False))
    assert (tmp_path / "u" / "yt_dlp").is_dir()


def test_a_wrong_checksum_is_refused_and_leaves_the_old_update(tmp_path):
    dest = tmp_path / "u"
    ytdlp_update.install_latest(dest, current="2020.1.1", fetch=FakePyPI("2029.01.01"))
    with pytest.raises(ytdlp_update.UpdateError, match="checksum"):
        ytdlp_update.install_latest(dest, current="2029.01.01", fetch=FakePyPI(corrupt=True))
    assert paths.updated_ytdlp_version(dest) == "2029.01.01"
    assert not (tmp_path / "u.new").exists()


def test_unsafe_paths_in_a_wheel_are_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("yt_dlp/../../evil.py", "x")
    with pytest.raises(ytdlp_update.UpdateError, match="unsafe"):
        ytdlp_update._unpack(buffer.getvalue(), "yt_dlp", tmp_path / "out")
    assert not (tmp_path / "evil.py").exists()


def test_a_wheel_without_the_folder_is_refused(tmp_path):
    with pytest.raises(ytdlp_update.UpdateError, match="no yt_dlp"):
        ytdlp_update._unpack(make_wheel("other"), "yt_dlp", tmp_path)


def test_updated_version_is_read_from_version_py(tmp_path):
    (tmp_path / "yt_dlp").mkdir()
    (tmp_path / "yt_dlp" / "version.py").write_text("__version__ = '2031.02.03'\n")
    assert paths.updated_ytdlp_version(tmp_path) == "2031.02.03"
    assert paths.updated_ytdlp_version(tmp_path / "missing") is None


def _frozen(monkeypatch, tmp_path, bundled="2025.01.01"):
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setenv("MEDIAFORGE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(paths, "bundled_ytdlp_version", lambda: bundled)
    monkeypatch.setattr(sys, "path", list(sys.path))


def _isolate_ytdlp(monkeypatch):
    """Hide the real yt-dlp so the test imports a fake one, and bring the real one back after."""
    for name in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
        monkeypatch.delitem(sys.modules, name)


def _update(tmp_path, version):
    folder = tmp_path / "data" / "updates" / "yt_dlp"
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("")
    (folder / "version.py").write_text(f"__version__ = '{version}'\n")
    return folder.parent


def test_an_older_update_is_deleted_at_start(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    update = _update(tmp_path, "2024.01.01")
    paths.use_updated_packages()
    assert not update.exists()
    assert str(update) not in sys.path


def test_a_newer_update_goes_first_on_the_path(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    update = _update(tmp_path, "2099.01.01")
    _isolate_ytdlp(monkeypatch)
    paths.use_updated_packages()
    assert sys.path[0] == str(update)
    assert update.exists()


def test_a_broken_update_is_removed(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path)
    update = _update(tmp_path, "2099.01.01")
    (update / "yt_dlp" / "__init__.py").write_text("raise RuntimeError('broken')")
    _isolate_ytdlp(monkeypatch)
    paths.use_updated_packages()
    assert not update.exists()
    assert str(update) not in sys.path


def test_not_frozen_never_touches_the_path(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "FROZEN", False)
    monkeypatch.setenv("MEDIAFORGE_DATA_DIR", str(tmp_path / "data"))
    update = _update(tmp_path, "2099.01.01")
    before = list(sys.path)
    paths.use_updated_packages()
    assert sys.path == before and update.exists()


def test_folders_default_next_to_the_program_when_packaged(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "MediaForge" / "MediaForge.exe"))
    monkeypatch.delenv("MEDIAFORGE_DATA_DIR", raising=False)
    assert paths.app_dir() == (tmp_path / "MediaForge").resolve()
    assert paths.data_dir() == (tmp_path / "MediaForge").resolve() / "data"
    assert paths.updates_dir().name == "updates"


def test_the_packaged_app_updates_without_pip(monkeypatch):
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(main, "_ytdlp_version", lambda: "2025.01.01")
    monkeypatch.setattr(
        ytdlp_update,
        "install_latest",
        lambda current=None: {"before": current, "after": "2030.01.01", "changed": True},
    )
    assert main._upgrade_ytdlp()["after"] == "2030.01.01"

    def fail(current=None):
        raise ytdlp_update.UpdateError("no internet")

    monkeypatch.setattr(ytdlp_update, "install_latest", fail)
    with pytest.raises(ConversionError, match="no internet"):
        main._upgrade_ytdlp()


def test_ffmpeg_install_needs_winget(monkeypatch):
    monkeypatch.setattr(main, "_winget", lambda: None)
    with pytest.raises(ConversionError, match="winget"):
        main._install_ffmpeg()


def test_ffmpeg_install_reports_success_and_failure(monkeypatch):
    monkeypatch.setattr(main, "_winget", lambda: "winget")

    class Done:
        def __init__(self, code, out=""):
            self.returncode, self.stdout, self.stderr = code, out, ""

    monkeypatch.setattr(main.downloader, "ffmpeg_ready", lambda: True)
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: Done(0))
    assert main._install_ffmpeg() == {"ok": True, "ffmpeg": True}

    monkeypatch.setattr(main.downloader, "ffmpeg_ready", lambda: False)
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: Done(1, "no network\nfailed"))
    with pytest.raises(ConversionError, match="failed"):
        main._install_ffmpeg()


def test_health_reports_packaging_flags():
    from fastapi.testclient import TestClient

    data = TestClient(main.app).get("/api/health").json()
    assert data["packaged"] is False
    assert "can_install_ffmpeg" in data


def test_bundled_version_missing_is_none(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "bundle_dir", lambda: Path(tmp_path))
    assert paths.bundled_ytdlp_version() is None
