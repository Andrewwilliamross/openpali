#!/usr/bin/env python3
"""Build the original 2D identity SVGs. Requires FontTools with WOFF2 support.

Rasterize with export-assets.cjs and Sharp. Only this directory is written.
County map geometry is embedded unchanged from the adjoining map/close source.
"""
from pathlib import Path
from html import escape
import re

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent / "field-office/fonts"
BLUE = "#1557ff"
INK = "#183554"


def font(name, axes):
    value = TTFont(FONTS / name)
    return instantiateVariableFont(value, axes)


DISPLAY = font("Fraunces.woff2", {"wght": 450, "opsz": 144, "SOFT": 35, "WONK": 1})
BODY = font("DMSans.woff2", {"wght": 450, "opsz": 14})


def text(value, x, y, size, color=INK, face=DISPLAY, tracking=0):
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


def inner_svg(path):
    source = path.read_text()
    source = re.sub(r"^<svg\b[^>]*>", "", source.strip())
    source = re.sub(r"</svg>\s*$", "", source)
    return re.sub(r"<(title|desc)\b[^>]*>.*?</\1>", "", source, flags=re.S)


BIRD = inner_svg(HERE / "pelican.svg")
MAP = inner_svg(HERE / "map/close/alphabet-streets-linework.svg")
METADATA = """Original OpenPali 2D pelican and identity artwork. The pelican is illustrative.
Actual parcel/street geometry: Los Angeles County Office of the Assessor and
Los Angeles County Countywide Address Management System (CAMS).
Source and coordinate provenance: map/close/provenance.json.
Terms: https://egis-lacounty.hub.arcgis.com/pages/terms-of-use .
The County does not endorse this project. Geometry shows no property condition,
construction, damage, or recovery status. Fonts: Fraunces and DM Sans, SIL OFL 1.1.
"""


def svg(width, height, name, body, map_present=False):
    metadata = f"<metadata>{escape(METADATA)}</metadata>" if map_present else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="asset-title asset-description">
<title id="asset-title">{name}</title>
<desc id="asset-description">OpenPali. A place with footnotes. Public evidence for the Palisades rebuild. A smooth white and cobalt pelican carries a paper field notebook.</desc>
{metadata}<rect width="{width}" height="{height}" fill="white"/>{body}</svg>'''


def bird(x, y, size):
    return f'<g transform="translate({x} {y}) scale({size/260})">{BIRD}</g>'


def map_detail(x, y, width, height):
    # A uniform viewBox crop; every source path and street label is retained.
    return f'<svg x="{x}" y="{y}" width="{width}" height="{height}" viewBox="40 85 750 560" preserveAspectRatio="xMidYMid meet" opacity=".62">{MAP}</svg>'


def wordmark(x, y, size=39):
    return text("openpali", x, y, size, BLUE) + text("*", x + size * 3.39, y-size*.44, size*.53, BLUE)


def write(name, width, height, title, body, map_present=False):
    (HERE / f"{name}.svg").write_text(svg(width, height, title, body, map_present))


def main():
    write("avatar", 512, 512, "OpenPali field-note pelican avatar",
          '<rect width="512" height="512" fill="#eef3ff"/>' + bird(26, 13, 465))

    # A single head and bill remains recognizable in a 16–32px browser tab.
    favicon = '''<rect width="32" height="32" rx="7" fill="#eef3ff"/>
<path d="M7 28c2-4 5-8 5-12-3-2-5-5-5-8 0-3 2-5 5-5 4 0 7 3 7 7 0 4-4 6-4 9 0 3 2 6 3 9Z" fill="#fffef9" stroke="#183554" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M18 11c3 1 7 3 12 5-2 5-6 7-10 6-3-1-4-5-4-8Z" fill="#dfeaff" stroke="#183554" stroke-width="1.2" stroke-linejoin="round"/>
<path d="M18 10c4 1 8 3 12 5l-1 2c-5-1-8-2-12-3-2-1-1-4 1-4Z" fill="#1557ff" stroke="#183554" stroke-width="1.1" stroke-linejoin="round"/>
<ellipse cx="14.4" cy="8.4" rx="1.2" ry="1.4" fill="#183554"/>'''
    write("favicon", 32, 32, "OpenPali pelican favicon", favicon)

    banner = (
        map_detail(748, 76, 717, 430)
        + '<path d="M744 81v-18h22M1481 489v21h-22" fill="none" stroke="#1557ff" stroke-width="1.5"/>'
        + bird(1146, 144, 374)
        + wordmark(71, 78, 39)
        + text("A place with", 68, 255, 102)
        + text("footnotes.", 68, 365, 120, BLUE)
        + text("Public evidence for the Palisades rebuild.", 75, 428, 24, face=BODY)
        + '<path d="M75 478h45" stroke="#1557ff" stroke-width="2"/>'
        + text("A LITTLE CONTEXT GOES A LONG WAY.", 75, 511, 12, BLUE, BODY, .55)
        + text("PACIFIC PALISADES / FIELD NOTES", 778, 51, 11, BLUE, BODY, .9)
        + text("Map: LA County Assessor · LA County CAMS", 778, 552, 11, face=BODY)
        + text("Illustrative character. No property status shown.", 778, 572, 10, "#617084", BODY)
    )
    write("banner", 1600, 600, "OpenPali — A place with footnotes", banner, True)

    social = (
        map_detail(570, 153, 650, 379)
        + '<path d="M593 139v-17h21M1223 506v22h-21" fill="none" stroke="#1557ff" stroke-width="1.4"/>'
        + bird(892, 178, 331)
        + wordmark(64, 76, 39)
        + text("A place with", 61, 258, 91)
        + text("footnotes.", 61, 361, 110, BLUE)
        + text("Public evidence for", 68, 421, 24, face=BODY)
        + text("the Palisades rebuild.", 68, 454, 24, face=BODY)
        + '<path d="M68 499h42" stroke="#1557ff" stroke-width="2"/>'
        + text("A LITTLE CONTEXT GOES A LONG WAY.", 68, 531, 10.5, BLUE, BODY, .45)
        + text("PACIFIC PALISADES / FIELD NOTES", 610, 106, 10, BLUE, BODY, .7)
        + text("Map: LA County Assessor · LA County CAMS", 612, 568, 10.5, face=BODY)
        + text("Illustrative character. No property status shown.", 612, 586, 9.5, "#617084", BODY)
    )
    write("social-card", 1280, 640, "OpenPali — Public evidence for the Palisades rebuild", social, True)
    print("Built favicon, avatar, banner, and social-card SVGs with outlined local type.")


if __name__ == "__main__":
    main()
