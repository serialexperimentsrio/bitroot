"""Build bitroot.ttf, bitroot.woff2 and preview.png from src/bitroot-typeface.aseprite.

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
from PIL import Image

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


def build_preview(bms, grid_cell, path, scale=10):
    """Glyphs in pairs (Aa Bb … then everything else in sheet order) on a checkerboard."""
    chars = [c for row in CFG["rows"] for c in row if not c.isspace()]
    pairs = [u + u.lower() for u in chars if u.isupper() and u.lower() in chars]
    rest = [c for c in chars if not any(c in p for p in pairs)]
    pairs += ["".join(rest[i:i + 2]) for i in range(0, len(rest), 2)]
    pairs.sort(key=lambda p: chars.index(p[0]))
    cols, box, box_h = 13, 16, CH + 6
    img = Image.new("RGBA", (cols * box, -(-len(pairs) // cols) * box_h))
    for i, pair in enumerate(pairs):
        cx, cy = i % cols * box, i // cols * box_h
        shade = 77 if (i % cols + i // cols) % 2 == 0 else 57
        img.paste((shade, shade, shade, 255), (cx, cy, cx + box, cy + box_h))
        for k, ch in enumerate(pair):
            x0, y0 = cx + 2 + k * (CW + 2), cy + 3
            img.alpha_composite(grid_cell, (x0, y0))
            for x, y in bms[ch]:
                img.putpixel((x0 + x, y0 + BASE - 1 - y), (255, 255, 255, 255))
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).convert("RGB").save(path, optimize=True)


SPECIMEN = [  # (text, font size in px, colour) - sizes are multiples of 10 so every pixel stays sharp
    ("Bitroot", 30, (246, 153, 136)),
    ("Quiet foxes jump over blazing red maples,", 10, (255, 255, 255)),
    ("watching dark pines sway.", 10, (255, 255, 255)),
    ("", 10, None),
    ("THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG", 10, (176, 190, 197)),
    ("0123456789 !?&@#$%*()[]{}<>+-=/\\|~^_", 10, (176, 190, 197)),
    ("Ça va? Über naïve façade — «déjà vu», ±5°", 10, (176, 190, 197)),
    ("", 10, None),
    ('if (list[i] != 0 && flags | 0x1F) return "ok";', 10, (114, 213, 114)),
]


def build_specimen(font_path, path, scale=4, pad=10):
    """Sample text drawn with the built font itself, so the image always matches the font."""
    from PIL import ImageDraw, ImageFont
    fonts = {size: ImageFont.truetype(str(font_path), size) for _, size, _ in SPECIMEN}
    line_h = lambda size: size * (CH) // CFG["em"]  # 13px per 10px of font size
    width = max(int(fonts[s].getlength(t)) for t, s, _ in SPECIMEN) + 2 * pad
    height = sum(line_h(s) for _, s, _ in SPECIMEN) + 2 * pad
    img = Image.new("RGB", (width, height), (36, 36, 40))
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"  # no anti-aliasing: whole pixels only
    y = pad
    for text, size, colour in SPECIMEN:
        if text:
            draw.text((pad, y), text, font=fonts[size], fill=colour, anchor="la")
        y += line_h(size)
    img.resize((width * scale, height * scale), Image.NEAREST).save(path, optimize=True)


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

    gx, gy, grid = cels["Grid"]
    ox, oy = CFG["cell-offset"] - gx, CFG["cell-offset"] - gy
    cell = grid.crop((ox, oy, ox + CW, oy + CH))
    cell.putalpha(cell.getchannel("A").point(lambda a: a * 2 // 5))  # the Grid layer is drawn at ~40% opacity
    build_preview(bms, cell, ROOT / "preview.png")
    build_specimen(ROOT / "bitroot.ttf", ROOT / "specimen.png")
    print(f"built {len(bms)} glyphs")
    if stale := stale_accents(bms):
        print("warning: redraw these to match their base letter:", ", ".join(stale))


if __name__ == "__main__":
    main()
