"""The website in site/ is plain files, so check that nothing it points to is missing."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[2] / "site"


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.local = []
        self.ids = set()
        self.anchors = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        for key in ("href", "src", "poster"):
            target = values.get(key)
            if not target:
                continue
            if target.startswith("#"):
                self.anchors.append(target[1:])
            elif not re.match(r"^(https?:|mailto:|data:)", target):
                self.local.append(target)


@pytest.fixture(scope="module")
def page():
    parser = _Links()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
    return parser


def test_every_local_file_the_page_uses_exists(page):
    missing = [t for t in page.local if not (SITE / t.split("?")[0]).is_file()]
    assert not missing, f"site/index.html points to files that are not in site/: {missing}"


def test_every_in_page_link_has_a_target(page):
    missing = [a for a in page.anchors if a and a not in page.ids]
    assert not missing, f"links to sections that do not exist: {missing}"


def test_the_pages_needed_for_hosting_are_there():
    assert (SITE / ".nojekyll").is_file()
    assert (SITE / "media" / "promo.mp4").stat().st_size > 100_000
    assert (SITE / "media" / "poster.jpg").stat().st_size > 5_000


def test_the_download_button_falls_back_to_the_releases_page(page):
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'id="download" href="https://github.com/alwinsibym/mediaforge/releases/latest"' in html
