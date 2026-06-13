"""Placeholder prism geometry + coverage contract (ROADMAP D2 / PR2)."""

from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon

from core.spatial.geodesy import wgs84_to_ecef
from core.spatial.prisms import (
    GroundZSampler,
    PARCEL_PRISM_HEIGHT_M,
    parcel_prism_batch,
    polygon_prism_tris,
)
from core.spatial.web_export import build_coverage

LON0, LAT0 = -118.5265, 34.0438


def _square(d_deg: float = 0.0002) -> Polygon:
    return Polygon([
        (LON0, LAT0), (LON0 + d_deg, LAT0),
        (LON0 + d_deg, LAT0 + d_deg), (LON0, LAT0 + d_deg),
    ])


def test_prism_tris_walls_and_roof():
    tris = polygon_prism_tris(_square(), base_z=60.0, height=4.5)
    # 4 edges × 2 wall tris + ≥2 roof tris
    assert len(tris) >= 10
    zs = tris[:, :, 2]
    assert zs.min() == 60.0 and zs.max() == 64.5
    # roof triangles live entirely at the top plane
    roof = tris[np.all(zs == 64.5, axis=1)]
    assert len(roof) >= 2


def test_prism_roof_respects_concavity():
    # L-shaped parcel: naive Delaunay would bridge the notch
    L = Polygon([(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)])
    tris = polygon_prism_tris(L, base_z=0.0, height=1.0)
    roof = tris[np.all(tris[:, :, 2] == 1.0, axis=1)]
    cx = roof[:, :, 0].mean(axis=1)
    cy = roof[:, :, 1].mean(axis=1)
    # no roof triangle centroid inside the notch (x>1, y>1)
    assert not np.any((cx > 1.0) & (cy > 1.0))
    # roof area ≈ the L's 3 unit squares
    a = roof[:, 1] - roof[:, 0]
    b = roof[:, 2] - roof[:, 0]
    area = 0.5 * np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum()
    assert abs(area - 3.0) < 1e-6


def test_parcel_prism_batch_is_deterministic_and_capped():
    geom = _square().__geo_interface__
    b1 = parcel_prism_batch("4400000001", geom, 60.0, t_epoch=1.0)
    b2 = parcel_prism_batch("4400000001", geom, 60.0, t_epoch=1.0)
    assert b1 is not None and b2 is not None
    assert b1.kind == "splats" and b1.source == "parcel_prism"
    assert 10 <= len(b1) <= 1600
    np.testing.assert_array_equal(b1.xyz_ecef, b2.xyz_ecef)  # APN-seeded RNG
    assert np.all(b1.apn == "4400000001")


def test_ground_sampler_recovers_plane_height():
    rng = np.random.default_rng(3)
    n = 4000
    lon = LON0 + rng.uniform(-0.002, 0.002, n)
    lat = LAT0 + rng.uniform(-0.002, 0.002, n)
    # ground plane at h=60 with 30% rooftop outliers at h=66
    h = np.full(n, 60.0)
    h[: int(n * 0.3)] = 66.0
    xyz = wgs84_to_ecef(lon, lat, h)
    s = GroundZSampler(xyz, subsample=1)
    gz = s.ground_z(LON0, LAT0)
    assert gz is not None
    assert abs(gz - 60.0) < 0.75  # p15 rejects the roofs
    # far outside the cloud → honest None
    assert s.ground_z(LON0 + 1.0, LAT0) is None


def test_build_coverage_classes_and_missing():
    assets = [
        {"apn": "1", "kind": "lariac_prior", "source": "lariac_scene",
         "status": "live", "t_epoch": 1.7e9},
        {"apn": "2", "kind": "lariac_prior", "source": "lariac_footprint_extrusion",
         "status": "live", "t_epoch": 1.7e9},
        {"apn": "2", "kind": "renderable_splats", "source": "lariac_footprint_extrusion",
         "status": "live", "t_epoch": 1.7e9},
        {"apn": "3", "kind": "renderable_splats", "source": "parcel_prism",
         "status": "live", "t_epoch": 1.7e9},
    ]
    picking = {"1": {"n": 2000}, "2": {"n": 900}, "3": {"n": 500}}
    cov = build_coverage(["1", "2", "3", "4"], assets, picking)
    p = cov["parcels"]
    assert p["1"]["geometry_source"] == "lariac_model"
    assert p["2"]["geometry_source"] == "footprint_extrusion"
    assert p["3"]["geometry_source"] == "parcel_prism"
    assert p["4"]["geometry_source"] is None
    assert p["4"]["missing_reason"] == "no_renderable_geometry"
    assert p["1"]["acquired"] is not None
    assert cov["counts"] == {"lariac_model": 1, "footprint_extrusion": 1,
                             "parcel_prism": 1, "missing": 1}
    assert PARCEL_PRISM_HEIGHT_M > 2.5  # massing default stays human-scale
