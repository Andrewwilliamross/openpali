#!/usr/bin/env python3
"""Reproduce OpenPali's archived Parcel P identity (first design study).

For current Signal artwork, use assets/brand/signal/generate-assets.py.
Historical reproduction: python3 scripts/generate-brand.py
The decorative square fields are deterministic artwork, never real map or data.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "assets" / "brand"
BLUE = "#1557FF"
INK = "#10234A"
PALE = "#EAF0FF"
MID = "#C6D6FF"
SOFT = "#94B2FF"
WHITE = "#FFFFFF"
FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
MONO = "'SFMono-Regular', Consolas, 'Liberation Mono', monospace"
MATRIX = ("11110", "10001", "10001", "11110", "10000", "10000", "10000")
CATALOG: dict[str, dict[str, object]] = {}


def rect(x: float, y: float, width: float, height: float, fill: str) -> str:
    return f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" fill="{fill}"/>'


def text(x: float, y: float, value: str, size: float, *, fill: str = INK,
         weight: int = 650, spacing: float = 0, mono: bool = False) -> str:
    return (f'<text x="{x:g}" y="{y:g}" fill="{fill}" font-family="{escape(MONO if mono else FONT, quote=True)}" '
            f'font-size="{size:g}" font-weight="{weight}" letter-spacing="{spacing:g}">{escape(value)}</text>')


def mark(x: float, y: float, cell: float, gap: float, fill: str = BLUE) -> str:
    return '<g aria-hidden="true">' + ''.join(
        rect(x + col * (cell + gap), y + row * (cell + gap), cell, cell, fill)
        for row, line in enumerate(MATRIX) for col, value in enumerate(line) if value == "1"
    ) + '</g>'


def field(x: float, y: float, cols: int, rows: int, cell: float, gap: float,
          *, exclude: tuple[float, float, float, float] | None = None) -> str:
    """A repeatable, airy composition of discrete squares, with no data mapping."""
    shapes = []
    for row in range(rows):
        for col in range(cols):
            px, py = x + col * (cell + gap), y + row * (cell + gap)
            if exclude:
                ex, ey, ew, eh = exclude
                if px + cell > ex and px < ex + ew and py + cell > ey and py < ey + eh:
                    continue
            key = (col * 17 + row * 23 + col * row * 7) % 29
            # Breathing room around a diagonal; quiet outer cells and a few blue notes.
            if key < 8 or (col < 3 and row < 3) or (col > cols - 4 and row > rows - 4):
                continue
            fill = PALE if key < 22 else MID if key < 27 else SOFT
            if key == 28 and (row + col) % 4 == 0:
                fill = BLUE
            shapes.append(rect(px, py, cell, cell, fill))
    return '<g aria-hidden="true">' + ''.join(shapes) + '</g>'


def footer(x: float, y: float, size: float = 17) -> str:
    return rect(x, y - size + 3, 10, 10, BLUE) + text(
        x + 23, y, "PUBLIC EVIDENCE FOR THE PALISADES REBUILD", size,
        weight=500, spacing=1.7, mono=True)


def svg(name: str, width: int, height: int, title: str, description: str,
        body: str, *, background: str = "transparent") -> None:
    output = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
              f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">\n'
              f'  <title id="title">{escape(title)}</title>\n'
              f'  <desc id="description">{escape(description)}</desc>\n'
              f'  {body}\n</svg>\n')
    (DEST / name).write_text(output, encoding="utf-8")
    CATALOG[name] = {"width": width, "height": height, "background": background}


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    explanation = "An original P made from fifteen separated squares on a five-column, seven-row grid."
    svg("mark.svg", 256, 256, "OpenPali Parcel P", explanation,
        mark(51, 19, 26, 6))
    svg("mark-white.svg", 256, 256, "OpenPali Parcel P, white", explanation,
        mark(51, 19, 26, 6, WHITE))
    svg("avatar.svg", 512, 512, "OpenPali avatar", explanation,
        rect(0, 0, 512, 512, BLUE) + mark(144, 96, 40, 6, WHITE), background=BLUE)
    svg("wordmark.svg", 640, 128, "openpali", "OpenPali in blue, with the square-built Parcel P.",
        mark(16, 15, 12, 2) + text(114, 94, "openpali", 102, fill=BLUE, weight=700, spacing=-6))
    svg("wordmark-white.svg", 640, 128, "openpali", "OpenPali in white, with the square-built Parcel P.",
        mark(16, 15, 12, 2, WHITE) + text(114, 94, "openpali", 102, fill=WHITE, weight=700, spacing=-6))

    banner = rect(0, 0, 1600, 560, WHITE)
    banner += field(1018, 69, 17, 14, 20, 10, exclude=(1198, 117, 272, 326))
    banner += mark(1240, 144, 32, 8)
    banner += mark(66, 77, 12, 3) + text(174, 168, "openpali", 116, fill=BLUE, weight=700, spacing=-7)
    banner += text(64, 331, "Recovery, in the open.", 77, weight=650, spacing=-3.5)
    banner += rect(66, 414, 852, 1, MID) + footer(66, 474, 18)
    svg("banner.svg", 1600, 560, "OpenPali — Recovery, in the open.",
        "Public evidence for the Palisades rebuild. Blue square-built P marks and an abstract field of contribution-like squares on white. The squares are decorative artwork.",
        banner, background=WHITE)

    social = rect(0, 0, 1280, 640, WHITE)
    social += field(778, 72, 15, 15, 22, 10, exclude=(930, 155, 262, 346))
    social += mark(971, 187, 32, 8)
    social += mark(65, 78, 11, 3) + text(167, 159, "openpali", 108, fill=BLUE, weight=700, spacing=-6.5)
    social += text(64, 343, "Recovery,", 82, weight=650, spacing=-3.5)
    social += text(64, 439, "in the open.", 82, weight=650, spacing=-3.5)
    social += rect(66, 507, 652, 1, MID) + footer(66, 568, 17)
    svg("social-card.svg", 1280, 640, "OpenPali — Recovery, in the open.",
        "Public evidence for the Palisades rebuild. OpenPali's blue square-built identity on white. All background squares are decorative.",
        social, background=WHITE)

    square = rect(0, 0, 1080, 1080, WHITE)
    square += mark(72, 78, 14, 4) + text(208, 176, "openpali", 126, fill=BLUE, weight=700, spacing=-7.5)
    square += field(72, 306, 29, 11, 21, 11, exclude=(646, 300, 268, 350))
    square += mark(689, 331, 34, 8)
    square += text(72, 800, "Recovery,", 100, weight=650, spacing=-4.5)
    square += text(72, 909, "in the open.", 100, weight=650, spacing=-4.5)
    square += rect(74, 951, 932, 1, MID) + footer(74, 1010, 19)
    svg("social-square.svg", 1080, 1080, "OpenPali — Recovery, in the open.",
        "Public evidence for the Palisades rebuild. An abstract field of blue squares around the Parcel P. The field does not depict recovery data.",
        square, background=WHITE)

    # Pixel-aligned solid form: 16 px rendering keeps a three-pixel stem and open counter.
    favicon = '<path fill="' + BLUE + '" fill-rule="evenodd" d="M3 1h8v2h2v6h-2v2H6v4H3V1Zm3 3v4h4V4H6Z"/>'
    svg("favicon.svg", 16, 16, "OpenPali", "A solid, pixel-aligned blue P for small browser icons.", favicon)
    favicon_white = '<path fill="' + WHITE + '" fill-rule="evenodd" d="M3 1h8v2h2v6h-2v2H6v4H3V1Zm3 3v4h4V4H6Z"/>'
    svg("favicon-white.svg", 16, 16, "OpenPali", "A solid, pixel-aligned white P for dark browser icons.", favicon_white)

    ascii_mark = '\n'.join('  ' + ''.join('[]' if value == '1' else '  ' for value in line).rstrip()
                           for line in MATRIX)
    (DEST / "openpali.txt").write_text(
        ascii_mark + '\n\n  openpali\n  Recovery, in the open.\n\n  Public evidence for the Palisades rebuild.\n', encoding="utf-8")
    manifest = {
        "generator": "python3 scripts/generate-brand.py",
        "colors": {"blue": BLUE, "ink": INK, "white": WHITE, "pale": PALE,
                   "mid": MID, "soft": SOFT},
        "mark": {"name": "Parcel P", "columns": 5, "rows": 7, "filled_cells": 15,
                 "matrix": list(MATRIX)},
        "note": "Decorative square fields do not encode maps, people, progress, or evidence quality.",
        "assets": CATALOG,
    }
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + '\n', encoding="utf-8")
    print(f"Generated {len(CATALOG)} SVGs, openpali.txt, and manifest.json in {DEST}")


if __name__ == "__main__":
    main()
