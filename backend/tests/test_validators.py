import pytest

from app.validators import safe_filename, validate_url


def test_valid_url_is_trimmed():
    assert validate_url("  https://youtu.be/abc123 ") == "https://youtu.be/abc123"


@pytest.mark.parametrize(
    "bad", ["", "   ", None, "notaurl", "ftp://example.com/a", "file:///etc/passwd", "http://"]
)
def test_invalid_urls_rejected(bad):
    with pytest.raises(ValueError):
        validate_url(bad)


def test_overlong_url_rejected():
    with pytest.raises(ValueError):
        validate_url("https://example.com/" + "a" * 3000)


def test_safe_filename_strips_paths_and_symbols():
    assert safe_filename("../../etc/pa:ss*wd.mp3") == "passwd.mp3"
    assert safe_filename("C:\\Users\\me\\song.mp3") == "song.mp3"


def test_safe_filename_falls_back_to_default():
    assert safe_filename("   ") == "media"
    assert safe_filename(None, default="upload") == "upload"


def test_safe_filename_truncates():
    assert len(safe_filename("a" * 500)) == 80
