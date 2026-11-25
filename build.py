"""Build bitroot.ttf, bitroot.woff2, the README images and the site data from src/bitroot-typeface.aseprite.

    pip install -r requirements.txt
    python build.py
"""
import json
import struct
import zlib
from datetime import datetime
from pathlib import Path

from fontTools.agl import UV2AGL
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.O_S_2f_2 import Panose
from PIL import Image, ImageColor, ImageDraw

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "src/font.json").read_text("utf-8"))
CW, CH = CFG["cell-width"], CFG["cell-height"]
BASE, CAP, U = CFG["baseline"], CFG["cap-height"], CFG["units-per-pixel"]
STEP_X, STEP_Y = CW + CFG["cell-gap"], CH + CFG["cell-gap"]


def read_aseprite(path):
    """Return ({layer name: (x, y, RGBA image)}, {layer name: parent group}) for frame 0."""
    b = Path(path).read_bytes()
    assert struct.unpack_from("<H", b, 4)[0] == 0xA5E0 and struct.unpack_from("<H", b, 12)[0] == 32, "need an RGBA .aseprite"
    w, h = struct.unpack_from("<HH", b, 8)
    layers, parents, groups, cels = [], [], [], {}
    off = 144
    for _ in range(struct.unpack_from("<I", b, 140)[0]):
        size, typ = struct.unpack_from("<IH", b, off)
        d = b[off + 6:off + size]
        off += size
        if typ == 0x2004:  # layer
            level = struct.unpack_from("<H", d, 4)[0]
            name = d[18:18 + struct.unpack_from("<H", d, 16)[0]].decode()
            groups[level:] = [name]
            layers.append(name)
            parents.append(groups[level - 1] if level else None)
        elif typ == 0x2005:  # cel
            li, x, y = struct.unpack_from("<Hhh", d)
            kind = struct.unpack_from("<H", d, 7)[0]
            cw, ch = struct.unpack_from("<HH", d, 16)
            px = d[20:] if kind == 0 else zlib.decompress(d[20:]) if kind == 2 else None
            assert px is not None, f"unsupported cel type {kind}"
            cels[layers[li]] = (x, y, Image.frombytes("RGBA", (cw, ch), px))
    return cels, dict(zip(layers, parents)), (w, h)


def flatten(cels, names, size):
    out = Image.new("RGBA", size)
    for n in names:
        if n in cels:
            x, y, im = cels[n]
            out.alpha_composite(im, (max(x, 0), max(y, 0)), (max(-x, 0), max(-y, 0)))
    return out


def bitmaps(sheet):
    """{char: set of (x, y) ink pixels}, y counted upward from the baseline row."""
    out = {}
    for r, row in enumerate(CFG["rows"]):
        for c, ch in enumerate(row):
            x0 = CFG["cell-offset"] + c * STEP_X
            y0 = CFG["cell-offset"] + r * STEP_Y
            out[ch] = set() if ch.isspace() else {
                (x, BASE - 1 - y) for y in range(CH) for x in range(CW) if sheet.getpixel((x0 + x, y0 + y))[3]
            }
    return out


def outline(pixels):
    """Merge pixel squares into clockwise outer contours / counter-clockwise holes."""
    edges = set()
    for x, y in pixels:
        sq = [(x, y), (x, y + 1), (x + 1, y + 1), (x + 1, y)]
        for a, b in zip(sq, sq[1:] + sq[:1]):
            edges.discard((b, a)) if (b, a) in edges else edges.add((a, b))
    nxt = {}
    for a, b in edges:
        nxt.setdefault(a, []).append(b)
    contours = []
    while nxt:
        start = min(nxt)
        pts, p, d = [start], start, (0, 1)
        while True:
            outs = nxt[p]
            # at corners where two pixels touch diagonally, turn right so they stay separate
            q = max(outs, key=lambda q: ((q[0] - p[0]) * d[1] - (q[1] - p[1]) * d[0]))
            outs.remove(q)
            if not outs:
                del nxt[p]
            d, p = (q[0] - p[0], q[1] - p[1]), q
            if p == start:
                break
            pts.append(p)
        # drop points in the middle of straight runs
        n = len(pts)
        pts = [pts[i] for i in range(n) if (pts[i][0] - pts[i - 1][0]) * (pts[(i + 1) % n][1] - pts[i][1])
               != (pts[i][1] - pts[i - 1][1]) * (pts[(i + 1) % n][0] - pts[i][0])]
        contours.append(pts)
    return contours


