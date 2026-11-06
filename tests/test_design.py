import base64
import io
import os

import pytest
from PIL import Image, ImageDraw

from ptouch.design import (DESIGN_VERSION, DesignError, design_warnings, normalize_design,
                           render_design)
from ptouch.protocol import tape_pins

DEJAVU = next((p for p in ("/usr/share/fonts/TTF/DejaVuSans.ttf",
                           "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") if os.path.exists(p)), None)


class FakeAssets:
    def __init__(self, font=DEJAVU, glyph=("★",)):
        self.font, self.glyph = font, glyph
        self.calls = []

    def font_path(self, family, weight=400, italic=False):
        self.calls.append((family, weight, italic))
        return self.font

    def icon_glyph(self, name):
        if name.endswith("missing") or not self.font:
            return None
        return (self.font, self.glyph[0]) if False else (__import__("pathlib").Path(self.font), self.glyph[0])


class Boom:
    def font_path(self, *a):
        raise RuntimeError("x")

    def icon_glyph(self, *a):
        raise RuntimeError("x")


def ink(img, box=None):
    im = img.crop(box) if box else img
    return sum(1 for v in im.getdata() if v == 0)


def d(*els, **kw):
    return {"version": 1, "elements": list(els), **kw}


def png_uri(size=(20, 10), fmt="PNG", color=0):
    im = Image.new("L", size, 255)
    ImageDraw.Draw(im).rectangle((0, 0, size[0] // 2, size[1] - 1), fill=color)
    b = io.BytesIO()
    im.save(b, fmt)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(b.getvalue()).decode()


@pytest.mark.parametrize("tape", [4, 6, 9, 12, 18, 24])
def test_height_and_mode(tape):
    img = render_design(d({"type": "text", "text": "Hi", "w": 80, "h": 20}), tape)
    assert img.mode == "1" and img.height == tape_pins(tape)


def test_empty_design_min_length():
    img = render_design({}, 12)
    assert img.size == (6, 70)
    assert render_design(d(), 12).width == 6  # trailing padding only


def test_auto_and_fixed_length():
    e = {"type": "rect", "x": 10, "y": 0, "w": 100, "h": 10}
    assert render_design(d(e, padding_dots=4), 12).width == 114
    assert render_design(d(e, length_mm=25.4), 12).width == 180


def test_too_long():
    with pytest.raises(DesignError):
        render_design(d({"type": "rect", "w": 7000, "h": 5}), 12)
    assert render_design(d(length_mm=2000), 12).width == 6000  # clamped

def test_bad_tape_and_inputs():
    with pytest.raises(DesignError):
        render_design({}, 13)
    for bad in (None, [], "x", 5):
        with pytest.raises(DesignError):
            normalize_design(bad)
    with pytest.raises(DesignError):
        normalize_design({"elements": "no"})
    with pytest.raises(DesignError):
        normalize_design({"elements": [1]})
    with pytest.raises(DesignError):
        normalize_design({"version": 2})
    with pytest.raises(DesignError):
        normalize_design({"elements": [{"type": "rect"}] * 201})


def test_normalize_defaults_and_clamp():
    n = normalize_design({"elements": [
        {"type": "text", "x": 1e9, "y": "7", "w": -5, "h": float("nan"), "rotation": 100,
         "size": 9999, "weight": 5, "align": "bogus", "invert": "yes"},
        {"type": "wat"},
        {"type": "image", "src": "http://evil/x.png"},
        {"type": "barcode", "format": "nope"},
    ]})
    assert n["version"] == DESIGN_VERSION and len(n["elements"]) == 3
    t = n["elements"][0]
    assert t["x"] == 20000 and t["y"] == 7 and t["w"] == 0 and t["h"] == 40
    assert t["rotation"] == 90 and t["size"] == 400 and t["weight"] == 100
    assert t["align"] == "center" and t["invert"] is False and t["valign"] == "middle"
    assert n["elements"][1]["src"] == "" and n["elements"][2]["format"] == "code128"
    assert normalize_design(n) == n  # idempotent
    assert normalize_design({"elements": [{"type": "text", "size": "auto"}]})["elements"][0]["size"] == "auto"
    assert normalize_design({"elements": [{"type": "text", "size": "junk"}]})["elements"][0]["size"] == "auto"
    assert normalize_design({"elements": [{"type": "text", "size": 2}]})["elements"][0]["size"] == 4


def test_text_autosize_is_largest_fit():
    el = {"type": "text", "text": "Hello", "x": 0, "y": 0, "w": 300, "h": 40, "size": "auto"}
    img = render_design(d(el, length_mm=60), 12)
    box = img.crop((0, 0, 300, 40))
    bb = ImageOps_bbox(box)
    assert bb is not None and bb[3] <= 40 and bb[1] >= 0
    # taller box -> bigger glyphs
    el2 = dict(el, h=60)
    bb2 = ImageOps_bbox(render_design(d(el2, length_mm=60), 12).crop((0, 0, 300, 60)))
    assert (bb2[3] - bb2[1]) > (bb[3] - bb[1])


def ImageOps_bbox(img):
    from PIL import ImageOps
    return ImageOps.invert(img.convert("L")).getbbox()


def test_text_wrap_and_clip_warning():
    el = {"type": "text", "text": "one two three four five six", "w": 120, "h": 120, "size": 20}
    img = render_design(d(el), 12)
    bb = ImageOps_bbox(img.crop((6, 0, 126, 120)))
    assert bb[3] - bb[1] > 30  # several lines
    big = dict(el, size=60, h=20)
    assert any("clipped" in w for w in design_warnings(d(big), 12))
    assert not any("clipped" in w for w in design_warnings(d(el), 12))
    # clipping keeps pixels inside the box
    img = render_design(d(dict(big, x=0), {"type": "rect", "x": 300, "w": 4, "h": 4}, padding_dots=0), 12)
    assert ink(img, (0, 21, 120, 70)) == 0


def test_text_align_and_valign():
    base = {"type": "text", "text": "Hi", "w": 200, "h": 60, "size": 20}
    def bbox(**kw):
        return ImageOps_bbox(render_design(d(dict(base, **kw), padding_dots=0), 12))
    l, c, r = bbox(align="left"), bbox(align="center"), bbox(align="right")
    assert l[0] < c[0] < r[0] and r[2] > 190
    t, m, b = bbox(valign="top"), bbox(valign="middle"), bbox(valign="bottom")
    assert t[1] < m[1] < b[1]


def test_variables():
    el = {"type": "text", "text": "{{ name }}-{{x}}-{{ nope }}", "w": 300, "h": 40, "size": 20}
    a = render_design(d(el, variables={"name": "A", "x": "1"}), 12, variables={"name": "B"})
    b = render_design(d(dict(el, text="B-1--")), 12, variables=None)  # literal text, no vars... 
    raw = render_design(d(el), 12, variables=None)
    assert raw.tobytes() != a.tobytes()
    named = render_design(d(dict(el, text="B-1-")), 12)
    assert a.tobytes() == named.tobytes()
    assert b.size == a.size
    # empty text draws nothing
    e = render_design(d(dict(el, text="{{ gone }}")), 12, variables={})
    assert ink(e) == 0


def test_rotation_and_invert():
    el = {"type": "text", "text": "Hello", "w": 100, "h": 50, "size": 20, "x": 0}
    assert render_design(d(el), 24).width == render_design(d(dict(el, rotation=90)), 24).width
    bb90 = ImageOps_bbox(render_design(d(dict(el, rotation=90), padding_dots=0), 24))
    bb0 = ImageOps_bbox(render_design(d(el, padding_dots=0), 24))
    assert (bb90[3] - bb90[1]) > (bb0[3] - bb0[1])  # tall instead of wide
    assert bb90[2] <= 100 and bb90[3] <= 50
    img = render_design(d(dict(el, invert=True), padding_dots=0), 24)
    assert img.getpixel((0, 0)) == 0 and img.getpixel((99, 49)) == 0
    assert 0 < ink(img, (0, 0, 100, 50)) < 5000 and ink(img, (0, 0, 100, 50)) > 2500 - 600
    r180 = render_design(d(dict(el, rotation=180), padding_dots=0), 24)
    assert r180.size == (100, 128) and ink(r180) > 0


def test_rect_modes():
    outline = render_design(d({"type": "rect", "w": 20, "h": 20, "stroke": 2}, padding_dots=0), 12)
    assert ink(outline, (0, 0, 20, 20)) == 400 - 16 * 16
    assert outline.getpixel((10, 10)) == 255
    solid = render_design(d({"type": "rect", "w": 20, "h": 20, "fill": True}, padding_dots=0), 12)
    assert ink(solid, (0, 0, 20, 20)) == 400
    line = render_design(d({"type": "rect", "w": 50, "h": 1, "fill": True, "y": 5}, padding_dots=0), 12)
    assert ink(line) == 50


def test_qr_integer_scale_and_centred():
    el = {"type": "qr", "data": "HELLO", "w": 70, "h": 70, "ecc": "l", "quiet": 1}
    img = render_design(d(el, padding_dots=0), 12)
    bb = ImageOps_bbox(img)
    side = bb[2] - bb[0]
    assert side == bb[3] - bb[1] and 29 * 2 <= 70  # version 1 = 21 modules
    scale = side // 21
    assert side == 21 * scale and scale >= 3
    assert ink(render_design(d(dict(el, data="")), 12)) == 0
    # too small
    assert any("too small" in w for w in design_warnings(d(dict(el, w=10, h=10)), 12))
    # overflow of data never crashes
    assert design_warnings(d(dict(el, data="x" * 4000, ecc="h")), 12)


def test_barcode_formats_and_integer_modules():
    for fmt, data in [("code128", "Hello123"), ("code39", "AB-12"), ("ean13", "5901234123457"),
                      ("ean13", "590123412345"), ("ean8", "96385074"), ("upca", "036000291452"),
                      ("itf", "123456"), ("codabar", "A1234B")]:
        el = {"type": "barcode", "format": fmt, "data": data, "w": 300, "h": 60}
        img = render_design(d(el, padding_dots=0), 24)
        assert ink(img) > 100, fmt
        assert design_warnings(d(el), 24) == [], fmt
    el = {"type": "barcode", "format": "code128", "data": "abc", "w": 300, "h": 60, "show_text": False}
    img = render_design(d(el, padding_dots=0), 24)
    row = [img.getpixel((x, 5)) for x in range(300)]
    runs, cur = [], 1
    for a, b in zip(row, row[1:]):
        if a == b:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    mw = min(runs[1:] or runs)
    assert all(r % mw == 0 for r in runs[1:]), runs   # crisp integer modules


def test_barcode_text_toggle():
    base = {"type": "barcode", "data": "ABC123", "w": 300, "h": 60}
    with_t = render_design(d(base, padding_dots=0), 24)
    without = render_design(d(dict(base, show_text=False), padding_dots=0), 24)
    assert ink(with_t, (0, 50, 300, 60)) > 0
    assert ink(without, (0, 59, 300, 60)) > 0           # bars reach the bottom
    assert ink(with_t, (0, 59, 300, 60)) == 0           # text area below the bars


def test_barcode_bad_data_warns_not_crashes():
    for fmt, data in [("ean13", "5901234123458"), ("ean13", "abc"), ("ean8", "123"),
                      ("code39", "abc~é"), ("code128", "héllo→"), ("itf", "12a"), ("upca", "1")]:
        el = {"type": "barcode", "format": fmt, "data": data, "w": 300, "h": 60}
        img = render_design(d(el, padding_dots=0), 24)
        assert ink(img) == 0, (fmt, data)
        assert design_warnings(d(el), 24), (fmt, data)
    narrow = {"type": "barcode", "data": "A" * 40, "w": 50, "h": 40}
    assert any("narrow" in w for w in design_warnings(d(narrow), 24))


def test_image_element():
    el = {"type": "image", "src": png_uri(), "w": 40, "h": 40, "dither": False}
    img = render_design(d(el, padding_dots=0), 12)
    assert 0 < ink(img) < 40 * 40
    jp = render_design(d(dict(el, src=png_uri(fmt="JPEG"))), 12)
    assert ink(jp) > 0
    assert render_design(d(dict(el, dither=True)), 12).height == 70
    for bad in ("data:image/png;base64,AAAA", "data:image/png;base64,!!!", "javascript:1",
                "data:text/html;base64," + base64.b64encode(b"<b>").decode()):
        e = dict(el, src=bad)
        assert ink(render_design(d(e), 12)) == 0
    assert any("image" in w for w in design_warnings(d(dict(el, src="data:image/png;base64,AAAA")), 12))


def test_image_pixel_cap():
    big = Image.new("1", (6000, 6000), 0)  # compresses tiny
    b = io.BytesIO()
    big.save(b, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
    el = {"type": "image", "src": uri, "w": 40, "h": 40}
    assert ink(render_design(d(el), 12)) == 0
    assert any("pixels" in w for w in design_warnings(d(el), 12))


def test_icon_with_fake_and_missing_assets():
    el = {"type": "icon", "icon": "mdi:star", "w": 50, "h": 50}
    img = render_design(d(el, padding_dots=0), 12, assets=FakeAssets())
    bb = ImageOps_bbox(img)
    assert bb is not None and bb[2] - bb[0] <= 50 and bb[3] - bb[1] <= 50
    assert max(bb[2] - bb[0], bb[3] - bb[1]) >= 40  # as large as fits
    assert ink(render_design(d(el), 12)) == 0               # assets=None
    assert ink(render_design(d(el), 12, assets=Boom())) == 0
    assert ink(render_design(d(dict(el, icon="mdi:missing")), 12, assets=FakeAssets())) == 0
    assert any("icon" in w for w in design_warnings(d(el), 12))


def test_assets_font_used_and_failures_fall_back():
    a = FakeAssets()
    el = {"type": "text", "text": "Hi", "font": "Roboto Slab", "weight": 700, "italic": True, "w": 100, "h": 30}
    render_design(d(el), 12, assets=a)
    assert ("Roboto Slab", 700, True) in a.calls
    assert ink(render_design(d(el), 12, assets=Boom())) > 0
    assert ink(render_design(d(el), 12, assets=FakeAssets(font="/nonexistent.ttf"))) > 0
    assert ink(render_design(d(el), 12)) > 0


def test_last_resort_default_font(monkeypatch):
    import ptouch.design as m
    monkeypatch.setattr(m, "_system_font_path", lambda w, i: None)
    el = {"type": "text", "text": "Hi there", "w": 150, "h": 40}
    img = render_design(d(el), 12)
    assert ink(img) > 0
    el_bc = {"type": "barcode", "data": "ABC", "w": 200, "h": 60}
    assert ink(render_design(d(el_bc), 24)) > 0


def test_warnings_outside_and_beyond():
    w = design_warnings(d({"type": "rect", "x": 500, "y": 0, "w": 10, "h": 10, "id": "far"},
                          {"type": "rect", "x": 0, "y": 60, "w": 10, "h": 30, "id": "low"},
                          length_mm=10), 12)
    assert any("far" in x and "outside" in x for x in w)
    assert any("low" in x and "beyond" in x for x in w)
    assert design_warnings(d({"type": "rect", "w": 10, "h": 10}), 12) == []


def test_elements_painted_in_order():
    a = {"type": "rect", "w": 20, "h": 20, "fill": True}
    b = {"type": "rect", "w": 10, "h": 10, "fill": True, "invert": True}
    img = render_design(d(a, b, padding_dots=0), 12)
    assert img.getpixel((12, 12)) == 0
    assert img.getpixel((15, 15)) == 0


def test_fuzz_never_raises_other_than_designerror():
    import random
    rnd = random.Random(3)
    vals = [None, True, -1, 1e30, "x", "", [], {}, float("inf"), 3, "{{ a }}", "auto", 90]
    keys = ["type", "x", "y", "w", "h", "rotation", "invert", "text", "size", "data", "format", "src",
            "icon", "stroke", "fill", "ecc", "quiet", "weight", "line_spacing", "align", "font"]
    for _ in range(300):
        el = {k: rnd.choice(vals) for k in rnd.sample(keys, 8)}
        el["type"] = rnd.choice(["text", "icon", "qr", "barcode", "rect", "image", "bogus", 5])
        try:
            render_design({"elements": [el], "length_mm": rnd.choice([None, 20, "x"]),
                           "padding_dots": rnd.choice(vals)}, rnd.choice([12, 24]),
                          variables=rnd.choice([None, {}]), assets=rnd.choice([None, Boom()]))
        except DesignError:
            pass
