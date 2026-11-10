"""Terrain the scene is registered to, and the tiles the map draws.

One elevation function serves both uses, so a structure's baked ground delta
is measured against the surface the client renders:

    USGS 2025 post-fire lidar (0.5 m, NAVD88)   where a tile was acquired
    Mapzen terrain tiles                        everywhere else

The lidar is feathered into Mapzen over ``BLEND_M`` at the outer edge of its
coverage; interior tile joins stay exact.
"""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import numpy as np
import pyproj
import rasterio
from PIL import Image

from .sources import MAPZEN, USGS_DEM, USGS_TILE_M, Missing, cache_path, fetch, usgs_tile_name

BLEND_M = 25.0
USGS_RES_M = 0.5
USGS_PIXELS = int(USGS_TILE_M / USGS_RES_M)
MAPZEN_Z = 15
#: baked zooms. Below 14 a pixel is wider than 15 m and Mapzen is used as is;
#: above 16 (2 m) the client's terrain mesh cannot show more detail.
BAKE_ZOOMS = (14, 15, 16)
#: Baked heights are rounded to this. Terrarium stores 1/256 m, but below the
#: lidar's own ~0.1 m vertical accuracy those bits are noise that PNG cannot
#: compress: rounding to an eighth of a metre halves every tile.
BAKE_STEP_M = 0.125


def tile_lonlat(z: int, x: int, y: int, size: int = 256):
    """Longitude/latitude of every pixel centre of a web-mercator tile."""
    axis = (np.arange(size) + 0.5) / size
    xx, yy = np.meshgrid(axis, axis)
    lon = (x + xx) / 2 ** z * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + yy) / 2 ** z))))
    return lon, lat