def glyph_name(ch):
    return UV2AGL.get(ord(ch), f"uni{ord(ch):04X}")


def ts(s):  # TrueType timestamps count seconds from 1904
    return int((datetime.fromisoformat(s) - datetime(1904, 1, 1)).total_seconds())


def build_font(bms):
    advance = (CW + CFG["spacing"]) * U
    ascent, descent = BASE * U, (CH - BASE) * U
    notdef = {(x, y) for x in range(CW) for y in range(CAP) if x in (0, CW - 1) or y in (0, CAP - 1)}
    shapes = {".notdef": notdef, **{glyph_name(c): p for c, p in bms.items()}}

    glyphs, metrics = {}, {}
    for name, px in shapes.items():
        pen = TTGlyphPen(None)
        for contour in outline(px):
            pen.moveTo((contour[0][0] * U, contour[0][1] * U))
            for x, y in contour[1:]:
                pen.lineTo((x * U, y * U))
            pen.closePath()
        glyphs[name] = pen.glyph()
        metrics[name] = (advance, min((x for x, _ in px), default=0) * U)

    cmap = {ord(c): glyph_name(c) for c in bms}
    cmap[0xA0] = cmap[0x20]  # no-break space
    name = CFG["name"]
    version = f"{float(CFG['version']):.3f}"

    # 1em = 10px keeps every font pixel whole at 10/20/30px; the extra headroom only adds line height
    fb = FontBuilder(CFG["em"] * U, isTTF=True)
    fb.setupGlyphOrder(list(shapes))
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent, descent=-descent, lineGap=0)
    fb.setupNameTable({
        "copyright": CFG["copyright"],
        "familyName": name,
        "styleName": "Regular",
        "uniqueFontIdentifier": f"{version};{name}-Regular",
        "fullName": f"{name} Regular",
        "version": f"Version {version}",
        "psName": f"{name}-Regular",
        "designer": CFG["author"],
        "description": CFG["description"],
        "licenseDescription": CFG["license"],
        "licenseInfoURL": CFG["license-url"],
        "sampleText": CFG["sample-text"],
    })
    panose = Panose()
    panose.bFamilyType, panose.bProportion = 2, 9  # latin text, monospaced
    fb.setupOS2(
        version=4, fsType=0, achVendID="NONE", panose=panose,
        fsSelection=0x40 | 0x80,  # REGULAR | USE_TYPO_METRICS
        sTypoAscender=ascent, sTypoDescender=-descent, sTypoLineGap=0,
        usWinAscent=ascent, usWinDescent=descent,
        sxHeight=CFG["x-height"] * U, sCapHeight=CAP * U,
        usDefaultChar=0, usBreakChar=32,
    )
    os2 = fb.font["OS/2"]
    os2.recalcUnicodeRanges(fb.font)
    os2.recalcCodePageRanges(fb.font)
    fb.setupPost(isFixedPitch=1, underlinePosition=-U, underlineThickness=U)
    fb.updateHead(fontRevision=float(CFG["version"]), created=ts(CFG["created"]), modified=ts(CFG["modified"]))
    fb.font.recalcTimestamp = False  # keep builds byte-for-byte reproducible
    return fb.font


