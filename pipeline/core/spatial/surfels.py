"""Surfel construction: oriented, coloured disk-Gaussians from mesh vertices.

Convention (also noted in schema.py): splat rotation quaternions are expressed
in the **local ENU frame** (x=east, y=north, z=up at the splat's location).
ENU axes rotate by <0.1° across the entire fire footprint, so a single ENU
frame per tile/area is geometrically exact at our tolerances — and it keeps
the LOD tiler's covariance algebra and the WebGL renderer in one frame.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from .schema import GaussianBatch

_SH_DC = 0.2820948


def quats_from_normals(normals: np.ndarray) -> np.ndarray:
    """(N,3) ENU unit normals → (N,4) wxyz quaternions rotating +z onto n.

    Uses the half-vector shortcut: q = normalize([1 + n·z, cross(z, n)]),
    which is the minimal rotation from +z to n. The antipodal case (n ≈ −z)
    is degenerate there and handled explicitly as a 180° flip about x.
    """
    n = np.asarray(normals, dtype=np.float64)
    norm = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, norm, out=np.tile(np.array([0.0, 0.0, 1.0]), (len(n), 1)),
                  where=norm > 1e-8)
    w = 1.0 + n[:, 2]  # 1 + dot(z, n)
    xyz = np.stack([-n[:, 1], n[:, 0], np.zeros(len(n))], axis=1)  # cross(z, n)
    q = np.concatenate([w[:, None], xyz], axis=1)
    flipped = w < 1e-8  # n ≈ −z
    q[flipped] = [0.0, 1.0, 0.0, 0.0]
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    return q.astype(np.float32)


def surfels_from_vertices(xyz_ecef: np.ndarray, normals_enu: np.ndarray,
                          colors_rgba: np.ndarray, *, t_epoch: float, apn: str,
                          source: str, thickness_ratio: float = 0.15,
                          r_min: float = 0.15, r_max: float = 1.2) -> GaussianBatch:
    """Vertices + normals + colours → disk-shaped Gaussian surfels.

    Disk radius adapts to local vertex spacing (nearest-neighbour distance),
    so dense roof meshes get small tight disks and sparse walls get larger
    ones that still close the surface.
    """
    xyz = np.asarray(xyz_ecef, dtype=np.float64).reshape(-1, 3)
    n_pts = len(xyz)

    # local spacing → per-point disk radius
    if n_pts > 2:
        d, _ = cKDTree(xyz).query(xyz, k=2)
        radius = np.clip(d[:, 1] * 0.9, r_min, r_max)
    else:
        radius = np.full(n_pts, 0.5)
    scale = np.stack([radius, radius, radius * thickness_ratio], axis=1).astype(np.float32)

    rot = quats_from_normals(normals_enu)

    rgb = np.asarray(colors_rgba[:, :3], dtype=np.float32) / 255.0
    sh = np.zeros((n_pts, 1, 3), dtype=np.float32)
    sh[:, 0, :] = (rgb - 0.5) / _SH_DC

    return GaussianBatch(
        xyz_ecef=xyz,
        t_epoch=np.full(n_pts, t_epoch, dtype=np.float64),
        scale=scale,
        rot=rot,
        alpha=np.full(n_pts, 0.92, dtype=np.float32),
        sh=sh,
        apn=np.full(n_pts, apn, dtype="<U10"),
        kind="splats",
        source=source,
    )
