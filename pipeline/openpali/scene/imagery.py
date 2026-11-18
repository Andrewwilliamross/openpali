"""Aerial imagery: a WebP mirror of the ground tiles around the release's
parcels, and the stitched roof image each building batch is textured with.

    python -m openpali.scene.imagery [--plan] [--offline]

The county's vendor serves 256 px PNGs of 130-165 KB, uncacheable, over six
HTTP/1.1 connections. The mirror keeps the same z/x/y scheme at about a
seventh of the bytes, so the map asks its own host first and the vendor only
for what is not mirrored (the finest zoom, and anywhere away from the parcels).

Source tiles land in ``data/raw/imagery/<layer>/z/x/y.png``; an interrupted
run resumes from them. Output is ``data/out/imagery/<layer>/z/x/y.webp`` plus
``index.json``, which is written last.
"""
from __future__ import annotations

import argparse
import http.client
import io
import json
import os
import ssl
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import numpy as np
from PIL import Image

from .sources import ROOT, Missing, mercator

#: EagleView 2026 mosaic on the county's LARIAC WMTS account (also MapView.tsx)
LAYER = 'PICT-CALOSA26-WX2j52mKfq'
TILES = ('https://svc.pictometry.com/Image/BCC27E3E-766E-CE0B-7D11-AA4760AC43ED/wmts/'
         f'{LAYER}/default/GoogleMapsCompatible/{{z}}/{{x}}/{{y}}.png')
RAW = ROOT / 'data/raw/imagery' / LAYER
OUT = ROOT / 'data/out/imagery'
SCHEMA = 'openpali-imagery-v1'

#: parcels are covered by whole tiles of this zoom, plus one tile all round
COVER_ZOOM = 18
#: finest mirrored zoom; fetched, and the zooms down to COVER_ZOOM derived from it
TOP_ZOOM = 20
#: coarsest zoom the vendor serves
MIN_ZOOM = 11
QUALITY = 75
#: concurrent kept-alive connections to the vendor (about 12 requests a second)
WORKERS = 4
RETRIES = 5
ATLAS_MAX_PX = 2048

_context = ssl.create_default_context(cafile=certifi.where())
_local = threading.local()


def get(url: str) -> tuple[int, bytes]:
    """GET over this thread's kept-alive connection: a new TLS handshake per
    tile would cost several times the transfer itself."""
    parts = urllib.parse.urlsplit(url)
    connection = getattr(_local, 'connection', None)
    if connection is None:
        connection = _local.connection = http.client.HTTPSConnection(parts.netloc, context=_context, timeout=60)
    try:
        connection.request('GET', parts.path, headers={'User-Agent': 'tile-mirror/1'})
        response = connection.getresponse()
        return response.status, response.read()
    except Exception:
        connection.close()
        _local.connection = None
        raise


def raw_path(z: int, x: int, y: int) -> Path:
    return RAW / str(z) / str(x) / f'{y}.png'


def tile(z: int, x: int, y: int, *, offline: bool = False) -> bytes:
    """One source tile, from the raw cache or the vendor. Raises Missing on a 404."""
    path = raw_path(z, x, y)
    absent = path.with_suffix('.absent')
    if path.exists():
        return path.read_bytes()
    if absent.exists():
        raise Missing(f'{z}/{x}/{y}')
    if offline:
        raise FileNotFoundError(f'not in the raw cache (offline): imagery tile {z}/{x}/{y}')
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(RETRIES):
        try:
            status, raw = get(TILES.format(z=z, x=x, y=y))
        except (OSError, http.client.HTTPException):
            status, raw = 0, b''
        if status == 200:
            break
        if status == 404:
            absent.write_bytes(b'')
            raise Missing(f'{z}/{x}/{y}')
        if attempt == RETRIES - 1 or 400 <= status < 500:
            raise RuntimeError(f'imagery tile {z}/{x}/{y}: HTTP {status or "connection failed"}')
        time.sleep(2 ** attempt)
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'imagery tile {z}/{x}/{y} is not a PNG')
    partial = path.with_suffix(f'.{os.getpid()}.{time.monotonic_ns()}.part')
    partial.write_bytes(raw)
    partial.replace(path)
    return raw


def cover() -> list[tuple[int, int]]:
    """COVER_ZOOM tiles under any parcel of the current release, grown by one tile."""
    pointer = ROOT / 'data/out/evidence/current.json'
    release = json.loads(pointer.read_text())['release_id']
    parcels = json.loads((ROOT / 'data/out/evidence' / release / 'parcels.geojson').read_text())
    n = 2 ** COVER_ZOOM
    tiles: set[tuple[int, int]] = set()
    for feature in parcels['features']:
        geometry = feature.get('geometry')
        if not geometry:
            continue
        polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
        for polygon in polygons:
            ring = np.asarray(polygon[0])[:, :2]
            mx, my = mercator(ring[:, 0], ring[:, 1])
            for x in range(int(mx.min() * n) - 1, int(mx.max() * n) + 2):
                for y in range(int(my.min() * n) - 1, int(my.max() * n) + 2):
                    tiles.add((x, y))
    return sorted(tiles)


def webp(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, 'WEBP', quality=QUALITY, method=4)
    return out.getvalue()


def write(z: int, x: int, y: int, image: Image.Image) -> int:
    path = OUT / LAYER / str(z) / str(x) / f'{y}.webp'
    path.parent.mkdir(parents=True, exist_ok=True)
    body = webp(image)
    partial = path.with_suffix(f'.{os.getpid()}.{time.monotonic_ns()}.part')
    partial.write_bytes(body)
    partial.replace(path)
    return len(body)


