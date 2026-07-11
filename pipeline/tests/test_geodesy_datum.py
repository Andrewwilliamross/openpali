"""Datum-foundation guardrails for post-fire DEM adoption.

Three things must hold so a NAVD88/GEOID18 raster can never silently enter the
canonically-ellipsoidal ECEF pipeline:
  1. wgs84_to_ecef rejects any non-ellipsoidal height frame at the boundary.
  2. navd88_geoid18_to_wgs84 actually applies the GEOID18 grid (LA undulation
     ≈ −36 m) and is distinct from the EGM96 scalar — or fails loudly.
  3. the pinned post-fire baseline provenance is the Palisades product, not its
     easily-confused Eaton / differencing neighbours.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.spatial import geodesy
from core.spatial.baselines import BASELINES, PALISADES_POSTFIRE_DEM
from core.spatial.geodesy import HeightFrame

PALISADES_LON, PALISADES_LAT = -118.5265, 34.0440
# Palisades sample point in NAD83(2011)/UTM 11N metres (EPSG:6340)
PALISADES_E, PALISADES_N = 359097.49, 3768085.57


# ---------------------------------------------------------------------------
# 1. boundary guard on wgs84_to_ecef
# ---------------------------------------------------------------------------


def test_wgs84_to_ecef_defaults_to_ellipsoidal_and_is_unchanged():
    lon = np.array([PALISADES_LON]); lat = np.array([PALISADES_LAT]); h = np.array([55.0])
    explicit = geodesy.wgs84_to_ecef(lon, lat, h, height_frame=HeightFrame.ELLIPSOIDAL_WGS84)
    default = geodesy.wgs84_to_ecef(lon, lat, h)
    np.testing.assert_array_equal(explicit, default)
    assert 6.35e6 < np.linalg.norm(default[0]) < 6.40e6


@pytest.mark.parametrize("frame", [
    HeightFrame.ORTHOMETRIC_EGM96,
    HeightFrame.ORTHOMETRIC_NAVD88_GEOID18,
])
def test_wgs84_to_ecef_rejects_orthometric_heights(frame):
    lon = np.array([PALISADES_LON]); lat = np.array([PALISADES_LAT]); h = np.array([55.0])
    with pytest.raises(ValueError, match="ellipsoidal"):
        geodesy.wgs84_to_ecef(lon, lat, h, height_frame=frame)


# ---------------------------------------------------------------------------
# 2. NAVD88/GEOID18 -> WGS84 ellipsoidal (grid-based)
# ---------------------------------------------------------------------------


def test_navd88_geoid18_to_wgs84_applies_geoid18_grid():
    try:
        lon, lat, h = geodesy.navd88_geoid18_to_wgs84(
            np.array([PALISADES_E]), np.array([PALISADES_N]), np.array([50.0]))
    except RuntimeError as e:  # grid unavailable offline (CI without egress)
        pytest.skip(f"GEOID18 grid unavailable: {e}")

    # lands in the Palisades
    assert -118.65 < float(lon[0]) < -118.40
    assert 33.95 < float(lat[0]) < 34.15
    # GEOID18 undulation in the LA basin is ≈ −36 m
    undulation = float(h[0]) - 50.0
    assert -40.0 < undulation < -30.0, f"undulation {undulation:.2f} m not LA-plausible"
    # and it must NOT equal the EGM96 scalar (−35.6 m, scene_client.GEOID_OFFSET_LA_M)
    # — proves a real grid lift, not the constant the LARIAC path uses
    assert abs(undulation - (-35.6)) > 0.05, "undulation suspiciously equals the EGM96 constant"


def test_navd88_geoid18_round_trips_back_to_utm_navd88():
    try:
        lon, lat, h = geodesy.navd88_geoid18_to_wgs84(
            np.array([PALISADES_E]), np.array([PALISADES_N]), np.array([50.0]))
    except RuntimeError as e:
        pytest.skip(f"GEOID18 grid unavailable: {e}")
    from pyproj import Transformer
    back = Transformer.from_crs("EPSG:4979", "EPSG:6340+5703", always_xy=True,
                                allow_ballpark=False)
    e2, n2, h2 = back.transform(float(lon[0]), float(lat[0]), float(h[0]))
    assert abs(e2 - PALISADES_E) < 0.01
    assert abs(n2 - PALISADES_N) < 0.01
    assert abs(h2 - 50.0) < 0.01


# ---------------------------------------------------------------------------
# 3. baseline provenance pin
# ---------------------------------------------------------------------------


def test_palisades_postfire_dem_provenance_is_pinned_and_correct():
    b = PALISADES_POSTFIRE_DEM
    assert b.opentopo_id == "OTSDEM.012025.6340.2"
    # Palisades, NOT Eaton (G9JH3JD6) and NOT the differencing product (G95B00PW)
    assert b.doi == "10.5069/G9DR2SPG"
    assert b.doi not in ("10.5069/G9JH3JD6", "10.5069/G95B00PW")
    # datum facts that the ingestion path depends on
    assert b.horizontal_epsg == 6340  # NAD83(2011)/UTM 11N
    assert b.vertical_epsg == 5703  # NAVD88 / GEOID18 — NOT ellipsoidal, NOT EGM96
    assert b.resolution_m == 0.5
    assert b.acquired == "2025-01-21"  # pre-debris-removal vintage
    assert b.preliminary is True
    assert b.license == "CC0-1.0"
    assert b.doi_url == "https://doi.org/10.5069/G9DR2SPG"
    assert BASELINES[b.key] is b
