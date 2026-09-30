"""Loopback-only visual experiment server with bounded, cached terrain and imagery.

Imagery is fetched only from the four county-published WMTS layers. Terrain
combines the four frozen USGS pilot rasters with Mapzen context. No API key,
external deployment, invented imagery, or stale-image substitution is used.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from io import BytesIO
import argparse
import hashlib
import json
import math
import ssl
import threading
import time
import urllib.request

import certifi
import numpy as np
from PIL import Image
import pyproj
import rasterio
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'data/out/scene-prototype'
CACHE = ROOT / 'data/raw/palisades-map'
BOUNDS = [-118.585, 34.024, -118.493, 34.103]
LAYERS = {'july2026': 'PICT-LARIAC8--pGc1fsJ6vr', 'october2025': 'PICT-LARIAC7--YRwyJETYPH',
          'january2025': 'PICT-LARIAC7--TiSy8NkPsY', 'summer2024': 'PICT-LARIAC7--TTfEQPUUgh'}
WMTS = 'https://svc.pictometry.com/Image/BCC27E3E-766E-CE0B-7D11-AA4760AC43ED/wmts/'
NETWORK = threading.BoundedSemaphore(8)
LOCKS = [threading.Lock() for _ in range(61)]


def remote(url: str) -> bytes:
    path = CACHE / 'http' / (hashlib.sha256(url.encode()).hexdigest() + '.bin')
    with LOCKS[hash(url) % len(LOCKS)]:
        if path.exists():
            return path.read_bytes()
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (OpenPali local visual research)'})
        # The upstream sometimes resets a healthy image request. Retry that
        # transient failure before telling the renderer that a tile is absent.
        for attempt in range(3):
            try:
                with NETWORK, urllib.request.urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=35) as r:
                    data = r.read()
                break
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(.2 * (attempt + 1))
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError(f'Expected PNG image: {url}')
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(data)
        return data


def tile_xy(lon, lat, z):
    return (lon + 180) / 360 * 2 ** z, (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * 2 ** z


def check_tile(z, x, y, maximum=21):
    if not 11 <= z <= maximum or not (0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise ValueError('Tile coordinates outside supported range')
    w, s, e, n = BOUNDS
    x0, y0 = tile_xy(w, n, z)
    x1, y1 = tile_xy(e, s, z)
    if not (math.floor(x0) - 1 <= x <= math.floor(x1) + 1 and math.floor(y0) - 1 <= y <= math.floor(y1) + 1):
        raise ValueError('Tile outside Palisades research extent')


@lru_cache(maxsize=32)
def coarse(z, x, y):
    rgb = np.asarray(Image.open(BytesIO(remote(f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'))).convert('RGB'), dtype=np.float64)
    return rgb[:, :, 0] * 256 + rgb[:, :, 1] + rgb[:, :, 2] / 256 - 32768


class Terrain:
    def __init__(self):
        self.to_utm = pyproj.Transformer.from_crs(4326, 6340, always_xy=True)
        self.rasters = []
        for path in sorted((CACHE / 'dem').glob('*.tif')):
            with rasterio.open(path) as ds:
                if ds.crs.to_epsg() != 6340 or ds.res != (0.5, 0.5):
                    raise ValueError('Unexpected USGS pilot DEM grid')
                self.rasters.append((ds.read(1), ds.transform, ds.nodata))
        print(f'Terrain: {len(self.rasters)} USGS pilot rasters; regional Mapzen context', flush=True)

    def tile(self, z, x, y):
        path = OUT / 'terrain-cache' / str(z) / str(x) / f'{y}.png'
        if path.exists():
            return path.read_bytes()
        check_tile(z, x, y, 17)
        cz = min(z, 15)
        factor = 2 ** (z - cz)
        cx, cy = x // factor, y // factor
        axis = (np.arange(256) + 0.5) / 256
        xx, yy = np.meshgrid(axis, axis)
        u, v = (x % factor + xx) / factor * 256 - 0.5, (y % factor + yy) / factor * 256 - 0.5
        h = map_coordinates(coarse(cz, cx, cy), [v, u], order=1, mode='nearest')
        lon = (x + xx) / 2 ** z * 360 - 180
        lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + yy) / 2 ** z))))
        ux, uy = self.to_utm.transform(lon, lat)
        # Sample the metric source grid. Blend only the outer edge of the whole
        # pilot rectangle, so internal source-tile borders remain exact.
        for data, transform, nodata in self.rasters:
            col, row = (~transform) * (ux, uy)
            valid = (col >= 0) & (row >= 0) & (col < data.shape[1]) & (row < data.shape[0])
            if not valid.any():
                continue
            values = map_coordinates(data, [row - .5, col - .5], order=1, mode='nearest')
            valid &= np.isfinite(values) & (values != nodata) & (values > -1000)
            d = np.minimum.reduce([ux - 358500, 360000 - ux, uy - 3767250, 3768750 - uy])
            weight = np.clip(d / 25, 0, 1)
            h[valid] = values[valid] * weight[valid] + h[valid] * (1 - weight[valid])
        if not np.isfinite(h).all():
            raise ValueError('Non-finite terrain sample')
        packed = np.clip(np.round((h + 32768) * 256), 0, 2 ** 24 - 1).astype(np.uint32)
        rgb = np.stack([packed >> 16, packed >> 8 & 255, packed & 255], axis=-1).astype(np.uint8)
        stream = BytesIO()
        Image.fromarray(rgb).save(stream, format='PNG')
        data = stream.getvalue()
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(data)
        return data


def atlas(dataset, node):
    if dataset not in LAYERS:
        raise ValueError('Unknown imagery layer')
    manifest = json.loads((OUT / 'buildings/manifest.json').read_text())
    record = next((n for n in manifest['nodes'] if str(n['id']) == node), None)
    if not record:
        raise ValueError('Unknown building node')
    a = record['atlas']
    path = OUT / 'atlas-cache' / dataset / f'{node}.png'
    if path.exists():
        return path.read_bytes()
    z, x0, y0, width, height = a['z'], a['x'], a['y'], a['width'], a['height']
    if width * height > 144:
        raise ValueError('Atlas request exceeds experiment bound')
    canvas = Image.new('RGBA', (width * 256, height * 256))

    def get(xy):
        x, y = xy
        raw = remote(f'{WMTS}{LAYERS[dataset]}/default/GoogleMapsCompatible/{z}/{x}/{y}.png')
        return x, y, Image.open(BytesIO(raw)).convert('RGBA')
    with ThreadPoolExecutor(max_workers=6) as ex:
        for x, y, img in ex.map(get, [(x, y) for x in range(x0, x0 + width) for y in range(y0, y0 + height)]):
            canvas.paste(img, ((x - x0) * 256, (y - y0) * 256))
    stream = BytesIO()
    canvas.save(stream, format='PNG')
    data = stream.getvalue()
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_bytes(data)
    return data


class Handler(SimpleHTTPRequestHandler):
    terrain: Terrain

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUT), **kwargs)

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        try:
            if path.startswith('/terrain/'):
                parts = path.split('/')
                if len(parts) != 5 or not parts[-1].endswith('.png'):
                    raise ValueError('Invalid terrain path')
                z, x, y = int(parts[2]), int(parts[3]), int(parts[4][:-4])
                payload = self.terrain.tile(z, x, y)
            elif path.startswith('/atlas/'):
                parts = path.split('/')
                if len(parts) != 4 or not parts[-1].endswith('.png'):
                    raise ValueError('Invalid atlas path')
                payload = atlas(parts[2], parts[3][:-4])
            else:
                return super().do_GET()
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(payload)
        except (ValueError, OSError, StopIteration) as e:
            self.send_error(503, str(e))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8941)
    args = parser.parse_args()
    Handler.terrain = Terrain()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'OpenPali aerial scene: http://127.0.0.1:{args.port}/', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
