#!/usr/bin/env python3
"""Deterministic square-field identity. Requires FontTools with WOFF2 support.

Run export-assets.cjs with Sharp to generate PNGs from these self-contained SVGs.
The field is decorative. Tile placement never uses a letter, data, or map mask.
"""
from pathlib import Path
from html import escape
import json
import random

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HERE = Path(__file__).resolve().parent
FONT = HERE.parent / "fonts/DMSans.woff2"
BLUE = "#1557ff"
INK = "#10234a"


def load_font(weight, optical):
    return instantiateVariableFont(TTFont(FONT), {"wght": weight, "opsz": optical})


DISPLAY = load_font(675, 48)
WORDMARK = load_font(700, 36)
BODY = load_font(450, 14)


def type_paths(value, x, y, size, color=INK, face=DISPLAY, tracking=0):
    glyphs, cmap = face.getGlyphSet(), face.getBestCmap()
    scale = size / face["head"].unitsPerEm
    paths, offset = [], 0
    for char in value:
        glyph = glyphs[cmap[ord(char)]]
        pen = SVGPathPen(glyphs)
        glyph.draw(pen)
        paths.append(f'<path transform="translate({offset:.3f} 0)" d="{pen.getCommands()}"/>')
        offset += glyph.width + tracking / scale
    return f'<g aria-label="{escape(value)}" fill="{color}" transform="translate({x} {y}) scale({scale} {-scale})">{"".join(paths)}</g>'


