"""Unit tests for the spatial pipeline's pure logic (SPATIAL-001)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from openpali.spatial.aoi import load_aoi
from openpali.spatial.derive import (
    _terrarium_encode,
    _tile_bounds_merc,
    _tiles_for_bbox,
    build_surfel_batch,
    Mosaic,
)
from openpali.spatial.registry import version_id_from_hashes
from openpali.spatial.usgs import UsgsDemAdapter, _parse_tfw, _parse_vendor_dates
from openpali.adapters.base import AcquisitionRequest, OfflineInputError, SchemaDriftError


# ---------------------------------------------------------------------------
# frozen AOI
# ---------------------------------------------------------------------------


def test_frozen_aoi_contract():
    aoi = load_aoi()
    assert len(aoi.tiles) == 4, "four independently requested LOD tiles"
    assert aoi.destroyed_parcels_inside >= 25
    assert aoi.horizontal_crs.startswith("EPSG:6340")
    assert "NAVD88" in aoi.vertical_datum
    min_e, min_n, max_e, max_n = aoi.utm_bounds
    assert (max_e - min_e) == pytest.approx(1500.0)
    assert (max_n - min_n) == pytest.approx(1500.0)
    assert aoi.extent_wkt.startswith("POLYGON((")


def test_tile_grid_is_contiguous():
    aoi = load_aoi()
    corners = {t.utm_bounds for t in aoi.tiles}
    assert len(corners) == 4
    widths = {t.utm_bounds[2] - t.utm_bounds[0] for t in aoi.tiles}
    assert widths == {750.0}


# ---------------------------------------------------------------------------
# tfw / vendor XML parsing
# ---------------------------------------------------------------------------


def test_parse_tfw_roundtrip():
    body = b"0.5\n0\n0\n-0.5\n358500.25\n3768749.75\n"
    tfw = _parse_tfw(body)
    assert tfw["pixel_size_x"] == 0.5
    assert tfw["pixel_size_y"] == -0.5
    assert tfw["upper_left_center_x"] == 358500.25


def test_parse_tfw_rejects_garbage():
    with pytest.raises(SchemaDriftError):
        _parse_tfw(b"1 2 3")


def test_parse_vendor_dates():
    xml = b"<metadata><begdate>20250121</begdate><enddate>20250123</enddate></metadata>"
    dates = _parse_vendor_dates(xml)
    assert dates["begdate"] == "2025-01-21"
    assert dates["enddate"] == "2025-01-23"


def test_offline_requires_hashes():
    adapter = UsgsDemAdapter()
    with pytest.raises(OfflineInputError):
        adapter.acquire(AcquisitionRequest(online=False))


# ---------------------------------------------------------------------------
# terrain math
# ---------------------------------------------------------------------------


def test_terrarium_encoding_roundtrip():
    elev = np.array([[0.0, 87.25], [-12.5, 1523.0]], dtype=np.float32)
    rgb = _terrarium_encode(elev)
    decoded = rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0
    assert np.allclose(decoded, elev, atol=1 / 256)


def test_tile_bounds_cover_aoi():
    aoi = load_aoi()
    lons = [p[0] for p in aoi.wgs84_polygon]
    lats = [p[1] for p in aoi.wgs84_polygon]
    tiles = list(_tiles_for_bbox(15, min(lons), min(lats), max(lons), max(lats)))
    assert tiles, "AOI must intersect at least one z15 tile"
    # every tile's mercator bounds must overlap the AOI's mercator bbox
    from openpali.spatial.derive import _merc

    x0, y1 = _merc(min(lons), min(lats))
    x1, y0 = _merc(max(lons), max(lats))
    for tx, ty in tiles:
        minx, miny, maxx, maxy = _tile_bounds_merc(15, tx, ty)
        assert maxx > x0 and minx < x1
        assert maxy > y1 and miny < y0


# ---------------------------------------------------------------------------
# surfel derivation (synthetic mosaic; no DB, no network)
# ---------------------------------------------------------------------------


def _synthetic_mosaic(slope: float = 0.0) -> Mosaic:
    aoi = load_aoi()
    h, w = 60, 60
    min_e, min_n, max_e, max_n = aoi.utm_bounds
    cols = np.arange(w, dtype=np.float64)
    height = np.tile(50.0 + slope * cols * 0.5, (h, 1)).astype(np.float32)
    return Mosaic(
        height_m=height,
        # shrink bounds to the synthetic grid size (60 px * 0.5 m)
        utm_bounds=(min_e, max_n - h * 0.5, min_e + w * 0.5, max_n),
        raw_assets=[],
        seam_quality={"median_seam_step_m": 0.0},
        nodata_fraction=0.0,
    )


def test_surfel_batch_flat_terrain_normals_up():
    mosaic = _synthetic_mosaic(slope=0.0)
    grid = np.full(mosaic.shape, -1, dtype=np.int32)
    batch = build_surfel_batch(mosaic, grid, [], stride=4)
    assert len(batch) == 15 * 15
    # identity-ish quaternion: local +Z stays up for flat terrain
    assert np.allclose(batch.rot[:, 0], 1.0, atol=1e-5)
    # ECEF radius near Earth's surface
    radii = np.linalg.norm(batch.xyz_ecef, axis=1)
    assert np.all((radii > 6.35e6) & (radii < 6.4e6))
    # flight date, never processing time
    assert np.all(batch.t_epoch == batch.t_epoch[0])
    assert abs(batch.t_epoch[0] - 1737417600.0) < 86400 * 2  # 2025-01-21 UTC


def test_surfel_batch_slope_tilts_normals():
    mosaic = _synthetic_mosaic(slope=1.0)  # 45 degrees along +E
    grid = np.full(mosaic.shape, -1, dtype=np.int32)
    batch = build_surfel_batch(mosaic, grid, [], stride=4)
    # rotation angle = 2*acos(qw) must be ~45 degrees away from vertical
    interior = batch.rot[len(batch) // 2]
    angle = 2 * math.degrees(math.acos(float(interior[0])))
    assert 35.0 < angle < 55.0


def test_surfel_batch_carries_parcel_apns():
    mosaic = _synthetic_mosaic()
    grid = np.full(mosaic.shape, -1, dtype=np.int32)
    grid[0:30, 0:30] = 0
    batch = build_surfel_batch(mosaic, grid, ["4416001001"], stride=4)
    apns = set(batch.apn.tolist())
    assert "4416001001" in apns
    assert "" in apns  # off-parcel ground carries no APN


def test_version_id_deterministic():
    a = version_id_from_hashes("aa", "bb", "cc")
    b = version_id_from_hashes("aa", "bb", "cc")
    c = version_id_from_hashes("aa", "bb", "cd")
    assert a == b != c
    assert a.startswith("sv-")