def check(path, bms):
    """Every pixel center must be inside the outline exactly when the sheet has ink there."""
    font = TTFont(path)
    gs, cmap = font.getGlyphSet(), font.getBestCmap()
    for ch, px in bms.items():
        for x in range(CW):
            for y in range(BASE - CH, BASE):
                pen = PointInsidePen(gs, ((x + 0.5) * U, (y + 0.5) * U))
                gs[cmap[ord(ch)]].draw(pen)
                assert pen.getResult() == ((x, y) in px), f"outline of {ch!r} is wrong at {x},{y}"
    assert {font["hmtx"][g][0] for g in font.getGlyphOrder()} == {(CW + CFG["spacing"]) * U}, "not monospaced"


def stale_accents(bms):
    """Accented letters whose body no longer matches their base letter (e.g. A redrawn, À not)."""
    import unicodedata
    out = []
    for ch, px in bms.items():
        base, *marks = unicodedata.normalize("NFD", ch)
        if not marks or base not in bms:
            continue
        top = CAP if base.isupper() else CFG["x-height"]  # accents sit above this row
        bottom = 0 if marks[0] == "̧" else BASE - CH  # a cedilla sits below the baseline
        body = lambda p: {(x, y) for x, y in p if bottom <= y < top}
        if body(px) != body(bms[base]):
            out.append(f"{ch} (base {base})")
    return out


# ---------- README images ----------
# Drawn straight from the glyph bitmaps, on the same grid as the specimen site: a column is one character
# (6 font pixels) and a row is one line (13 font pixels) of 20px text. Coordinates below are in those font
# pixels. Images are saved at twice the size the README shows them (width = columns x 12), so they stay
# sharp on high-density screens and scale down by exactly half everywhere else.
P = 4  # image pixels per font pixel of 20px text
COLS = 66
RGB = {"paper": "#f2eddf", "grid": "#e6dfcb", "ink": "#1d2419", "muted": "#6d6a55", "moss": "#4c7a33", "sprout": "#7fb24a",
       "soil": "#8a5a35", "root": "#b4532a", "label": "#f6e6a2", "sky": "#3d6b8a"}


def rgb(c):
    return c if isinstance(c, tuple) else ImageColor.getrgb(RGB.get(c, c))


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(rgb(a), rgb(b)))


class Sheet:
    """Grid paper. Frames are one font pixel thick and centred on grid lines, with their corner pixels cut away."""

    def __init__(self, bms, rows, cols=COLS):
        self.bms, self.w, self.h = bms, cols * 6, rows * 13
        self.img = Image.new("RGBA", (self.w * P, self.h * P))
        self.draw = ImageDraw.Draw(self.img)
        self.rect(0, 0, self.w, self.h, "paper")
        for x in range(0, self.w, 6):
            self.rect(x, 0, .5, self.h, "grid")
        for y in range(0, self.h, 13):
            self.rect(0, y, self.w, .5, "grid")

    def rect(self, x, y, w, h, colour):
        x0, y0, x1, y1 = (round(v * P) for v in (x, y, x + w, y + h))
        if x1 > x0 and y1 > y0:
            self.draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=rgb(colour))

    def notch(self, x, y):
        """Cut the corner pixel at grid point (x, y) back to bare grid paper."""
        self.rect(x - .5, y - .5, 1, 1, "paper")
        if x % 6 == 0:
            self.rect(x, y - .5, .5, 1, "grid")
        if y % 13 == 0:
            self.rect(x - .5, y, 1, .5, "grid")

    def frame(self, x, y, w, h, notch=True):
        for args in ((x - .5, y - .5, w + 1, 1), (x - .5, y + h - .5, w + 1, 1), (x - .5, y - .5, 1, h + 1), (x + w - .5, y - .5, 1, h + 1)):
            self.rect(*args, "ink")
        if notch:
            for corner in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                self.notch(*corner)

    def box(self, col, row, cols, rows, fill):
        x, y, w, h = col * 6, row * 13, cols * 6, rows * 13
        self.rect(x, y, w, h, fill)
        self.frame(x, y, w, h)
        return x, y

    def text(self, x, y, s, colour="ink", px=1):
        """Draw s (a string, or a list of (string, colour) runs) with its first character cell at (x, y)."""
        runs = [(s, colour)] if isinstance(s, str) else s
        n = sum(len(r) for r, _ in runs)
        assert x + n * 6 * px <= self.w, f"text runs off the image: {s!r}"
        i = 0
        for run, c in runs:
            for ch in run:
                for gx, gy in self.bms.get(ch, ()):
                    self.rect(x + (i * 6 + gx) * px, y + (BASE - 1 - gy) * px, px, px, c)
                i += 1

    def save(self, path):
        w, h = self.w, self.h  # the image edge gets a frame too, with transparent corner pixels
        for args in ((0, 0, w, 1), (0, h - 1, w, 1), (0, 0, 1, h), (w - 1, 0, 1, h)):
            self.rect(*args, "ink")
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            self.rect(x, y, 1, 1, (0, 0, 0, 0))
        self.img.save(path, optimize=True)


