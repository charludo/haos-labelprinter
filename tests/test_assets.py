"""Tests for ptouch.assets (offline with a fake fetch; live test needs PTOUCH_LIVE=1)."""
import json
import os
import threading
import time
from pathlib import Path

import pytest

from ptouch import assets as A
from ptouch.assets import AssetError, AssetManager


def _find_ttf():
    for p in (
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        if os.path.isfile(p):
            return Path(p).read_bytes()
    return None


TTF = _find_ttf()
needs_ttf = pytest.mark.skipif(TTF is None, reason="no system TTF available")

CATALOG = [
    {"id": "roboto", "family": "Roboto", "category": "sans-serif", "weights": [100, 400, 700],
     "styles": ["normal", "italic"], "subsets": ["latin"], "variable": True},
    {"id": "roboto-slab", "family": "Roboto Slab", "category": "serif", "weights": [100, 400, 900],
     "styles": ["normal"], "subsets": ["latin", "latin-ext"]},
    {"id": "abel", "family": "Abel", "category": "sans-serif", "weights": [400], "styles": ["normal"],
     "subsets": ["latin"]},
    {"id": "droid-robot", "family": "Droid Robot", "category": "display", "weights": [400],
     "styles": ["normal"], "subsets": ["latin"]},
    {"id": "evil", "family": "../evil", "category": "serif", "weights": [400], "styles": ["normal"]},
    {"id": "fira-code", "family": "Fira Code", "category": "monospace", "weights": [400, 700],
     "styles": ["normal"], "subsets": ["latin"]},
]
CATALOG_BODY = json.dumps(CATALOG).encode()
GSTATIC = "https://fonts.gstatic.com/s/x/v1/abc.ttf"
MDI_CSS = (
    b'@font-face{font-family:"Material Design Icons";src:url("../fonts/x.woff2")}'
    b'.mdi-ab-testing::before{content:"\\F01C9"}.mdi-tag::before{content:"\\F04F9"}'
    b'.mdi-tag-outline::before{content:"\\F04FA"}.mdi-label-tag::before{content:"\\F0001"}'
    b'.mdi-tag-text::before{content:"\\F0002"}'
)


class Fake:
    def __init__(self, ttf=TTF, css=None):
        self.calls = []
        self.ttf = ttf
        self.css = css
        self.delay = 0.0

    def __call__(self, url, headers=None):
        self.calls.append((url, headers))
        if self.delay:
            time.sleep(self.delay)
        if url == A.CATALOG_URL:
            return CATALOG_BODY
        if url.startswith("https://fonts.googleapis.com/css2"):
            if self.css is not None:
                return self.css
            return (
                "/* latin-ext */\n@font-face {\n  src: url(https://fonts.gstatic.com/s/x/ext.ttf) "
                "format('truetype');\n}\n/* latin */\n@font-face {\n  font-family: 'X';\n  src: url("
                + GSTATIC + ") format('truetype');\n}\n"
            ).encode()
        if url.startswith("https://fonts.gstatic.com/"):
            return self.ttf
        if url == A.MDI_CSS_URL:
            return MDI_CSS
        if url == A.MDI_TTF_URL:
            return self.ttf
        raise AssertionError(f"unexpected url {url}")

    def urls(self, prefix):
        return [u for u, _ in self.calls if u.startswith(prefix)]


@pytest.fixture
def fake():
    return Fake()


@pytest.fixture
def mgr(tmp_path, fake):
    return AssetManager(tmp_path, fake)


# ---------------------------------------------------------------- catalog
def test_catalog_parse_and_filter(mgr):
    cat = mgr.font_catalog()
    fams = [f["family"] for f in cat]
    assert "../evil" not in fams  # invalid family names dropped
    assert fams[0] == "Roboto"
    assert set(cat[0]) == {"id", "family", "category", "weights", "styles", "subsets"}
    assert cat[0]["weights"] == [100, 400, 700]


def test_catalog_cached_in_memory_and_disk(tmp_path, fake):
    m = AssetManager(tmp_path, fake)
    m.font_catalog()
    m.font_catalog()
    assert len(fake.urls(A.CATALOG_URL)) == 1
    AssetManager(tmp_path, fake).font_catalog()  # fresh manager reads the disk cache
    assert len(fake.urls(A.CATALOG_URL)) == 1


def test_catalog_expiry_and_refresh(tmp_path, fake):
    m = AssetManager(tmp_path, fake)
    m.font_catalog()
    path = tmp_path / "catalog.json"
    raw = json.loads(path.read_text())
    raw["fetched"] -= 8 * 24 * 3600
    path.write_text(json.dumps(raw))
    AssetManager(tmp_path, fake).font_catalog()
    assert len(fake.urls(A.CATALOG_URL)) == 2
    m.font_catalog(refresh=True)
    assert len(fake.urls(A.CATALOG_URL)) == 3


def test_catalog_stale_fallback_on_failure(tmp_path, fake):
    AssetManager(tmp_path, fake).font_catalog()
    path = tmp_path / "catalog.json"
    raw = json.loads(path.read_text())
    raw["fetched"] -= 30 * 24 * 3600
    path.write_text(json.dumps(raw))

    def broken(url, headers=None):
        raise OSError("offline")

    assert AssetManager(tmp_path, broken).font_catalog()[0]["family"] == "Roboto"
    with pytest.raises(AssetError):
        AssetManager(tmp_path / "empty", broken).font_catalog()


def test_catalog_garbage(tmp_path):
    for body in (b"not json", b"{}", b"[]"):
        with pytest.raises(AssetError):
            AssetManager(tmp_path, lambda u, h=None, b=body: b).font_catalog()


# ---------------------------------------------------------------- search
def test_search_fonts_ranking(mgr):
    names = [f["family"] for f in mgr.search_fonts("robo")]
    assert names == ["Roboto", "Roboto Slab", "Droid Robot"]  # prefix (catalog order) then substring
    assert [f["family"] for f in mgr.search_fonts("ROBOTO S")] == ["Roboto Slab"]
    assert [f["family"] for f in mgr.search_fonts("", limit=2)] == ["Roboto", "Roboto Slab"]
    assert mgr.search_fonts("zzzz") == []


def test_search_fonts_category(mgr):
    assert [f["family"] for f in mgr.search_fonts("", category="monospace")] == ["Fira Code"]
    assert [f["family"] for f in mgr.search_fonts("robo", category="serif")] == ["Roboto Slab"]
    assert mgr.search_fonts("", category="handwriting") == []


def test_search_icons_ranking(mgr):
    assert mgr.search_icons("tag") == [
        "mdi:tag", "mdi:tag-outline", "mdi:tag-text", "mdi:label-tag"
    ]
    assert mgr.search_icons("mdi:tag", limit=1) == ["mdi:tag"]
    assert mgr.icon_names() == sorted(mgr.icon_names())
    assert "mdi:ab-testing" in mgr.icon_names()
    assert len(mgr.search_icons("")) == 5


# ---------------------------------------------------------------- font download
@needs_ttf
def test_ensure_font_download_and_cache(mgr, fake, tmp_path):
    p = mgr.ensure_font("roboto", 700, False)
    assert p.is_file() and p.read_bytes() == TTF and tmp_path in p.parents
    assert mgr.ensure_font("Roboto", 700) == p
    assert len(fake.urls("https://fonts.googleapis.com")) == 1
    css_url, headers = [c for c in fake.calls if c[0].startswith("https://fonts.googleapis.com")][0]
    assert css_url == "https://fonts.googleapis.com/css2?family=Roboto:ital,wght@0,700&display=swap"
    assert headers == {"User-Agent": "curl/8.0"}
    assert fake.urls("https://fonts.gstatic.com") == [GSTATIC]  # latin block chosen
    assert not [f for f in p.parent.iterdir() if f.name.startswith(".tmp")]


@needs_ttf
def test_weight_clamp_and_italic(mgr, fake):
    mgr.ensure_font("Roboto Slab", 800, True)  # no italic -> normal; 800 -> 900
    url = fake.urls("https://fonts.googleapis.com")[0]
    assert "family=Roboto+Slab:ital,wght@0,900" in url
    mgr.ensure_font("Roboto", 250, True)  # 250 is equidistant 100/400 -> lower
    assert "family=Roboto:ital,wght@1,100" in fake.urls("https://fonts.googleapis.com")[1]
    mgr.ensure_font("Roboto", "bogus", True)  # bad weight -> 400
    assert "wght@1,400" in fake.urls("https://fonts.googleapis.com")[2]
    mgr.ensure_font("Roboto Slab", 100, False)
    mgr.ensure_font("Roboto Slab", 150, False)  # same cache file as 100
    assert len(fake.urls("https://fonts.googleapis.com")) == 4


@needs_ttf
def test_css_without_labels_uses_first_block(tmp_path):
    css = b"@font-face {\n src: url(https://fonts.gstatic.com/s/a.ttf) format('truetype');\n}\n"
    m = AssetManager(tmp_path, Fake(css=css))
    assert m.font_path("Abel").is_file()


def test_css_without_face(tmp_path):
    m = AssetManager(tmp_path, Fake(css=b"<html>400</html>"))
    with pytest.raises(AssetError):
        m.ensure_font("Abel")
    assert m.font_path("Abel") is None


def test_css_pointing_to_bad_host(tmp_path):
    css = b"@font-face { src: url(https://evil.example.com/a.ttf) format('truetype'); }"
    fake = Fake(css=css)
    m = AssetManager(tmp_path, fake)
    with pytest.raises(AssetError, match="host not allowed"):
        m.ensure_font("Abel")
    assert not fake.urls("https://evil")


@pytest.mark.parametrize("family", ["", "../etc/passwd", "a/b", "Roboto;rm", "x" * 80, " Roboto", None, 5, "Nope"])
def test_invalid_family(mgr, fake, family):
    with pytest.raises(AssetError):
        mgr.ensure_font(family)
    assert mgr.font_path(family) is None
    assert not fake.urls("https://fonts.g")


@pytest.mark.parametrize("body", [b"<html>not a font</html>", b"", b"\x00\x01\x00\x00" + b"junk" * 10])
def test_bad_font_bytes_not_cached(tmp_path, body):
    m = AssetManager(tmp_path, Fake(ttf=body))
    with pytest.raises(AssetError):
        m.ensure_font("Abel")
    assert not list((tmp_path / "fonts").glob("*")) if (tmp_path / "fonts").exists() else True


def test_oversize_rejected(tmp_path):
    def big(url, headers=None):
        return b"x" * (A.MAX_DOWNLOAD + 1) if "css2" in url else CATALOG_BODY
    m = AssetManager(tmp_path, big)
    with pytest.raises(AssetError, match="large"):
        m.ensure_font("Abel")


@needs_ttf
def test_concurrent_ensure_downloads_once(tmp_path):
    fake = Fake()
    fake.delay = 0.05
    m = AssetManager(tmp_path, fake)
    m.font_catalog()
    out, errs = [], []

    def work():
        try:
            out.append(m.ensure_font("Roboto", 700))
        except Exception as e:  # pragma: no cover
            errs.append(e)

    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and len(set(out)) == 1
    assert len(fake.urls("https://fonts.googleapis.com")) == 1
    assert len(fake.urls("https://fonts.gstatic.com")) == 1


# ---------------------------------------------------------------- icons
@needs_ttf
def test_icon_glyph(mgr, fake):
    path, ch = mgr.icon_glyph("mdi:tag")
    assert ch == chr(0xF04F9) and len(ch) == 1 and path.is_file()
    assert mgr.icon_glyph("tag") == (path, ch)
    assert mgr.icon_glyph("MDI:Tag") == (path, ch)
    assert mgr.icon_glyph("mdi:does-not-exist") is None
    assert mgr.icon_glyph("../../x") is None
    assert len(fake.urls(A.MDI_TTF_URL)) == 1 and len(fake.urls(A.MDI_CSS_URL)) == 1


def test_icon_glyph_unknown_never_downloads_font(mgr, fake):
    assert mgr.icon_glyph("nope") is None
    assert not fake.urls(A.MDI_TTF_URL)


def test_icon_css_garbage(tmp_path):
    m = AssetManager(tmp_path, lambda u, h=None: b"body{}")
    with pytest.raises(AssetError):
        m.icon_names()
    assert m.icon_glyph("tag") is None


# ---------------------------------------------------------------- allow-list
@pytest.mark.parametrize("url", [
    "http://fonts.googleapis.com/css2", "https://evil.example.com/x", "file:///etc/passwd",
    "https://fonts.googleapis.com.evil.com/x", "https://user@fonts.gstatic.com/x",
    "https://fonts.gstatic.com:8443/x", "ftp://cdn.jsdelivr.net/x", "//fonts.gstatic.com/x",
])
def test_check_url_rejects(url):
    with pytest.raises(AssetError):
        A.check_url(url)


def test_check_url_accepts():
    for h in A.ALLOWED_HOSTS:
        assert A.check_url(f"https://{h}/x") == f"https://{h}/x"


def test_default_fetch_rejects_before_network():
    with pytest.raises(AssetError):
        A.default_fetch("http://fonts.gstatic.com/x")
    with pytest.raises(AssetError):
        A.default_fetch("https://example.com/x")


def test_redirect_handler_enforces_allow_list():
    import urllib.request
    h = A._AllowListRedirect()
    req = urllib.request.Request("https://fonts.gstatic.com/a")
    with pytest.raises(AssetError):
        h.redirect_request(req, None, 302, "Found", {}, "https://evil.example.com/b")
    with pytest.raises(AssetError):
        h.redirect_request(req, None, 302, "Found", {}, "http://fonts.gstatic.com/b")
    assert h.redirect_request(req, None, 302, "Found", {}, "https://cdn.jsdelivr.net/b") is not None


def test_default_fetch_local_server_roundtrip(monkeypatch):
    """default_fetch against a local http server by temporarily whitelisting nothing: must refuse."""
    with pytest.raises(AssetError):
        A.default_fetch("https://127.0.0.1/x")


# ---------------------------------------------------------------- live
@pytest.mark.skipif(os.environ.get("PTOUCH_LIVE") != "1", reason="set PTOUCH_LIVE=1 for network test")
def test_live(tmp_path):
    from PIL import Image, ImageDraw, ImageFont

    m = AssetManager(tmp_path)
    assert len(m.font_catalog()) > 1000
    assert m.search_fonts("roboto slab")[0]["family"] == "Roboto Slab"
    bold = m.ensure_font("Roboto Slab", 700)
    reg = m.ensure_font("Roboto Slab", 400)
    assert bold != reg and bold.stat().st_size > 10000
    wb = ImageFont.truetype(str(bold), 40).getlength("Hamburgefonts")
    wr = ImageFont.truetype(str(reg), 40).getlength("Hamburgefonts")
    assert wb > wr  # a bold instance, not a variable default
    assert m.font_path("Roboto", 700, True).is_file()  # real italic
    assert m.font_path("Pacifico", 400, True).is_file()  # no italic exists -> falls back to normal

    assert len(m.icon_names()) > 5000
    path, ch = m.icon_glyph("mdi:tag")
    font = ImageFont.truetype(str(path), 48)
    img = Image.new("L", (64, 64), 255)
    ImageDraw.Draw(img).text((8, 8), ch, font=font, fill=0)
    assert img.getextrema()[0] == 0
    assert "mdi:tag" in m.search_icons("tag", 5)
