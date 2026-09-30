#!/usr/bin/env python3
"""Rebuild static brand glyphs. Authoring dependencies: FontTools and Brotli."""
import json
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets/brand/field-office"
PHRASES = ("openpali", "A place with", "footnotes.", "Leave a", "clearer record.")


def main():
    font = TTFont(BRAND / "fonts/Fraunces.woff2")
    font = instantiateVariableFont(
        font, {"wght": 450, "opsz": 144, "SOFT": 35, "WONK": 1}
    )
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    outlines = {}
    for phrase in PHRASES:
        offset = 0
        parts = []
        for char in phrase:
            name = cmap[ord(char)]
            pen = SVGPathPen(glyphs)
            glyphs[name].draw(pen)
            parts.append({"x": offset, "d": pen.getCommands()})
            offset += glyphs[name].width
        outlines[phrase] = {
            "units": font["head"].unitsPerEm,
            "width": offset,
            "parts": parts,
        }
    (BRAND / "type-outlines.json").write_text(
        json.dumps(outlines, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
