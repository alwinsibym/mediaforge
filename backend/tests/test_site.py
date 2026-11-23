"""The website in site/ is plain files, so check that nothing it points to is missing."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[2] / "site"
PROMO = Path(__file__).resolve().parents[2] / "scripts" / "promo"


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


def test_the_files_needed_for_hosting_and_search_are_there():
    for name in ("robots.txt", "sitemap.xml", "llms.txt", "404.html", "vercel.json", "favicon.svg"):
        assert (SITE / name).is_file(), name
    assert (SITE / "media" / "promo.mp4").stat().st_size > 100_000
    assert (SITE / "media" / "poster.jpg").stat().st_size > 5_000
    assert (SITE / "media" / "og.jpg").stat().st_size > 5_000
    json.loads((SITE / "vercel.json").read_text(encoding="utf-8"))


def _html():
    return (SITE / "index.html").read_text(encoding="utf-8")


def test_one_address_is_used_everywhere():
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', _html()).group(1)
    assert canonical.startswith("https://") and canonical.endswith("/")
    assert f"<loc>{canonical}</loc>" in (SITE / "sitemap.xml").read_text(encoding="utf-8")
    assert f"Sitemap: {canonical}sitemap.xml" in (SITE / "robots.txt").read_text(encoding="utf-8")
    assert canonical in (SITE / "llms.txt").read_text(encoding="utf-8")
    assert f'content="{canonical}"' in _html()  # og:url
    host = canonical.split("//")[1].rstrip("/")
    assert host in (PROMO / "end.html").read_text(encoding="utf-8")


def test_share_image_points_at_a_real_file():
    url = re.search(r'property="og:image" content="([^"]+)"', _html()).group(1)
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', _html()).group(1)
    assert url.startswith(canonical)
    assert (SITE / url[len(canonical) :].split("?")[0]).is_file()


def _json_ld():
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', _html(), re.S)
    return [json.loads(b) for b in blocks]


def test_structured_data_is_valid_and_describes_the_page():
    kinds = {item["@type"] for item in _json_ld()}
    assert {"SoftwareApplication", "VideoObject", "FAQPage"} <= kinds
    app = next(i for i in _json_ld() if i["@type"] == "SoftwareApplication")
    assert app["offers"]["price"] == "0" and app["license"].endswith("/mit")
    assert "aggregateRating" not in app  # never invent ratings


def test_faq_data_matches_the_questions_shown_on_the_page():
    faq = next(i for i in _json_ld() if i["@type"] == "FAQPage")
    in_data = [q["name"] for q in faq["mainEntity"]]
    summaries = re.findall(r"<summary>(.*?)</summary>", _html(), re.S)
    shown = [re.sub(r"<[^>]+>", "", q).strip() for q in summaries]
    assert in_data == shown and len(shown) >= 5


def test_page_has_one_h1_and_a_sensible_title_and_description():
    html = _html()
    assert len(re.findall(r"<h1[ >]", html)) == 1
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    description = re.search(r'name="description" content="([^"]+)"', html).group(1)
    assert 20 <= len(title) <= 65
    assert 70 <= len(description) <= 160


def test_the_download_button_falls_back_to_the_releases_page(page):
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'id="download" href="https://github.com/alwinsibym/mediaforge/releases/latest"' in html


def test_media_links_carry_the_hash_of_the_current_file():
    """Media is cached for a year, so a changed file needs a new address (--stamp-only)."""
    import hashlib

    html = _html()
    for name in ("promo.mp4", "poster.jpg", "og.jpg"):
        digest = hashlib.md5((SITE / "media" / name).read_bytes()).hexdigest()[:8]
        links = re.findall(rf"media/{re.escape(name)}(\?v=[0-9a-f]+)?", html)
        assert links, name
        assert all(link == f"?v={digest}" for link in links), (
            f"{name} links are stale or unversioned"
        )


def test_the_video_frame_does_not_force_a_height():
    css = (SITE / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.window video \{[^}]*height: auto", css)