def build_specimen(bms, path):
    """The name, a spec sheet, and the font in use in code and a terminal."""
    s = Sheet(bms, rows=20)
    s.text(12, 13, "Bitroot", px=6)  # each font pixel is 6x6, so each letter covers 6x6 grid cells
    specs = [("version", CFG["version"]), ("cell", f"{CW}×{CH} px"), ("advance", f"{CW + CFG['spacing']} px"),
             ("glyphs", str(sum(not c.isspace() for c in bms))), ("formats", "TTF, WOFF2"), ("license", "OFL 1.1")]
    for i, (k, v) in enumerate(specs):
        s.text(46 * 6, (1 + i) * 13, [(k.ljust(8), "muted"), (v, "ink")])
    s.text(12, 8 * 13, "A monospaced pixel font for code, terminals and small screens.")

    K, F, N, S_, C, T = "#ff9f6b", "#79c0e6", "#e6c86e", "#b8db7a", "#8a8f7a", "#e6e1cf"
    code = [
        [("fn", K), (" ", T), ("main", F), ("() {", T)],
        [("    let", K), (" x = ", T), ("0x1F", N), ("; ", T), ("// 0O 1lI", C)],
        [("    if", K), (" x != ", T), ("0", N), (" && x <= ", T), ("31", N), (" {", T)],
        [("        println!", F), ("(", T), ('"{x}"', S_), (");", T)],
        [("    }", T)],
        [("}", T)],
    ]
    sizes = {f: (ROOT / f).stat().st_size for f in ("bitroot.ttf", "bitroot.woff2")}
    width = len(str(sum(sizes.values()))) + 1
    G, T2 = "#7dff8a", "#b7f5bd"
    term = [
        [("$ ", G), ("python build.py", T2)],
        [(f"built {sum(not c.isspace() for c in bms)} glyphs", T2)],
        [("$ ", G), ("wc -c bitroot.*", T2)],
        *[[(f"{n:>{width}} {f}", T2)] for f, n in sizes.items()],
        [(f"{sum(sizes.values()):>{width}} total", T2)],
    ]
    for col, bg, lines, caption in ((2, "#1b1f17", code, "0/O and 1/l/I stay distinct"), (34, "#08110a", term, "Output lines up in columns")):
        x, y = s.box(col, 10, 30, 8, bg)
        for i, line in enumerate(lines):
            s.text(x + 12, y + 13 * (i + 1), line)
        s.text(x, 18 * 13, caption, "muted")
    s.save(path)


