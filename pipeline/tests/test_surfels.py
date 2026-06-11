"""Stratified barycentric face densification — anti-stub guardrails."""

from __future__ import annotations

import numpy as np

from core.spatial.splat_tiler import quats_to_matrices
from core.spatial.surfels import (
    FLAT_SZ_M,
    sample_faces_stratified,
    stratified_barycentric,
)

RNG = np.random.default_rng(7)
EYE3 = np.eye(3)  # identity ECEF→ENU rotation: keeps test geometry literal


def test_barycentric_mapping_is_valid_and_area_uniform():
    bary = stratified_barycentric(4096, RNG)
    # valid barycentric coordinates
    assert bary.shape == (4096, 3)
    assert np.all(bary >= -1e-12) and np.all(bary <= 1 + 1e-12)
    np.testing.assert_allclose(bary.sum(axis=1), 1.0, atol=1e-12)
    # area-uniformity: map onto a right triangle and check quadrant occupancy.
    # The square-root warp is uniform in area, so the corner sub-triangle at
    # the right-angle vertex (1/4 of the area) must get ~1/4 of the samples.
    tri = np.array([[0, 0], [1, 0], [0, 1]], dtype=float)
    pts = bary @ tri
    frac_near_origin = np.mean((pts[:, 0] < 0.5) & (pts[:, 1] < 0.5) & (pts.sum(axis=1) < 0.5))
    assert abs(frac_near_origin - 0.25) < 0.03, f"not area-uniform: {frac_near_origin:.3f}"
    # naive (un-warped) sampling would put ~50% of mass there — guard the warp
    assert frac_near_origin < 0.35


def test_stratification_no_clumping():
    # stratified samples on a square face: occupancy of a coarse grid must be
    # near-complete (white noise leaves ~37% of cells empty at n == cells)
    tri = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]])
    bary = stratified_barycentric(400, np.random.default_rng(3))
    pts = bary @ tri
    gx = np.clip((pts[:, 0] / 10 * 10).astype(int), 0, 9)
    gy = np.clip((pts[:, 1] / 10 * 10).astype(int), 0, 9)
    occupied = len(set(zip(gx.tolist(), gy.tolist())))
    # 100 cells, only the lower triangle (~55 cells) is reachable; demand most hit
    assert occupied > 40, f"clumped: only {occupied} cells occupied"


def _square_roof(z: float = 10.0, size: float = 20.0):
    """Two triangles forming a size×size horizontal quad at height z."""
    a, b, c, d = ([0, 0, z], [size, 0, z], [size, size, z], [0, size, z])
    tris = np.array([[a, b, c], [a, c, d]], dtype=float)
    cols = np.full((2, 3, 4), 200, dtype=np.uint8)
    return tris, cols


def test_face_sampling_density_flatness_and_normals():
    tris, cols = _square_roof()
    batch = sample_faces_stratified(tris, cols, EYE3, t_epoch=1.78e9,
                                    apn="4412019009", source="test",
                                    spacing_m=0.75)
    # density: 400 m² at 1/0.5625 per m² ≈ 711 samples
    assert 500 < len(batch) < 900, len(batch)
    # all samples on the quad, at the right height
    np.testing.assert_allclose(batch.xyz_ecef[:, 2], 10.0, atol=1e-9)
    assert batch.xyz_ecef[:, 0].min() >= -1e-9 and batch.xyz_ecef[:, 0].max() <= 20 + 1e-9
    # structural flatness: s_z locked to FLAT_SZ_M, s_x = s_y
    np.testing.assert_allclose(batch.scale[:, 2], FLAT_SZ_M, atol=1e-7)
    np.testing.assert_allclose(batch.scale[:, 0], batch.scale[:, 1])
    assert batch.scale[0, 0] > 0.3  # a real disk, not a point
    # orientation: R·ẑ must equal the face normal (+z for a horizontal roof)
    mats = quats_to_matrices(batch.rot[:50].astype(np.float64))
    disk_normals = mats[:, :, 2]  # third column = rotated z-axis
    np.testing.assert_allclose(disk_normals, np.tile([0, 0, 1.0], (50, 1)), atol=1e-5)


def test_wall_normals_align_horizontally():
    # vertical wall in the x-z plane: normal must be ±y, horizontal
    a, b, c = [0, 0, 0], [10, 0, 0], [10, 0, 8]
    tris = np.array([[a, b, c]], dtype=float)
    cols = np.full((1, 3, 4), 128, dtype=np.uint8)
    batch = sample_faces_stratified(tris, cols, EYE3, t_epoch=0, apn="x",
                                    source="test")
    mats = quats_to_matrices(batch.rot[:20].astype(np.float64))
    nz = mats[:, 2, 2]  # z-component of the disk normal
    np.testing.assert_allclose(nz, 0.0, atol=1e-6)  # perfectly horizontal