def mirror_block(x: int, y: int, offline: bool) -> tuple[int, int, int]:
    """One COVER_ZOOM tile: its TOP_ZOOM tiles, and the zooms between derived
    from them. Returns (tiles written, source tiles missing, bytes written)."""
    done = OUT / LAYER / str(COVER_ZOOM) / str(x) / f'{y}.webp'
    if done.exists():  # written last, so its presence means the block is whole
        return 0, 0, 0
    span = 2 ** (TOP_ZOOM - COVER_ZOOM)
    canvas = Image.new('RGB', (span * 256, span * 256))
    written = missing = size = 0
    for row in range(span):
        for column in range(span):
            tx, ty = x * span + column, y * span + row
            try:
                image = Image.open(io.BytesIO(tile(TOP_ZOOM, tx, ty, offline=offline))).convert('RGB')
            except Missing:
                missing += 1
                continue
            canvas.paste(image, (column * 256, row * 256))
            size += write(TOP_ZOOM, tx, ty, image)
            written += 1
    if missing:
        # a hole in the source: leave the coarser tiles to the vendor too
        return written, missing, size
    for z in range(TOP_ZOOM - 1, COVER_ZOOM - 1, -1):
        canvas = canvas.resize((canvas.width // 2, canvas.height // 2), Image.Resampling.LANCZOS)
        scale = 2 ** (z - COVER_ZOOM)
        for row in range(scale):
            for column in range(scale):
                box = (column * 256, row * 256, column * 256 + 256, row * 256 + 256)
                size += write(z, x * scale + column, y * scale + row, canvas.crop(box))
                written += 1
    return written, 0, size


def mirror_low(z: int, x: int, y: int, offline: bool) -> int:
    """A tile coarser than the cover, taken from the vendor as it is."""
    if (OUT / LAYER / str(z) / str(x) / f'{y}.webp').exists():
        return 0
    try:
        return write(z, x, y, Image.open(io.BytesIO(tile(z, x, y, offline=offline))).convert('RGB'))
    except Missing:
        return 0


def ancestors(blocks: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    out: set[tuple[int, int, int]] = set()
    for x, y in blocks:
        for z in range(MIN_ZOOM, COVER_ZOOM):
            shift = COVER_ZOOM - z
            out.add((z, x >> shift, y >> shift))
    return sorted(out)


def atlas(z: int, x: int, y: int, width: int, height: int, *, offline: bool = False) -> bytes | None:
    """The roof image for a building batch: its tile rectangle stitched into
    one WebP, at most ATLAS_MAX_PX on a side. None when no tile is available."""
    px = max(64, min(256, ATLAS_MAX_PX // max(width, height)))
    canvas = Image.new('RGBA', (width * px, height * px))
    drawn = 0
    for row in range(height):
        for column in range(width):
            try:
                image = Image.open(io.BytesIO(tile(z, x + column, y + row, offline=offline))).convert('RGBA')
            except Missing:
                continue  # stays transparent: the shader leaves roofs neutral there
            if px != 256:
                image = image.resize((px, px), Image.Resampling.LANCZOS)
            canvas.paste(image, (column * px, row * px))
            drawn += 1
    if not drawn:
        return None
    out = io.BytesIO()
    (canvas if drawn < width * height else canvas.convert('RGB')).save(out, 'WEBP', quality=80, method=4)
    return out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='fail instead of fetching anything')
    parser.add_argument('--plan', action='store_true', help='list what a run would fetch, then stop')
    args = parser.parse_args(argv)

    blocks = cover()
    span = 2 ** (TOP_ZOOM - COVER_ZOOM)
    low = ancestors(blocks)
    top = [(TOP_ZOOM, x * span + c, y * span + r) for x, y in blocks for r in range(span) for c in range(span)]
    need = sum(1 for t in [*top, *low]
               if not raw_path(*t).exists() and not raw_path(*t).with_suffix('.absent').exists())
    if args.plan:
        print(json.dumps({
            'layer': LAYER, 'cover_tiles': len(blocks), 'source_tiles': len(top) + len(low),
            'source_tiles_to_fetch': need, 'bytes_each_about': 150_000,
            'download_gb_about': round(need * 150_000 / 1e9, 2),
            'hours_about': round(need / 12 / 3600, 2),
        }, indent=1))
        return 0

    print(f'{len(blocks):,} cover tiles; {need:,} source tiles to fetch', flush=True)
    started = time.monotonic()
    written = missing = size = 0
    holes: set[tuple[int, int]] = set()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = pool.map(lambda b: (b, mirror_block(*b, args.offline)), blocks)
        for count, (block, (w, m, s)) in enumerate(results, 1):
            written, missing, size = written + w, missing + m, size + s
            if m:
                holes.add(block)
            if count % 100 == 0:
                print(f'  {count:,}/{len(blocks):,} blocks, {size / 1e6:,.0f} MB written, '
                      f'{(time.monotonic() - started) / 60:.0f} min', flush=True)
        size += sum(pool.map(lambda t: mirror_low(*t, args.offline), low))

    index = {
        'schema': SCHEMA, 'layer': LAYER, 'tiles': f'{LAYER}/{{z}}/{{x}}/{{y}}.webp',
        'minzoom': MIN_ZOOM, 'maxzoom': TOP_ZOOM, 'cover_zoom': COVER_ZOOM,
        'cover': [list(b) for b in blocks if b not in holes],
    }
    staging = OUT / '.index.json'
    staging.write_text(json.dumps(index, separators=(',', ':')))
    os.replace(staging, OUT / 'index.json')
    print(json.dumps({
        'cover_tiles': len(index['cover']), 'blocks_with_holes': len(holes),
        'source_tiles_missing': missing, 'tiles_written_this_run': written,
        'mb_written_this_run': round(size / 1e6, 1), 'path': str(OUT.relative_to(ROOT)),
    }, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
