"""Remote sources for the scene build, with a content-hashed raw cache.

Every byte the build consumes is written to ``data/raw/scene`` under the
SHA-256 of its URL and recorded (hash, size) in the scene's provenance, so a
build is reproducible offline from the cache and an altered source is visible.
"""
from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import ssl
import struct
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import certifi
import numpy as np
import pyproj

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / 'data/raw/scene'
OUT = ROOT / 'data/out/scene'

# LA County LOD2 buildings (2023 geometry; county labels it non-authoritative)
SCENE_LAYER = ('https://tiles.arcgis.com/tiles/RmCCgQtiZLDCtblq/arcgis/rest/services/'
               'Palisades_3D_Buildings/SceneServer/layers/0')
# USGS 2025 post-wildfire lidar, bare-earth 0.5 m rasters, 750 m tiles, EPSG:6340 / NAVD88
USGS_DEM = ('https://prd-tnm.s3.amazonaws.com/CA_FireImpactZone_2025_PRELIMINARY/'
            'Palisades/bare_earth/be_rasters')
USGS_TILE_M = 750
# Mapzen terrain tiles (AWS Open Data), the regional context under and around the lidar
MAPZEN = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium'
PROJ_CDN = 'https://cdn.proj.org'
GRIDS = ('us_nga_egm96_15.tif', 'us_noaa_g2018u0.tif')

USER_AGENT = 'OpenPali-scene-build/2'
RETRIES = 5


class Missing(Exception):
    """The source answered that this resource does not exist."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_path(url: str, suffix: str = '.bin') -> Path:
    return RAW / (digest(url.encode()) + suffix)


def fetch(url: str, records: dict | None = None, *, offline: bool = False,
          suffix: str = '.bin', timeout: int = 60) -> bytes:
    """Cached GET. A 404 is cached too (as an empty marker) and raises Missing."""
    path = cache_path(url, suffix)
    absent = path.with_suffix('.absent')
    if absent.exists():
        raise Missing(url)
    if path.exists():
        raw = path.read_bytes()
    else:
        if offline:
            raise FileNotFoundError(f'not in the raw cache (offline build): {url}')
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        context = ssl.create_default_context(cafile=certifi.where())
        for attempt in range(RETRIES):
            try:
                with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as error:
                if error.code in (403, 404):  # S3 answers 403 for a missing key without list rights
                    RAW.mkdir(parents=True, exist_ok=True)
                    absent.write_bytes(b'')
                    raise Missing(url) from error
                if error.code < 500 or attempt == RETRIES - 1:
                    raise
            except (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException):
                # resets and truncated bodies are routine on long public downloads
                if attempt == RETRIES - 1:
                    raise
            time.sleep(2 ** attempt)
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        # ArcGIS may answer an error body with HTTP 200; never cache it as data.
        # A binary I3S string attribute can also start with '{', so parse to tell.
        if raw.lstrip().startswith(b'{'):
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                payload = None
            if isinstance(payload, dict) and 'error' in payload:
                raise ValueError(f'{url}: {payload["error"]}')
        RAW.mkdir(parents=True, exist_ok=True)
        # write-then-rename: an interrupted build never leaves a short file in the cache
        partial = path.with_suffix(path.suffix + f'.{threading.get_ident()}.part')
        partial.write_bytes(raw)
        partial.replace(path)
    if records is not None:
        records[url] = {'sha256': digest(raw), 'bytes': len(raw)}
    return raw


def strings(raw: bytes) -> list[str]:
    """Decode an I3S string attribute buffer."""
    count, size = struct.unpack_from('<II', raw)
    lengths = np.frombuffer(raw, '<u4', count=count, offset=8)
    if len(raw) != 8 + count * 4 + size or int(lengths.sum()) != size:
        raise ValueError('Invalid I3S string buffer length')
    blob, offset, result = raw[8 + count * 4:], 0, []
    for length in lengths:
        result.append(blob[offset:offset + int(length)].rstrip(b'\0').decode('utf-8'))
        offset += int(length)
    return result


def grid_paths(records: dict | None = None, *, offline: bool = False) -> list[Path]:
    """The two geoid grids, fetched into the raw cache under their own names."""
    paths = []
    for name in GRIDS:
        url = f'{PROJ_CDN}/{name}'
        fetch(url, records, offline=offline, suffix='.tif', timeout=300)
        paths.append(cache_path(url, '.tif'))
    return paths


def egm96_to_navd88(grids: list[Path]):
    """EGM96 orthometric height → NAVD88 (GEOID18), by explicit grids.

    Explicit grids prevent a silent vertical pass-through; ``+multiplier=1``
    matches the inverse-height operations PROJ's EPSG database selects for
    these grids (``vgridshift`` defaults to −1).
    """
    def vertical(path: Path) -> pyproj.Transformer:
        return pyproj.Transformer.from_pipeline(
            '+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad '
            f'+step +proj=vgridshift +grids={path} +multiplier=1 '
            '+step +proj=unitconvert +xy_in=rad +xy_out=deg')
    egm, geoid18 = (vertical(p) for p in grids)

    def convert(lon: np.ndarray, lat: np.ndarray, h: np.ndarray) -> np.ndarray:
        _, _, ellipsoidal = egm.transform(lon, lat, h, errcheck=True)
        _, _, undulation = geoid18.transform(lon, lat, np.zeros(len(lon)), errcheck=True)
        return np.asarray(ellipsoidal) - np.asarray(undulation)
    return convert


def usgs_tile_name(column: int, row: int) -> str:
    """750 m tile whose south-west corner is (column, row) × 750 m in UTM 11N."""
    east, north = column * USGS_TILE_M, row * USGS_TILE_M
    return f'Prelim_11SLT{east // 100:06d}{north // 100:06d}'


def mercator(lon, lat):
    """lon/lat degrees → MapLibre mercator units (0..1, y south)."""
    return (np.asarray(lon) + 180) / 360, (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2
