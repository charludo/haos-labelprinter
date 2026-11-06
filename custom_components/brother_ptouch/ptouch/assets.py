"""Downloadable assets for the label editor: Google Fonts (TTF) and Material Design Icons.

Everything is fetched from a fixed host allow-list over https, validated, and cached on disk
with atomic writes. All I/O is blocking; call from an executor thread. No Home Assistant imports.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from PIL import ImageFont

from .errors import PtouchError

_LOGGER = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset(
    {"api.fontsource.org", "fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net"}
)
MAX_DOWNLOAD = 30 * 1024 * 1024
FETCH_TIMEOUT = 20
CATALOG_TTL = 7 * 24 * 3600

CATALOG_URL = "https://api.fontsource.org/v1/fonts?type=google"
MDI_VERSION = "7.4.47"
MDI_BASE = f"https://cdn.jsdelivr.net/npm/@mdi/font@{MDI_VERSION}"
MDI_TTF_URL = f"{MDI_BASE}/fonts/materialdesignicons-webfont.ttf"
MDI_CSS_URL = f"{MDI_BASE}/css/materialdesignicons.min.css"
CSS_USER_AGENT = "curl/8.0"  # makes Google answer with .ttf instead of woff

_FAMILY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .&'-]{0,59}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_ICON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_FACE_RE = re.compile(r"(?:/\*\s*([\w-]+)\s*\*/\s*)?@font-face\s*\{([^}]*)\}")
_SRC_RE = re.compile(r"url\(\s*['\"]?([^)'\"\s]+)['\"]?\s*\)")
_ICON_CSS_RE = re.compile(r'\.mdi-([a-z0-9-]+)::before\s*\{\s*content:\s*"\\([0-9A-Fa-f]+)"')
_TTF_MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")
CATEGORIES = ("sans-serif", "serif", "display", "handwriting", "monospace")


class AssetError(PtouchError):
    """An asset could not be found, downloaded or validated."""


Fetch = Callable[[str, "dict | None"], bytes]


def check_url(url: str) -> str:
    """Return the url if it is https on an allowed host, else raise AssetError."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as err:
        raise AssetError(f"invalid url: {err}") from err
    if parts.scheme != "https":
        raise AssetError(f"refusing non-https url: {url[:80]}")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise AssetError("refusing url with credentials or custom port")
    if (parts.hostname or "").lower() not in ALLOWED_HOSTS:
        raise AssetError(f"host not allowed: {parts.hostname}")
    return url


class _AllowListRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_fetch(url: str, headers: dict | None = None) -> bytes:
    """GET ``url`` (allow-listed https only), 20 s timeout, 30 MB cap, redirects re-checked."""
    check_url(url)
    opener = urllib.request.build_opener(_AllowListRedirect)
    hdrs = {"User-Agent": "ha-brother-ptouch/1.0"}  # urllib's default UA gets a 403 from some CDNs
    hdrs.update(headers or {})
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT) as resp:
            check_url(resp.geturl())
            length = resp.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > MAX_DOWNLOAD:
                raise AssetError("download too large")
            body = resp.read(MAX_DOWNLOAD + 1)
    except AssetError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise AssetError(f"download failed: {err}") from err
    if len(body) > MAX_DOWNLOAD:
        raise AssetError("download too large")
    return body


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _validate_font_bytes(data: bytes) -> None:
    if not data.startswith(_TTF_MAGICS):
        raise AssetError("downloaded file is not a TrueType/OpenType font")
    try:
        ImageFont.truetype(io.BytesIO(data), 12)
    except Exception as err:  # noqa: BLE001 - Pillow raises OSError/others
        raise AssetError(f"font file cannot be opened: {err}") from err


