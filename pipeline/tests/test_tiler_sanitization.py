"""LOD-merge sanitization invariants (the giant-opaque-LOD-sheet fix).

Recovered artifact-elimination spec, tiler half: Ledoit-Wolf conditioning,
voxel eigenvalue cap, energy-conserving parent opacity, and the finite-
thickness floor on flat surfels.
"""

from __future__ import annotations

import numpy as np

from core.spatial.splat_tiler import (
    SURFEL_THICKNESS_FLOOR_M,
    _ALPHA_MAX,
    merge_cluster,
    splat_covariances,
)


def _flat_surfels(n: int, spread: float, rng: np.random.Generator):
    """n roof-style flat disks scattered over a square of size `spread`."""
    pos = np.zeros((n, 3))
    pos[:, :2] = rng.uniform(0, spread, size=(n, 2))
    scale = np.tile([0.56, 0.56, 0.001], (n, 1))
    rot = np.tile([1.0, 0.0, 0.0, 0.0], (n, 1))  # identity: normal = +z
    cov = splat_covariances(scale, rot)
    alpha = np.full(n, 0.92)
    sh_dc = np.zeros((n, 3))
    t = np.zeros(n)
    area = np.sort(scale, axis=1)[:, 1:].prod(axis=1)
    return pos, cov, alpha, sh_dc, t, area


def test_sparse_cluster_gets_faint_not_opaque():
    rng = np.random.default_rng(7)
    # 8 surfels scattered over a 500 m voxel: almost all empty space
    pos, cov, alpha, sh_dc, t, area = _flat_surfels(8, 500.0, rng)
    _, scale, _, a, _, _ = merge_cluster(pos, cov, alpha, sh_dc, t, area,
                                         cap_radius=250.0)
    # member energy: 8 * 0.92 * 0.31 m^2 ≈ 2.3 m^2 over a >> 100 m^2 footprint
    assert a < 0.05, f"sparse cluster must be faint, got alpha={a}"
    # the old behaviour was the members' mean (≈0.92) — never again
    assert a < alpha.mean() / 10


def test_dense_cluster_saturates_to_opaque():
    rng = np.random.default_rng(8)
    # 4000 surfels tiling a 30 m roof: integrated area >> representative area
    pos, cov, alpha, sh_dc, t, area = _flat_surfels(4000, 30.0, rng)
    _, _, _, a, _, _ = merge_cluster(pos, cov, alpha, sh_dc, t, area,
                                     cap_radius=250.0)
    assert a == _ALPHA_MAX  # clamped: a building mass IS opaque from afar


def test_eigen_cap_binds_and_alpha_follows():
    rng = np.random.default_rng(9)
    pos, cov, alpha, sh_dc, t, area = _flat_surfels(64, 400.0, rng)
    _, scale_uncapped, _, _, _, _ = merge_cluster(pos, cov, alpha, sh_dc, t,
                                                  area, cap_radius=1e9)
    _, scale_capped, _, a_capped, _, _ = merge_cluster(pos, cov, alpha, sh_dc,
                                                       t, area, cap_radius=50.0)
    assert scale_uncapped.max() > 50.0  # the spread term really did inflate
    assert scale_capped.max() <= 50.0 + 1e-9
    assert 0.0 < a_capped <= _ALPHA_MAX

def test_coplanar_cluster_is_conditioned_not_degenerate():
    # all members in one plane: without Ledoit-Wolf the smallest eigenvalue of
    # the spread term collapses and quaternion extraction destabilises
    rng = np.random.default_rng(10)
    pos, cov, alpha, sh_dc, t, area = _flat_surfels(32, 100.0, rng)
    pos[:, 2] = 0.0
    _, scale, quat, _, _, _ = merge_cluster(pos, cov, alpha, sh_dc, t, area,
                                            cap_radius=100.0)
    assert np.all(np.isfinite(scale)) and np.all(np.isfinite(quat))
    assert abs(np.linalg.norm(quat) - 1.0) < 1e-6
    # LW shrink keeps the flat axis a real (non-collapsed) fraction of trace
    assert scale.min() > 1.0  # ~sqrt(0.1/3) of a ~100 m planar spread


def test_thickness_floor_constant_is_sane():
    # the floor must stay an order of magnitude under the in-plane sigma so
    # face-on surfels do not visibly fatten
    assert 0.02 <= SURFEL_THICKNESS_FLOOR_M <= 0.2
    assert SURFEL_THICKNESS_FLOOR_M < 0.56 / 3