def test_per_parcel_cap_scales_counts_and_radius():
    # a huge face (200×200 m = 40,000 m²) would want ~71k samples at 0.75 m
    a, b, c, d = [0, 0, 0], [200, 0, 0], [200, 200, 0], [0, 200, 0]
    tris = np.array([[a, b, c], [a, c, d]], dtype=float)
    cols = np.full((2, 3, 4), 90, dtype=np.uint8)
    batch = sample_faces_stratified(tris, cols, EYE3, t_epoch=0, apn="big",
                                    source="test", max_surfels=5000)
    assert len(batch) <= 5002  # cap honoured (±rounding)
    # radius grows to keep the sparser sampling covering the surface
    assert batch.scale[0, 0] > 1.5


def test_degenerate_faces_dropped():
    a, b = [0, 0, 0], [5, 0, 0]
    tris = np.array([[a, b, a]], dtype=float)  # zero-area sliver
    cols = np.full((1, 3, 4), 50, dtype=np.uint8)
    assert sample_faces_stratified(tris, cols, EYE3, t_epoch=0, apn="d",
                                   source="test") is None


def test_deterministic_per_apn():
    tris, cols = _square_roof()
    b1 = sample_faces_stratified(tris, cols, EYE3, t_epoch=0, apn="4400000001", source="t")
    b2 = sample_faces_stratified(tris, cols, EYE3, t_epoch=0, apn="4400000001", source="t")
    np.testing.assert_array_equal(b1.xyz_ecef, b2.xyz_ecef)


def test_quaternion_antiparallel_singularity():
    # §III.1 audit: n = −ẑ is the half-vector singularity (w = 1+n_z → 0).
    # The deterministic fallback must be an exact 180° flip, no NaN/zero-div.
    from core.spatial.surfels import quats_from_normals

    q = quats_from_normals(np.array([[0.0, 0.0, -1.0]]))
    np.testing.assert_allclose(q[0], [0.0, 1.0, 0.0, 0.0], atol=1e-7)
    mats = quats_to_matrices(q.astype(np.float64))
    np.testing.assert_allclose(mats[0] @ [0, 0, 1], [0, 0, -1], atol=1e-7)


def test_quaternion_near_antiparallel_stability():
    # overhangs: normals within micro-radians of −ẑ must stay finite and unit,
    # and still rotate ẑ onto n to high accuracy
    from core.spatial.surfels import quats_from_normals

    eps = np.array([1e-5, 1e-6, 1e-7, 1e-8])
    n = np.stack([eps, np.zeros_like(eps), -np.sqrt(1 - eps**2)], axis=1)
    q = quats_from_normals(n)
    assert np.isfinite(q).all()
    np.testing.assert_allclose(np.linalg.norm(q, axis=1), 1.0, atol=1e-6)
    mats = quats_to_matrices(q.astype(np.float64))
    for i in range(len(n)):
        err = np.linalg.norm(mats[i] @ [0, 0, 1] - n[i])
        assert err < 1e-4, f"eps={eps[i]}: rotation error {err}"


def test_downward_faces_sample_finite_into_store_guard():
    # an overhang (ceiling) face: downward normal — full path must produce a
    # storable batch (the schema constructor now hard-rejects non-finite data)
    a, b, c = [0, 0, 5], [10, 0, 5], [0, 10, 5]
    tris = np.array([[c, b, a]], dtype=float)  # reversed winding → n = −ẑ
    cols = np.full((1, 3, 4), 120, dtype=np.uint8)
    batch = sample_faces_stratified(tris, cols, EYE3, t_epoch=0, apn="ovh", source="t")
    assert batch is not None and len(batch) > 50
    assert np.isfinite(batch.rot).all() and np.isfinite(batch.xyz_ecef).all()
    mats = quats_to_matrices(batch.rot[:8].astype(np.float64))
    np.testing.assert_allclose(mats[:, 2, 2], -1.0, atol=1e-5)  # disks face down


def test_color_interpolation_barycentric():
    # gradient triangle: corner colours 0 / 255 — interior samples must span between
    a, b, c = [0, 0, 0], [10, 0, 0], [0, 10, 0]
    tris = np.array([[a, b, c]], dtype=float)
    cols = np.zeros((1, 3, 4), dtype=np.uint8)
    cols[0, 1, :3] = 255  # corner b bright, others black
    batch = sample_faces_stratified(tris, cols, EYE3, t_epoch=0, apn="g", source="t")
    rgb = np.clip(0.5 + batch.sh[:, 0, :] * 0.2820948, 0, 1)
    # brightness must increase with x (towards corner b)
    x = batch.xyz_ecef[:, 0]
    hi = rgb[x > 7, 0].mean()
    lo = rgb[x < 2, 0].mean()
    assert hi > lo + 0.3, (hi, lo)