def wrap(width, height, title, body, background=True):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="signal-title signal-description">
<title id="signal-title">{title}</title>
<desc id="signal-description">OpenPali. Understand the rebuild. A data platform for analyzing the Palisades rebuild. Decorative cobalt squares remain scattered on a fixed grid; they do not depict records or measurements.</desc>
{'<rect width="100%" height="100%" fill="white"/>' if background else ''}{body}</svg>'''


def field_data():
    rng = random.Random("openpali-signal-scatter-v1")
    squares = []
    for row in range(29):
        for col in range(25):
            if rng.random() < .11:
                continue
            selector = rng.random()
            size = rng.choices([3, 4, 5, 6, 8, 10, 12, 16], [12, 16, 17, 15, 14, 12, 9, 5])[0]
            opacity = rng.uniform(.10, .46)
            accent = selector > .971 and col > 4
            if accent:
                size, opacity = 22, rng.uniform(.72, 1)
            elif selector > .86:
                size, opacity = rng.choice([12, 16]), rng.uniform(.48, .76)
            # Opacity varies per tile; there is no SVG gradient or geometric mask.
            left_quiet = .10 + .90 * min(1, (col / 13) ** 1.7)
            opacity = round(opacity * left_quiet, 3)
            squares.append({"id": f"tile-{row:02d}-{col:02d}", "col": col, "row": row,
                            "cx": 64 + col * 28, "cy": 58 + row * 28,
                            "size": size, "opacity": opacity, "accent": accent})
    return {"width": 800, "height": 900, "columns": 25, "rows": 29, "step": 28,
            "seed": "openpali-signal-scatter-v1", "color": BLUE,
            "description": "Decorative scattered squares. No data, letter, or map mask.", "squares": squares}


def field_rects(data):
    return '<g id="signal-field" fill="#1557ff">' + ''.join(
        f'<rect id="{s["id"]}" x="{s["cx"]-s["size"]/2:g}" y="{s["cy"]-s["size"]/2:g}" width="{s["size"]}" height="{s["size"]}" opacity="{s["opacity"]}" data-col="{s["col"]}" data-row="{s["row"]}"/>'
        for s in data["squares"]
    ) + '</g>'


def cluster(x, y, scale=1):
    # Five unequal squares, with deliberately open, asymmetric spacing.
    pieces = [(0, 8, 6, .40), (9, 0, 8, 1), (17, 17, 7, .88),
              (27, 8, 4, .55), (8, 28, 5, .95)]
    return f'<g fill="{BLUE}" transform="translate({x} {y}) scale({scale})">' + ''.join(
        f'<rect x="{a}" y="{b}" width="{s}" height="{s}" opacity="{o}"/>' for a,b,s,o in pieces
    ) + '</g>'


def wordmark(x, y, size):
    return cluster(x, y-size*.82, size/40) + type_paths("openpali", x+size*1.12, y, size, BLUE, WORDMARK, -.7)


def main():
    data = field_data()
    field = field_rects(data)
    (HERE / "field.json").write_text(json.dumps(data, separators=(",", ":")) + "\n")
    (HERE / "field.svg").write_text(wrap(800, 900, "OpenPali scattered square field", field, False))

    banner = (
        f'<g transform="translate(800 -158)">{field}</g>'
        + wordmark(72, 72, 31)
        + type_paths("Understand", 100, 286, 142, BLUE, tracking=-6.3)
        + type_paths("the rebuild.", 100, 418, 142, BLUE, tracking=-6.3)
        + type_paths("A data platform for analyzing the Palisades rebuild.", 108, 473, 24, INK, BODY, -.15)
        + '<path d="M72 548H1528" stroke="#e5ebfa"/>'
        + type_paths("RECORDS / GEOSPATIAL DATA / IMAGERY", 74, 579, 10.5, BLUE, BODY, 1.05)
    )
    social = (
        f'<g transform="translate(622 -116) scale(.89)">{field}</g>'
        + wordmark(58, 72, 31)
        + type_paths("Understand", 78, 282, 114, BLUE, tracking=-5.1)
        + type_paths("the rebuild.", 78, 390, 114, BLUE, tracking=-5.1)
        + type_paths("A data platform for analyzing", 84, 446, 23, INK, BODY, -.15)
        + type_paths("the Palisades rebuild.", 84, 478, 23, INK, BODY, -.15)
        + '<path d="M58 577H1222" stroke="#e5ebfa"/>'
        + type_paths("RECORDS / GEOSPATIAL DATA / IMAGERY", 60, 610, 10, BLUE, BODY, .8)
    )
    avatar = cluster(111, 84, 9.3)
    favicon = cluster(3.6, 2.1, .78)
    for name, width, height, title, body in [
        ("banner", 1600, 600, "OpenPali — Understand the rebuild", banner),
        ("social-card", 1280, 640, "OpenPali — Understand the rebuild", social),
        ("avatar", 512, 512, "OpenPali scattered-square identity", avatar),
        ("favicon", 32, 32, "OpenPali scattered-square favicon", favicon),
        ("mark", 40, 40, "OpenPali asymmetric square cluster", cluster(4, 3, 1)),
        ("wordmark", 240, 58, "OpenPali wordmark", wordmark(5, 41, 35)),
    ]:
        (HERE / f"{name}.svg").write_text(wrap(width, height, title, body))
    (HERE / "openpali.txt").write_text("""    []       .
 .       []
       .       []        openpali
   []
                        Understand the rebuild.

A data platform for analyzing the Palisades rebuild.
RECORDS / GEOSPATIAL DATA / IMAGERY

https://github.com/Andrewwilliamross/openpali
""")
    (HERE / "manifest.json").write_text(json.dumps({
        "direction": "Signal / white and cobalt",
        "headline": "Understand the rebuild.",
        "compact_purpose": "A data platform for analyzing the Palisades rebuild.",
        "descriptor": "RECORDS / GEOSPATIAL DATA / IMAGERY",
        "palette": {"blue": BLUE, "ink": INK, "background": "#ffffff"},
        "font": {"name": "DM Sans", "headline_weight": 675, "source": "../fonts/DMSans.woff2", "license": "../fonts/DMSans-OFL.txt"},
        "field": {"viewBox": [0, 0, 800, 900], "tiles": len(data["squares"]),
                  "columns": 25, "rows": 29, "step": 28, "kind": "Decorative; no records, measurements, maps, or glyph mask"},
        "exports": {"banner": [1600, 600], "social-card": [1280, 640], "avatar": [512, 512], "favicon": [32, 32]},
        "rebuild": "Run generate-assets.py with FontTools, then export-assets.cjs with Sharp. Text is outlined in all SVGs."
    }, indent=2) + "\n")
    print(f"Generated {len(data['squares'])} independent field tiles, identity SVGs, and ASCII companion.")


if __name__ == "__main__":
    main()