def build_metrics(bms, path):
    """Three glyphs drawn large on their pixel grid, with the vertical metrics marked."""
    Z, x0, y0, word = 13, 12, 13, "Åbg"  # Z grid units per font pixel, so each pixel row is exactly one grid row
    s = Sheet(bms, rows=19)
    w, h = len(word) * 6 * Z, CH * Z
    bands = [(0, BASE - CAP, mix("paper", "sky", .18)), (BASE - CAP, BASE - CFG["x-height"], mix("paper", "sprout", .22)),
             (BASE - CFG["x-height"], BASE, mix("paper", "moss", .18)), (BASE, CH, mix("paper", "soil", .28))]
    for top, bottom, colour in bands:
        s.rect(x0, y0 + top * Z, w, (bottom - top) * Z, colour)
        for cell in range(len(word)):  # the spacing column after each glyph is dithered
            for r in range(top * Z, bottom * Z):
                for c in range(Z):
                    if (r + c) % 2:
                        s.rect(x0 + (cell * 6 + CW) * Z + c, y0 + r, 1, 1, mix(colour, "ink", .07))
        line = mix(colour, "ink", .14)
        for gx in range(0, w, Z):
            s.rect(x0 + gx, y0 + top * Z, .5, (bottom - top) * Z, line)
        for gy in range(top, bottom):
            s.rect(x0, y0 + gy * Z, w, .5, line)
    s.text(x0, y0, word, px=Z)
    s.rect(x0, y0 + BASE * Z - .5, 53 * 6 - x0, 1, "root")  # baseline, carried under its label
    s.frame(x0, y0, w, h)

    def bracket(col, top, bottom):
        x, ya, yb = col * 6 + 3, y0 + top * Z, y0 + bottom * Z
        s.rect(x, ya + 2, 1, yb - ya - 4, "ink")
        s.rect(x - 3, ya + 2, 3, 1, "ink")
        s.rect(x - 3, yb - 3, 3, 1, "ink")

    bracket(43, 0, BASE - CAP)
    bracket(42, BASE - CAP, BASE)
    bracket(43, BASE - CFG["x-height"], BASE)
    bracket(43, BASE, CH)
    labels = [(1, "accent space", BASE - CAP), (4, "cap height", CAP), (7, "x-height", CFG["x-height"]), (11, "descender", CH - BASE)]
    for row, name, size in labels:
        s.text(45 * 6, y0 + row * 13, [(name.ljust(14), "ink"), (f"{size}px", "moss")])
    s.text(45 * 6, y0 + BASE * 13, "baseline", "root")

    y = 15 * 13  # the advance, measured under the first glyph
    s.rect(x0, y - .5, 6 * Z, 1, "ink")
    for x in (x0, x0 + CW * Z, x0 + 6 * Z):
        s.rect(x - .5, y - 3, 1, 6, "ink")
    s.text(x0, y, [("advance ", "ink"), (f"{CW + CFG['spacing']}px", "moss")])
    s.text(x0, y + 13, f"{CW}px glyph + {CFG['spacing']}px spacing", "muted")
    table = [("units per em", CFG["em"] * U), ("ascent", BASE * U), ("descent", (CH - BASE) * U), ("line gap", 0)]
    for i, (k, v) in enumerate(table):
        s.text(45 * 6, (14 + i) * 13, [(k.ljust(14), "muted"), (str(v).rjust(3), "ink")])
    s.save(path)


def build_sizes(bms, path):
    """The same text at 10, 20, 30 and 40px, each label sitting on its sample's baseline."""
    s = Sheet(bms, rows=13)
    samples = [(1, .5, "The quick brown fox jumps over the lazy dog. 0123456789 !?&@#$%*()[]{}"),
               (3, 1, "The quick brown fox jumps over the lazy dog."),
               (6, 1.5, "The quick brown fox jumps"),
               (10, 2, "Bitroot 0123456789")]
    for row, px, text in samples:
        baseline = row * 13 + BASE
        s.text(12, row * 13, f"{round(px * 20)}px", "muted")
        s.text(48, baseline - BASE * px, text, px=px)
    s.save(path)


