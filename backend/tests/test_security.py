import pytest
from fastapi.testclient import TestClient

from app import config, downloader, jobs, settings, validators
from app.main import app


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://localhost:8000/x",
        "http://192.168.1.5/video",
        "http://10.0.0.2/x",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/x",
        "http://[::ffff:127.0.0.1]/x",
        "http://printer.local/x",
        "http://0.0.0.0/x",
    ],
)
def test_private_addresses_blocked(url):
    with pytest.raises(validators.BlockedAddress) as info:
        validators.validate_url(url)
    assert info.value.code == "MF-SEC-01"


def test_public_address_and_override(monkeypatch):
    assert validators.validate_url("https://93.184.216.34/v") == "https://93.184.216.34/v"
    monkeypatch.setattr(config, "ALLOW_PRIVATE_URLS", True)
    assert validators.validate_url("http://127.0.0.1/x")


def test_name_resolving_to_private_is_blocked(monkeypatch):
    monkeypatch.setattr(
        validators.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("192.168.0.9", 0))],
    )
    with pytest.raises(validators.BlockedAddress):
        validators.validate_url("https://sneaky.example.org/x")


def test_unresolvable_name_is_allowed(monkeypatch):
    def fail(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(validators.socket, "getaddrinfo", fail)
    assert validators.validate_url("https://example.org/x")


def test_api_returns_security_code(monkeypatch):
    client = TestClient(app)
    response = client.post("/api/info", json={"url": "http://127.0.0.1/x"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MF-SEC-01"


def test_proxy_setting_validation():
    assert settings.save({"proxy": "socks5://127.0.0.1:1080"})["proxy"].startswith("socks5")
    assert settings.save({"proxy": ""})["proxy"] == ""
    for bad in ("127.0.0.1:1080", "ftp://h:21", "http://nohost", "http://h:99999"):
        with pytest.raises(ValueError):
            settings.save({"proxy": bad})


def test_proxy_and_impersonation_reach_options(monkeypatch):
    settings.save({"proxy": "http://127.0.0.1:8080", "impersonate": True})
    monkeypatch.setattr(downloader, "impersonation_available", lambda: False)
    options = downloader._base_options()
    assert options["proxy"] == "http://127.0.0.1:8080" and "impersonate" not in options


def test_job_limit(monkeypatch):
    monkeypatch.setattr(config, "MAX_ACTIVE_JOBS", 0)
    with pytest.raises(downloader.ConversionError) as info:
        jobs.start_job(
            "t", [{"title": "a", "url": "https://93.184.216.34/a"}], "mp3", "192", True, False
        )
    assert info.value.code == "MF-LIM-04"


class TestToken:
    def test_remote_client_needs_token(self, monkeypatch):
        monkeypatch.setattr(config, "ACCESS_TOKEN", "s3cret")
        remote = TestClient(app, client=("203.0.113.5", 50000))
        assert remote.get("/api/formats").status_code == 401
        assert remote.get("/api/health").json()["authorised"] is False
        assert remote.post("/api/login", json={"token": "nope"}).status_code == 401
        assert remote.post("/api/login", json={"token": "s3cret"}).status_code == 200
        assert remote.get("/api/formats").status_code == 200
        assert remote.get("/api/health").json()["authorised"] is True

    def test_bearer_header_and_local_exempt(self, monkeypatch):
        monkeypatch.setattr(config, "ACCESS_TOKEN", "s3cret")
        remote = TestClient(app, client=("203.0.113.5", 50000))
        assert (
            remote.get("/api/formats", headers={"Authorization": "Bearer s3cret"}).status_code
            == 200
        )
        assert TestClient(app).get("/api/formats").status_code == 200

    def test_no_token_means_open(self, monkeypatch):
        monkeypatch.setattr(config, "ACCESS_TOKEN", "")
        remote = TestClient(app, client=("203.0.113.5", 50000))
        assert remote.get("/api/formats").status_code == 200
