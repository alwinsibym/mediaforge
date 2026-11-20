import http.server
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import launcher, runtime
from app.main import app

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import create_shortcut  # noqa: E402


class _Health(http.server.BaseHTTPRequestHandler):
    body = b'{"status":"ok","ffmpeg":true,"yt_dlp":"1"}'

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def test_detects_running_mediaforge(fake_server):
    assert launcher.is_mediaforge(fake_server.server_port)


def test_other_server_is_not_mediaforge(fake_server, monkeypatch):
    monkeypatch.setattr(_Health, "body", b"<html>hello</html>")
    assert not launcher.is_mediaforge(fake_server.server_port)


def test_choose_port_reuses_or_skips(fake_server, monkeypatch):
    port = fake_server.server_port
    assert launcher.choose_port(port) == (port, True)
    monkeypatch.setattr(_Health, "body", b"nope")
    chosen, running = launcher.choose_port(port)
    assert chosen != port and not running


def test_log_is_rotated(tmp_path):
    log = launcher.log_file(tmp_path)
    log.write_text("x" * 1_100_000)
    launcher.log_file(tmp_path)
    assert (tmp_path / "mediaforge.log.old").exists() and not log.exists()


def test_quit_needs_a_running_server_and_this_computer(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(runtime, "SERVER", None)
    assert client.post("/api/quit").status_code == 409
    assert client.get("/api/health").json()["can_quit"] is False

    class Fake:
        should_exit = False

    fake = Fake()
    monkeypatch.setattr(runtime, "SERVER", fake)
    assert client.get("/api/health").json()["can_quit"] is True
    assert client.post("/api/quit").status_code == 200 and fake.should_exit
    remote = TestClient(app, client=("203.0.113.5", 5000))
    assert remote.post("/api/quit").status_code == 403


def test_powershell_quotes_odd_paths():
    script = create_shortcut.powershell_script(
        Path("C:/Users/O'Neil/Desktop/MediaForge.lnk"),
        "C:/py/pythonw.exe",
        '"D:/my apps/run.py" --open',
        Path("D:/my apps"),
        Path("D:/my apps/icon.ico"),
    )
    assert "O''Neil" in script and "--open" in script and "icon.ico,0" in script


def test_desktop_entry_has_launch_line():
    entry = create_shortcut.desktop_entry("/py", Path("/a/run.py"), Path("/a"), Path("/a/i.png"))
    assert 'Exec="/py" "/a/run.py" --open' in entry and "Terminal=false" in entry


def test_windowless_python_prefers_pythonw(tmp_path):
    (tmp_path / "python.exe").write_text("")
    assert create_shortcut.windowless_python(str(tmp_path / "python.exe")).endswith("python.exe")
    (tmp_path / "pythonw.exe").write_text("")
    assert create_shortcut.windowless_python(str(tmp_path / "python.exe")).endswith("pythonw.exe")