def tile_of(lon, lat, z: int):
    x = (np.asarray(lon) + 180) / 360 * 2 ** z
    y = (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * 2 ** z
    return x, y


def encode_terrarium(height: np.ndarray) -> bytes:
    packed = np.clip(np.round((height + 32768) * 256), 0, 2 ** 24 - 1).astype(np.uint32)
    rgb = np.stack([packed >> 16, packed >> 8 & 255, packed & 255], axis=-1).astype(np.uint8)
    stream = BytesIO()
    Image.fromarray(rgb).save(stream, format='PNG', optimize=True)
    return stream.getvalue()


def decode_terrarium(png: bytes) -> np.ndarray:
    rgb = np.asarray(Image.open(BytesIO(png)).convert('RGB'), dtype=np.float64)
    return rgb[:, :, 0] * 256 + rgb[:, :, 1] + rgb[:, :, 2] / 256 - 32768


def bilinear(grid: np.ndarray, row: np.ndarray, col: np.ndarray) -> np.ndarray:
    """Bilinear sample at fractional pixel-centre coordinates, clamped at edges."""
    row = np.clip(row, 0, grid.shape[0] - 1)
    col = np.clip(col, 0, grid.shape[1] - 1)
    r0 = np.floor(row).astype(np.intp)
    c0 = np.floor(col).astype(np.intp)
    r1 = np.minimum(r0 + 1, grid.shape[0] - 1)
    c1 = np.minimum(c0 + 1, grid.shape[1] - 1)
    fr, fc = row - r0, col - c0
    top = grid[r0, c0] * (1 - fc) + grid[r0, c1] * fc
    bottom = grid[r1, c0] * (1 - fc) + grid[r1, c1] * fc
    return top * (1 - fr) + bottom * fr


class Terrain:
    def __init__(self, records: dict, *, offline: bool = False, cache: int = 32):
        self.records = records
        self.offline = offline
        self.to_utm = pyproj.Transformer.from_crs(4326, 6340, always_xy=True)
        self.available: set[tuple[int, int]] = set()
        self.missing: set[tuple[int, int]] = set()
        self._rasters: OrderedDict[tuple[int, int], np.ndarray] = OrderedDict()
        self._mapzen: OrderedDict[tuple[int, int, int], np.ndarray | None] = OrderedDict()
        self._cache = cache

    # ------------------------------------------------------------- sources

    def usgs_tiles_for(self, lon, lat) -> set[tuple[int, int]]:
        east, north = self.to_utm.transform(np.asarray(lon), np.asarray(lat))
        columns = np.floor(np.asarray(east) / USGS_TILE_M).astype(int)
        rows = np.floor(np.asarray(north) / USGS_TILE_M).astype(int)
        return set(zip(columns.tolist(), rows.tolist()))

    @staticmethod
    def usgs_url(tile: tuple[int, int]) -> str:
        return f'{USGS_DEM}/{usgs_tile_name(*tile)}.tif'

    def acquire(self, tiles: set[tuple[int, int]], log=print) -> None:
        """Make each lidar tile available from the raw cache, fetching if absent."""
        def one(tile: tuple[int, int]) -> tuple[tuple[int, int], bool]:
            try:
                fetch(self.usgs_url(tile), self.records, offline=self.offline, suffix='.tif', timeout=300)
                return tile, True
            except Missing:
                return tile, False  # outside the lidar acquisition (e.g. open water)

        with ThreadPoolExecutor(max_workers=4) as pool:
            for index, (tile, found) in enumerate(pool.map(one, sorted(tiles)), 1):
                (self.available if found else self.missing).add(tile)
                if index % 10 == 0 or index == len(tiles):
                    log(f'  lidar tiles {index}/{len(tiles)}: {len(self.available)} acquired, '
                        f'{len(self.missing)} not published')

    def _raster(self, tile: tuple[int, int]) -> np.ndarray:
        if tile in self._rasters:
            self._rasters.move_to_end(tile)
            return self._rasters[tile]
        with rasterio.open(cache_path(self.usgs_url(tile), '.tif')) as dataset:
            if dataset.crs.to_epsg() != 6340 or dataset.res != (USGS_RES_M, USGS_RES_M):
                raise ValueError(f'unexpected lidar grid in {usgs_tile_name(*tile)}')
            left, bottom = dataset.bounds.left, dataset.bounds.bottom
            if (left, bottom) != (tile[0] * USGS_TILE_M, tile[1] * USGS_TILE_M):
                raise ValueError(f'{usgs_tile_name(*tile)} is not where its name says')
            data = dataset.read(1).astype(np.float32)
            nodata = dataset.nodata
        invalid = ~np.isfinite(data) | (data < -1000)
        if nodata is not None:
            invalid |= data == nodata
        data[invalid] = np.nan
        self._rasters[tile] = data
        if len(self._rasters) > self._cache:
            self._rasters.popitem(last=False)
        return data

    def mapzen(self, z: int, x: int, y: int) -> np.ndarray | None:
        key = (z, x, y)
        if key not in self._mapzen:
            try:
                png = fetch(f'{MAPZEN}/{z}/{x}/{y}.png', self.records, offline=self.offline, suffix='.png')
                self._mapzen[key] = decode_terrarium(png)
            except Missing:
                self._mapzen[key] = None
            if len(self._mapzen) > 256:
                self._mapzen.popitem(last=False)
        else:
            self._mapzen.move_to_end(key)
        return self._mapzen[key]

    # ------------------------------------------------------------ sampling

    def sample_mapzen(self, lon, lat) -> np.ndarray:
        lon, lat = np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
        fx, fy = tile_of(lon, lat, MAPZEN_Z)
        tx, ty = np.floor(fx).astype(int), np.floor(fy).astype(int)
        out = np.zeros(lon.shape)
        for x, y in set(zip(tx.ravel().tolist(), ty.ravel().tolist())):
            mask = (tx == x) & (ty == y)
            grid = self.mapzen(MAPZEN_Z, x, y)
            if grid is None:
                continue
            out[mask] = bilinear(grid, (fy[mask] - y) * 256 - 0.5, (fx[mask] - x) * 256 - 0.5)
        return out

    def sample_usgs(self, lon, lat) -> tuple[np.ndarray, np.ndarray]:
        """(height, weight): weight 0 where the lidar has nothing, 1 well inside it."""
        lon, lat = np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
        east, north = self.to_utm.transform(lon, lat)
        east, north = np.asarray(east), np.asarray(north)
        columns = np.floor(east / USGS_TILE_M).astype(int)
        rows = np.floor(north / USGS_TILE_M).astype(int)
        height = np.full(lon.shape, np.nan)
        weight = np.zeros(lon.shape)
        for tile in set(zip(columns.ravel().tolist(), rows.ravel().tolist())):
            if tile not in self.available:
                continue
            mask = (columns == tile[0]) & (rows == tile[1])
            grid = self._raster(tile)
            e, n = east[mask] - tile[0] * USGS_TILE_M, north[mask] - tile[1] * USGS_TILE_M
            value = bilinear(grid, (USGS_TILE_M - n) / USGS_RES_M - 0.5, e / USGS_RES_M - 0.5)
            # feather only toward sides with no acquired neighbour
            edge = np.full(e.shape, np.inf)
            for (dc, dr), distance in (((-1, 0), e), ((1, 0), USGS_TILE_M - e),
                                       ((0, -1), n), ((0, 1), USGS_TILE_M - n)):
                if (tile[0] + dc, tile[1] + dr) not in self.available:
                    edge = np.minimum(edge, distance)
            w = np.clip(edge / BLEND_M, 0, 1)
            w[~np.isfinite(value)] = 0
            height[mask] = value
            weight[mask] = w
        return height, weight

    def sample(self, lon, lat) -> tuple[np.ndarray, np.ndarray]:
        """(elevation, lidar weight) of the composite surface, metres NAVD88."""
        base = self.sample_mapzen(lon, lat)
        lidar, weight = self.sample_usgs(lon, lat)
        blended = np.where(weight > 0, np.nan_to_num(lidar) * weight + base * (1 - weight), base)
        return blended, weight

    # -------------------------------------------------------------- baking

    def bake(self, z: int, x: int, y: int) -> bytes | None:
        """Terrarium PNG for one tile, or None when the lidar adds nothing to it."""
        lon, lat = tile_lonlat(z, x, y)
        lidar, weight = self.sample_usgs(lon, lat)
        if not (weight > 0).any():
            return None
        native = self.mapzen(z, x, y) if z <= MAPZEN_Z else None
        base = native if native is not None else self.sample_mapzen(lon, lat)
        height = np.where(weight > 0, np.nan_to_num(lidar) * weight + base * (1 - weight), base)
        if not np.isfinite(height).all():
            raise ValueError(f'non-finite terrain in tile {z}/{x}/{y}')
        return encode_terrarium(np.round(height / BAKE_STEP_M) * BAKE_STEP_M)

    def tiles_touching(self, z: int) -> list[tuple[int, int]]:
        """Web-mercator tiles at zoom z that overlap any acquired lidar tile."""
        to_lonlat = pyproj.Transformer.from_crs(6340, 4326, always_xy=True)
        found: set[tuple[int, int]] = set()
        for column, row in self.available:
            east = [column * USGS_TILE_M, (column + 1) * USGS_TILE_M]
            north = [row * USGS_TILE_M, (row + 1) * USGS_TILE_M]
            lon, lat = to_lonlat.transform([east[0], east[1], east[0], east[1]],
                                           [north[0], north[0], north[1], north[1]])
            fx, fy = tile_of(lon, lat, z)
            for x in range(int(np.floor(fx.min())), int(np.floor(fx.max())) + 1):
                for y in range(int(np.floor(fy.min())), int(np.floor(fy.max())) + 1):
                    found.add((x, y))
        return sorted(found)