class AssetManager:
    """Font catalog + Google Fonts TTF cache + MDI icon font/codepoints."""

    def __init__(self, cache_dir, fetch: Fetch | None = None):
        self._dir = Path(cache_dir)
        self._fetch: Fetch = fetch or default_fetch
        self._lock = threading.RLock()
        self._catalog: list[dict] | None = None
        self._catalog_time = 0.0
        self._icons: dict[str, int] | None = None
        self._icon_names: list[str] | None = None

    # ------------------------------------------------------------------ helpers
    def _get(self, url: str, headers: dict | None = None) -> bytes:
        check_url(url)
        try:
            body = self._fetch(url, headers)
        except AssetError:
            raise
        except Exception as err:  # noqa: BLE001 - custom fetch may raise anything
            raise AssetError(f"download failed: {err}") from err
        if not isinstance(body, (bytes, bytearray)):
            raise AssetError("fetch returned non-bytes")
        if len(body) > MAX_DOWNLOAD:
            raise AssetError("download too large")
        return bytes(body)

    # ------------------------------------------------------------------ fonts
    def font_catalog(self, refresh: bool = False) -> list[dict]:
        with self._lock:
            now = time.time()
            if not refresh and self._catalog is not None and now - self._catalog_time < CATALOG_TTL:
                return list(self._catalog)
            path = self._dir / "catalog.json"
            if not refresh:
                cached = self._read_catalog_file(path)
                if cached is not None and now - cached[0] < CATALOG_TTL:
                    self._catalog_time, self._catalog = cached
                    return list(self._catalog)
            try:
                fonts = self._parse_catalog(self._get(CATALOG_URL, {"Accept": "application/json"}))
            except AssetError:
                stale = self._catalog if self._catalog is not None else None
                if stale is None:
                    cached = self._read_catalog_file(path)
                    stale = cached[1] if cached else None
                if stale is not None:
                    _LOGGER.warning("font catalog refresh failed, using stale copy")
                    self._catalog = stale
                    return list(stale)
                raise
            self._catalog, self._catalog_time = fonts, now
            _atomic_write(
                path, json.dumps({"fetched": now, "fonts": fonts}).encode()
            )
            return list(fonts)

    @staticmethod
    def _read_catalog_file(path: Path):
        try:
            raw = json.loads(path.read_text())
            fonts = raw["fonts"]
            if not isinstance(fonts, list):
                return None
            return float(raw["fetched"]), fonts
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _parse_catalog(body: bytes) -> list[dict]:
        try:
            raw = json.loads(body)
        except ValueError as err:
            raise AssetError(f"font catalog is not JSON: {err}") from err
        if not isinstance(raw, list):
            raise AssetError("unexpected font catalog format")
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            fid, fam = item.get("id"), item.get("family")
            if not (isinstance(fid, str) and isinstance(fam, str)):
                continue
            if not (_ID_RE.match(fid) and _FAMILY_RE.match(fam)):
                continue
            weights = sorted({int(w) for w in item.get("weights") or [] if str(w).isdigit()})
            styles = [s for s in item.get("styles") or [] if s in ("normal", "italic")]
            out.append(
                {
                    "id": fid,
                    "family": fam,
                    "category": str(item.get("category") or ""),
                    "weights": weights,
                    "styles": styles or ["normal"],
                    "subsets": [str(s) for s in item.get("subsets") or []],
                }
            )
        if not out:
            raise AssetError("font catalog is empty")
        return out

    def search_fonts(self, query: str = "", category: str | None = None, limit: int = 50) -> list[dict]:
        q = (query or "").strip().lower()
        cat = (category or "").strip().lower() or None
        limit = max(0, int(limit))
        prefix, contains = [], []
        for font in self.font_catalog():
            if cat and font["category"].lower() != cat:
                continue
            name = font["family"].lower()
            if not q or name.startswith(q):
                prefix.append(font)
            elif q in name:
                contains.append(font)
        return (prefix + contains)[:limit]

    def _resolve(self, family: str) -> dict:
        if not isinstance(family, str) or not _FAMILY_RE.match(family):
            raise AssetError("invalid font family name")
        want = family.lower()
        for font in self.font_catalog():
            if font["family"].lower() == want:
                return font
        raise AssetError(f"unknown font family: {family}")

    @staticmethod
    def _pick_variant(font: dict, weight, italic: bool) -> tuple[int, bool]:
        try:
            weight = int(weight)
        except (TypeError, ValueError):
            weight = 400
        weights = font["weights"] or [400]
        best = min(weights, key=lambda w: (abs(w - weight), w))
        return best, bool(italic) and "italic" in font["styles"]

    def ensure_font(self, family, weight=400, italic=False) -> Path:
        font = self._resolve(family)
        wght, ital = self._pick_variant(font, weight, italic)
        path = self._dir / "fonts" / f"{font['id']}-{wght}-{'i' if ital else 'n'}.ttf"
        with self._lock:
            if path.is_file():
                return path
            data = self._download_font(font["family"], wght, ital)
            _atomic_write(path, data)
        return path

    def _download_font(self, family: str, weight: int, italic: bool) -> bytes:
        css_url = (
            "https://fonts.googleapis.com/css2?family="
            f"{urllib.parse.quote_plus(family)}:ital,wght@{1 if italic else 0},{weight}&display=swap"
        )
        css = self._get(css_url, {"User-Agent": CSS_USER_AGENT}).decode("utf-8", "replace")
        src = self._latin_src(css)
        data = self._get(src)
        _validate_font_bytes(data)
        return data

    @staticmethod
    def _latin_src(css: str) -> str:
        faces = []
        for label, body in _FACE_RE.findall(css):
            m = _SRC_RE.search(body)
            if m:
                faces.append((label, m.group(1)))
        if not faces:
            raise AssetError("no @font-face in Google Fonts response")
        for label, url in faces:
            if label == "latin":
                return url
        for label, url in faces:  # the TTF user agent normally yields one unlabeled block
            if not label:
                return url
        return faces[0][1]

    def font_path(self, family, weight=400, italic=False) -> Path | None:
        try:
            return self.ensure_font(family, weight, italic)
        except Exception as err:  # noqa: BLE001 - never raises by contract
            _LOGGER.debug("font %r unavailable: %s", family, err)
            return None

    # ------------------------------------------------------------------ icons
    def _icon_font_path(self) -> Path:
        path = self._dir / "icons" / f"materialdesignicons-{MDI_VERSION}.ttf"
        with self._lock:
            if not path.is_file():
                data = self._get(MDI_TTF_URL)
                _validate_font_bytes(data)
                _atomic_write(path, data)
        return path

    def _load_icons(self) -> dict[str, int]:
        with self._lock:
            if self._icons is not None:
                return self._icons
            path = self._dir / "icons" / f"materialdesignicons-{MDI_VERSION}.min.css"
            if not path.is_file():
                css = self._get(MDI_CSS_URL)
                if not _ICON_CSS_RE.search(css.decode("utf-8", "replace")):
                    raise AssetError("icon stylesheet has no icon definitions")
                _atomic_write(path, css)
            text = path.read_text("utf-8", "replace")
            icons = {m.group(1): int(m.group(2), 16) for m in _ICON_CSS_RE.finditer(text)}
            if not icons:
                try:
                    path.unlink()
                except OSError:
                    pass
                raise AssetError("icon stylesheet has no icon definitions")
            self._icons = icons
            self._icon_names = sorted(f"mdi:{n}" for n in icons)
            return icons

    def icon_names(self) -> list[str]:
        self._load_icons()
        return list(self._icon_names or [])

    def search_icons(self, query, limit=100) -> list[str]:
        self._load_icons()
        q = str(query or "").strip().lower()
        if q.startswith("mdi:"):
            q = q[4:]
        limit = max(0, int(limit))
        names = self._icon_names or []
        if not q:
            return names[:limit]
        exact, prefix, contains = [], [], []
        for full in names:
            n = full[4:]
            if n == q:
                exact.append(full)
            elif n.startswith(q):
                prefix.append(full)
            elif q in n:
                contains.append(full)
        return (exact + prefix + contains)[:limit]

    def icon_glyph(self, name) -> tuple[Path, str] | None:
        n = str(name or "").strip().lower()
        if n.startswith("mdi:"):
            n = n[4:]
        if not _ICON_RE.match(n):
            return None
        try:
            code = self._load_icons().get(n)
            if code is None:
                return None
            return self._icon_font_path(), chr(code)
        except AssetError as err:
            _LOGGER.debug("icon %r unavailable: %s", name, err)
            return None