def build_charset(bms, path):
    """Every glyph at 30px in a table, grouped by Unicode block, with the baseline marked in each cell."""
    chars = [c for row in CFG["rows"] for c in row if not c.isspace()]
    ascii_ = [c for c in chars if ord(c) < 128]
    groups = [("Basic Latin: capitals", [c for c in ascii_ if c.isupper()]),
              ("Basic Latin: lowercase", [c for c in ascii_ if c.islower()]),
              ("Basic Latin: figures and punctuation", [c for c in ascii_ if not c.isalpha()]),
              ("Latin-1: letters", [c for c in chars if ord(c) >= 128 and c.isalpha()]),
              ("Latin-1 and General Punctuation: symbols", [c for c in chars if ord(c) >= 128 and not c.isalpha()])]
    assert sum(len(g) for _, g in groups) == len(chars)
    per_row, cw, rh, px = 20, 18, 26, 1.5  # a cell is 3 columns by 2 rows; the 9x19.5 glyph cell sits inside it
    s = Sheet(bms, rows=1 + sum(2 + 2 * -(-len(g) // per_row) for _, g in groups))  # heading, cells, blank row
    row = 1
    for name, glyphs in groups:
        s.text(18, row * 13, [(name, "ink"), (f"  {len(glyphs)}", "moss")])
        x0, y0 = 18, (row + 1) * 13
        guide = mix("paper", "root", .35)
        for i, ch in enumerate(glyphs):
            x, y = x0 + i % per_row * cw, y0 + i // per_row * rh
            s.rect(x, y, cw, rh, "paper")
            s.rect(x, y + 3 + BASE * px, cw, .5, guide)
            s.text(x + 4.5, y + 3, ch, px=px)
        for i in range(len(glyphs)):
            s.frame(x0 + i % per_row * cw, y0 + i // per_row * rh, cw, rh, notch=False)
        rows = -(-len(glyphs) // per_row)
        last = (len(glyphs) - 1) % per_row + 1
        full = min(len(glyphs), per_row) * cw
        for corner in ((x0, y0), (x0 + full, y0), (x0, y0 + rows * rh), (x0 + last * cw, y0 + rows * rh), (x0 + full, y0 + (rows - 1) * rh)):
            s.notch(*corner)
        row += 2 + 2 * rows
    s.save(path)


def write_site_data(path):
    """Glyph list for the specimen site (site/index.html), in sheet order."""
    import unicodedata

    def kind(ch):
        if unicodedata.category(ch).startswith("N"):
            return "figure"
        if not ch.isalpha():
            return "symbol"
        return "accented" if len(unicodedata.normalize("NFD", ch)) > 1 else "letter"

    chars = [c for row in CFG["rows"] for c in row if not c.isspace()]
    data = {"version": CFG["version"], "glyphs": [[c, unicodedata.name(c, ""), kind(c)] for c in chars]}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", "utf-8", newline="\n")


def main():
    cels, parents, size = read_aseprite(ROOT / "src/bitroot-typeface.aseprite")
    sheet = flatten(cels, [n for n, p in parents.items() if p == "Glyphs"], size)
    bms = bitmaps(sheet)

    font = build_font(bms)
    font.save(ROOT / "bitroot.ttf")
    check(ROOT / "bitroot.ttf", bms)
    font = TTFont(ROOT / "bitroot.ttf", recalcTimestamp=False)
    font.flavor = "woff2"
    font.save(ROOT / "bitroot.woff2")

    images = ROOT / "images"
    images.mkdir(exist_ok=True)
    build_specimen(bms, images / "specimen.png")
    build_metrics(bms, images / "metrics.png")
    build_sizes(bms, images / "sizes.png")
    build_charset(bms, images / "charset.png")
    write_site_data(ROOT / "site/glyphs.json")
    print(f"built {sum(not c.isspace() for c in bms)} glyphs")
    if stale := stale_accents(bms):
        print("warning: redraw these to match their base letter:", ", ".join(stale))


if __name__ == "__main__":
    main()
