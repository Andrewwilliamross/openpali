"""Spatial core tests: geodesy exactness, schema round-trips, registration
ground-truth recovery, octree LOD invariants. These are the anti-stub
guardrails — every mathematical stage is exercised against known answers."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from core.spatial import geodesy
from core.spatial.registration import (
    apply_rigid,
    icp_refine,
    kabsch,
    mahalanobis_filter,
    ransac_coarse_align,
    register_capture,
    statistical_outlier_removal,
)
from core.spatial.schema import GaussianBatch, SpatialStore
from core.spatial.splat_tiler import (
    matrix_to_quat,
    quats_to_matrices,
    tile_batch,
)

RNG = np.random.default_rng(42)
PALISADES_LON, PALISADES_LAT = -118.5265, 34.0440


# ---------------------------------------------------------------------------
# geodesy
# ---------------------------------------------------------------------------


def test_ecef_round_trip_submillimetre():
    lon = np.array([PALISADES_LON, -118.55, 0.0, 139.69])
    lat = np.array([PALISADES_LAT, 34.07, 51.48, 35.68])
    h = np.array([55.0, 320.0, -10.0, 1500.0])
    xyz = geodesy.wgs84_to_ecef(lon, lat, h)
    # ECEF magnitude must be earth-like
    assert np.all(np.linalg.norm(xyz, axis=1) > 6.35e6)
    assert np.all(np.linalg.norm(xyz, axis=1) < 6.40e6)
    lon2, lat2, h2 = geodesy.ecef_to_wgs84(xyz)
    np.testing.assert_allclose(lon2, lon, atol=1e-9)
    np.testing.assert_allclose(lat2, lat, atol=1e-9)
    np.testing.assert_allclose(h2, h, atol=1e-3)  # < 1 mm


def test_enu_round_trip_and_orientation():
    origin = geodesy.wgs84_to_ecef(
        np.array(PALISADES_LON), np.array(PALISADES_LAT), np.array(50.0))
    pts = geodesy.wgs84_to_ecef(
        np.array([PALISADES_LON, PALISADES_LON]),
        np.array([PALISADES_LAT, PALISADES_LAT + 0.001]),  # ~111 m north
        np.array([50.0, 50.0]))
    enu = geodesy.ecef_to_enu(pts, origin, PALISADES_LON, PALISADES_LAT)
    # second point should be ~111 m north, ~0 east
    assert abs(enu[1, 1] - 110.9) < 1.0
    assert abs(enu[1, 0]) < 0.5
    back = geodesy.enu_to_ecef(enu, origin, PALISADES_LON, PALISADES_LAT)
    np.testing.assert_allclose(back, pts, atol=1e-6)


def test_stateplane_known_point():
    # Palisades-area state-plane coords (usft) must land in the Palisades
    lon, lat, h = geodesy.stateplane_to_wgs84(
        np.array([6.40e6]), np.array([1.84e6]), np.array([300.0]))
    assert -118.65 < lon[0] < -118.40
    assert 33.95 < lat[0] < 34.15
    assert abs(h[0] - 300.0 * 1200.0 / 3937.0) < 1e-9


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


def _random_batch(n: int = 500, apn: str = "4412013017") -> GaussianBatch:
    lon = PALISADES_LON + RNG.uniform(-0.002, 0.002, n)
    lat = PALISADES_LAT + RNG.uniform(-0.002, 0.002, n)
    h = RNG.uniform(20, 80, n)
    xyz = geodesy.wgs84_to_ecef(lon, lat, h)
    q = RNG.normal(size=(n, 4)).astype(np.float32)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    return GaussianBatch(
        xyz_ecef=xyz,
        t_epoch=np.full(n, 1.78e9),
        scale=np.abs(RNG.normal(0.3, 0.1, (n, 3))).astype(np.float32),
        rot=q,
        alpha=RNG.uniform(0.2, 1.0, n).astype(np.float32),
        sh=RNG.normal(0, 0.5, (n, 1, 3)).astype(np.float32),
        apn=np.full(n, apn, dtype="<U10"),
        kind="splats",
        source="test",
    )


def test_batch_arrow_round_trip():
    b = _random_batch()
    b2 = GaussianBatch.from_arrow(b.to_arrow())
    np.testing.assert_allclose(b2.xyz_ecef, b.xyz_ecef)
    np.testing.assert_allclose(b2.scale, b.scale, rtol=1e-6)
    np.testing.assert_allclose(b2.rot, b.rot, rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(b2.alpha, b.alpha, rtol=1e-6)
    np.testing.assert_allclose(b2.sh, b.sh, rtol=1e-6)
    assert list(b2.apn) == list(b.apn)
    assert b2.kind == "splats"


def test_store_partitioned_write_read_and_idempotency(tmp_path: Path):
    store = SpatialStore(root=tmp_path)
    b = _random_batch(400, apn="4412013017")
    store.write_batch(b, epoch_label="2026-06-10")
    store.write_batch(b, epoch_label="2026-06-10")  # idempotent re-run
    got = store.read(apn="4412013017")
    assert got is not None and len(got) == 400  # no duplication
    # partition layout is hive by res-8 H3
    parts = list((tmp_path / "gaussians").glob("h3_08=*/*.parquet"))
    assert parts, "expected hive-partitioned parquet files"
    # filtered miss returns None
    assert store.read(apn="0000000000") is None


def test_two_batches_same_cell_same_night_do_not_clobber(tmp_path: Path):
    # Regression: neighbouring parcels share res-8 H3 cells; same-night writes
    # of different batches must coexist, while re-writing the SAME batch must
    # still overwrite (idempotency).
    store = SpatialStore(root=tmp_path)
    b1 = _random_batch(300, apn="4409001905")
    b2 = _random_batch(200, apn="4409002001")  # same area → same partitions
    store.write_batch(b1, epoch_label="2026-06-10")
    store.write_batch(b2, epoch_label="2026-06-10")
    store.write_batch(b2, epoch_label="2026-06-10")  # idempotent re-run
    g1 = store.read(apn="4409001905")
    g2 = store.read(apn="4409002001")
    assert g1 is not None and len(g1) == 300
    assert g2 is not None and len(g2) == 200


def test_asset_index_is_geoparquet(tmp_path: Path):
    from shapely.geometry import Point

    store = SpatialStore(root=tmp_path)
    store.index_asset(apn="4412013017", kind="lariac_prior", t_epoch=1.78e9,
                      n_points=1234, geometry_wkb=Point(PALISADES_LON, PALISADES_LAT).wkb,
                      status="live", source="test")
    # newer row for same (apn, kind) must win
    store.index_asset(apn="4412013017", kind="lariac_prior", t_epoch=1.79e9,
                      n_points=5678, geometry_wkb=Point(PALISADES_LON, PALISADES_LAT).wkb,
                      status="live", source="test")
    n = store.flush_assets()
    assert n == 1
    t = pq.read_table(store.assets_path)
    assert b"geo" in t.schema.metadata  # GeoParquet metadata present
    meta = json.loads(t.schema.metadata[b"geo"])
    assert meta["primary_column"] == "geometry"
    assert t.to_pylist()[0]["n_points"] == 5678


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def _house_cloud(n: int = 3000) -> np.ndarray:
    """Synthetic building-ish cloud: 4 walls + gabled roof + ground ring."""
    rng = np.random.default_rng(3)
    pts = []
    # walls of a 14 x 9 x 6 m box
    for axis, lo, hi in ((0, 0, 14), (1, 0, 9)):
        u = rng.uniform(0, 14 if axis == 0 else 9, n // 6)
        v = rng.uniform(0, 6, n // 6)
        for fixed in (lo, hi):
            p = np.zeros((n // 6, 3))
            p[:, axis] = u
            p[:, 1 - axis] = fixed if axis == 0 else fixed
            p[:, 1 - axis] = np.full(n // 6, fixed)
            p[:, 2] = v
            pts.append(p)
    # gabled roof
    u = rng.uniform(0, 14, n // 3)
    v = rng.uniform(0, 9, n // 3)
    roof = np.stack([u, v, 6 + 2.5 * (1 - np.abs(v - 4.5) / 4.5)], axis=1)
    pts.append(roof)
    cloud = np.concatenate(pts)
    return cloud - cloud.mean(axis=0)


def _yaw(theta_deg: float) -> np.ndarray:
    t = np.radians(theta_deg)
    return np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])


def test_kabsch_exact_recovery():
    pts = RNG.normal(size=(50, 3))
    r_true = _yaw(33.0)
    t_true = np.array([1.5, -2.0, 0.7])
    rot, trans = kabsch(pts, pts @ r_true.T + t_true)
    np.testing.assert_allclose(rot, r_true, atol=1e-10)
    np.testing.assert_allclose(trans, t_true, atol=1e-10)
    assert np.linalg.det(rot) > 0.999


def test_sor_drops_planted_outliers():
    cloud = _house_cloud(1200)
    outliers = RNG.uniform(60, 90, size=(30, 3))
    mixed = np.concatenate([cloud, outliers])
    keep = statistical_outlier_removal(mixed)
    assert keep[: len(cloud)].mean() > 0.95  # structure survives
    assert keep[len(cloud):].mean() < 0.2  # planted junk dies


def test_mahalanobis_keeps_structure():
    cloud = _house_cloud(1200)
    far = np.array([[500.0, 500.0, 200.0], [-400.0, 300.0, -100.0]])
    keep = mahalanobis_filter(np.concatenate([cloud, far]))
    assert keep[: len(cloud)].mean() > 0.98
    assert not keep[-1] and not keep[-2]


def test_full_registration_recovers_known_transform():
    prior = _house_cloud(2600)
    r_true = _yaw(17.0) @ np.array(  # 17° yaw + ~1.5° tilt
        [[1, 0, 0], [0, np.cos(0.026), -np.sin(0.026)], [0, np.sin(0.026), np.cos(0.026)]])
    t_true = np.array([5.0, -3.5, 0.8])
    rng = np.random.default_rng(11)
    capture = prior @ r_true.T + t_true + rng.normal(0, 0.05, prior.shape)
    # 8% gross outliers (telemetry junk)
    junk = rng.uniform(-40, 40, size=(len(prior) // 12, 3)) + t_true
    capture = np.concatenate([capture, junk])

    rep = register_capture(capture, prior, voxel=1.0, seed=5)
    assert rep.icp.converged
    # composed transform must invert the truth: R̂ R_true ≈ I
    rot_err = np.degrees(np.arccos(np.clip((np.trace(rep.rotation @ r_true) - 1) / 2, -1, 1)))
    trans_err = np.linalg.norm(rep.rotation @ t_true + rep.translation)
    assert rot_err < 2.0, f"rotation error {rot_err:.2f}°"
    assert trans_err < 0.35, f"translation error {trans_err:.2f} m"
    assert rep.rmse < 0.25
    assert rep.n_after_mahalanobis < rep.n_input  # filters actually fired
    assert rep.accepted


def test_icp_converges_from_good_init():
    prior = _house_cloud(1500)
    r_true = _yaw(4.0)
    t_true = np.array([0.6, -0.4, 0.15])
    capture = prior @ r_true.T + t_true
    res = icp_refine(capture, prior, max_corr_dist=3.0)
    assert res.converged
    assert res.rmse < 0.05


def test_ransac_coarse_gets_within_icp_basin():
    prior = _house_cloud(2000)
    r_true = _yaw(25.0)
    t_true = np.array([8.0, 6.0, 1.0])
    capture = prior @ r_true.T + t_true
    rot, trans, frac = ransac_coarse_align(capture, prior, voxel=1.0, seed=2)
    moved = apply_rigid(capture, rot, trans)
    # coarse alignment must land within a couple of metres RMS
    from scipy.spatial import cKDTree

    d, _ = cKDTree(prior).query(moved, k=1)
    assert np.sqrt((d ** 2).mean()) < 2.0
    assert frac > 0.5


# ---------------------------------------------------------------------------
# splat tiler
# ---------------------------------------------------------------------------


def test_quat_matrix_round_trip():
    q = RNG.normal(size=(40, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    q[q[:, 0] < 0] *= -1  # canonical hemisphere
    mats = quats_to_matrices(q)
    for i in range(len(q)):
        q2 = matrix_to_quat(mats[i])
        if q2[0] < 0:
            q2 = -q2
        np.testing.assert_allclose(q2, q[i], atol=1e-6)
        assert abs(np.linalg.det(mats[i]) - 1.0) < 1e-9


def test_tiler_lod_invariants(tmp_path: Path):
    b = _random_batch(30000)
    res = tile_batch(b, tmp_path / "tiles", leaf_max=4000, max_depth=6,
                     node_budget_grid=16)
    ts = json.loads(res.tileset_path.read_text())
    assert ts["asset"]["version"] == "1.1"
    assert res.levels > 1, "must actually build a hierarchy"

    # every referenced .splat exists, is 32-byte aligned, leaves sum to input N
    leaf_total = 0
    max_internal = 16 ** 3

    def walk(node, parent_err):
        nonlocal leaf_total
        assert node["geometricError"] <= parent_err + 1e-9, "error must shrink down-tree"
        payload = (tmp_path / "tiles" / node["content"]["uri"]).read_bytes()
        assert len(payload) % 32 == 0
        n = len(payload) // 32
        if "children" in node:
            assert n <= max_internal, "internal nodes must be downsampled"
            for c in node["children"]:
                walk(c, node["geometricError"])
        else:
            assert node["geometricError"] == 0.0
            leaf_total += n

    walk(ts["root"], ts["geometricError"])
    assert leaf_total == 30000, "leaves must preserve every raw primitive"

    # root transform is a valid rigid ENU→ECEF matrix (column-major)
    m = np.array(ts["root"]["transform"]).reshape(4, 4).T
    r = m[:3, :3]
    np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-9)
    assert 6.3e6 < np.linalg.norm(m[:3, 3]) < 6.4e6


def test_packed_splat_positions_within_root_cube(tmp_path: Path):
    b = _random_batch(5000)
    res = tile_batch(b, tmp_path / "t2", leaf_max=2000, max_depth=5)
    ts = json.loads(res.tileset_path.read_text())
    root = ts["root"]
    half = root["boundingVolume"]["box"][3]
    payload = (tmp_path / "t2" / root["content"]["uri"]).read_bytes()
    rec = np.frombuffer(payload, dtype=[("pos", "<f4", 3), ("scale", "<f4", 3),
                                        ("rgba", "u1", 4), ("rot", "u1", 4)])
    center = np.array(root["boundingVolume"]["box"][:3])
    assert np.all(np.abs(rec["pos"] - center) <= half * 1.001)
    assert rec["rgba"][:, 3].min() >= 0  # alpha sane
