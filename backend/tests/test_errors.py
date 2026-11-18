import pytest
from fastapi.testclient import TestClient

from app import downloader, errors
from app.main import app


@pytest.mark.parametrize(
    "message,code",
    [
        ("[Errno 11001] getaddrinfo failed", "MF-NET-01"),
        ("Connection to x timed out. (connect timeout=30.0)", "MF-NET-02"),
        ("ConnectionResetError(10054, 'forcibly closed')", "MF-NET-03"),
        ("Sign in to confirm you're not a bot", "MF-SITE-01"),
        ("[twitter] 1: No video could be found in this tweet", "MF-SITE-04"),
        ("HTTP Error 403: Forbidden", "MF-SITE-03"),
        ("Could not copy Chrome cookie database", "MF-COOK-01"),
        ("HTTP Error 429: Too Many Requests", "MF-SITE-08"),
        ("Unsupported URL: https://x.test", "MF-SITE-06"),
        ("Something nobody expected", "MF-GEN-00"),
    ],
)
def test_classify(message, code):
    assert errors.classify(message) == code


def test_every_entry_is_complete():
    for code, entry in errors.CATALOG.items():
        assert code.startswith("MF-")
        for key in ("title", "summary", "what", "why", "fix"):
            assert entry[key], (code, key)


def test_describe_keeps_technical_text():
    info = errors.describe("MF-NET-01", "getaddrinfo failed")
    assert info["code"] == "MF-NET-01" and info["technical"] == "getaddrinfo failed"
    assert errors.describe("nope")["code"] == "MF-GEN-00"


def test_exception_carries_code():
    exc = downloader.ConversionError("x", "MF-LIM-02")
    assert errors.describe_exception(exc)["code"] == "MF-LIM-02"
    assert errors.describe_exception(ValueError("bad"))["code"] == "MF-INPUT-01"


def test_api_error_has_detail_and_info():
    client = TestClient(app)
    response = client.post("/api/jobs", json={"title": "t", "items": [], "format": "mp3"})
    assert response.status_code in (400, 422)
    if response.status_code == 400:
        assert "error" in response.json() and isinstance(response.json()["detail"], str)
