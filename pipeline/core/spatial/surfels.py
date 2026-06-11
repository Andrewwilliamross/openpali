"""Surfel construction: oriented, coloured disk-Gaussians from building meshes.

Two generators:
- `surfels_from_vertices` — one surfel per (deduped) mesh vertex. Kept for the
  footprint-extrusion fallback; coverage tracks the source vertex density.
- `sample_faces_stratified` — **stratified barycentric face densification**:
  surfels sampled ACROSS every triangle at a target spacing, closing the
  low-poly LARIAC shells into watertight-looking surfaces regardless of how
  sparse the source vertices are.

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

# face-densification defaults
TARGET_SPACING_M = 0.75  # stratified sample spacing on the surface
DISK_RADIUS_FACTOR = 0.75  # disk radius = factor × spacing (≈1.7× area coverage)
FLAT_SZ_M = 0.001  # structural flatness: surfels are surfaces, not blobs
MAX_SURFELS_PER_PARCEL = 7000


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


def stratified_barycentric(n: int, rng: np.random.Generator) -> np.ndarray:
    """N low-discrepancy barycentric coordinates (u, v, w) on the unit triangle.

    A jittered ⌈√n⌉×⌈√n⌉ grid in the unit square (stratified — at most one
    sample per cell, so no white-noise clumping or holes) is mapped onto the
    triangle with the area-preserving square-root warp:

        u = 1 − √r₁,   v = r₂·√r₁,   w = 1 − u − v

    which is uniform in *area*, not in parameter space.
    """
    if n <= 0:
        return np.zeros((0, 3))
    k = int(np.ceil(np.sqrt(n)))
    cells = np.stack(np.meshgrid(np.arange(k), np.arange(k), indexing="ij"),
                     axis=-1).reshape(-1, 2)
    # randomise which cells survive when k² > n so truncation has no spatial bias
    cells = cells[rng.permutation(len(cells))[:n]]
    jitter = rng.random((n, 2))
    r = (cells + jitter) / k  # stratified (r1, r2) in [0,1)²
    sqrt_r1 = np.sqrt(r[:, 0])
    u = 1.0 - sqrt_r1
    v = r[:, 1] * sqrt_r1
    w = 1.0 - u - v
    return np.stack([u, v, w], axis=1)


def sample_faces_stratified(
    tri_verts_ecef: np.ndarray,  # (T, 3, 3) triangle vertices, ECEF metres
    tri_vert_colors: np.ndarray,  # (T, 3, 4) per-vertex RGBA u8
    enu_rotation_at_origin: np.ndarray,  # (3, 3) ECEF→ENU component rotation
    *,
    t_epoch: float,
    apn: str,
    source: str,
    spacing_m: float = TARGET_SPACING_M,
    max_surfels: int = MAX_SURFELS_PER_PARCEL,
    seed: int | None = None,
) -> GaussianBatch | None:
    """Densify a triangle soup into a closed surfel surface.

    Per triangle: sample count ∝ face area (≥1 for any non-degenerate face),
    positions/colours interpolated barycentrically, orientation = the FACE
    normal (ECEF cross product, rotated into ENU), scale = (r, r, FLAT_SZ_M)
    with r tied to the realised spacing. Deterministic per parcel via the
    APN-seeded RNG.
    """
    tris = np.asarray(tri_verts_ecef, dtype=np.float64)
    cols = np.asarray(tri_vert_colors, dtype=np.float64)
    if len(tris) == 0:
        return None

    # face areas + normals from the ECEF cross product (Euclidean frame, exact)
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    cross = np.cross(e1, e2)
    cross_norm = np.linalg.norm(cross, axis=1)
    area = 0.5 * cross_norm
    ok = area > 1e-6  # drop degenerate slivers
    if not ok.any():
        return None
    tris, cols, cross, cross_norm, area = (
        tris[ok], cols[ok], cross[ok], cross_norm[ok], area[ok])

    # area-proportional sample counts at the target density, capped per parcel
    density = 1.0 / (spacing_m * spacing_m)
    counts = np.maximum(np.rint(area * density).astype(np.int64), 1)
    total = int(counts.sum())
    if total > max_surfels:
        scale_f = max_surfels / total
        counts = np.maximum(np.rint(counts * scale_f).astype(np.int64), 1)
        total = int(counts.sum())
    # realised spacing (after the cap) drives the disk radius so coverage holds
    realised_spacing = float(np.sqrt(area.sum() / max(total, 1)))
    radius = float(np.clip(DISK_RADIUS_FACTOR * max(realised_spacing, spacing_m),
                           0.2, 2.5))

    # Stable across processes — Python's hash() is salted per run, which would
    # make nightly extraction non-reproducible. APNs are numeric strings.
    if seed is None:
        try:
            seed = int(apn) & 0x7FFFFFFF
        except ValueError:
            import zlib

            seed = zlib.crc32(apn.encode()) & 0x7FFFFFFF
    rng = np.random.default_rng(seed)

    pos_parts: list[np.ndarray] = []
    col_parts: list[np.ndarray] = []
    nrm_parts: list[np.ndarray] = []
    for i in range(len(tris)):
        bary = stratified_barycentric(int(counts[i]), rng)  # (n, 3)
        pos_parts.append(bary @ tris[i])  # barycentric interp, linear in ECEF
        col_parts.append(bary @ cols[i, :, :3])
        n_face = cross[i] / cross_norm[i]
        nrm_parts.append(np.tile(n_face, (len(bary), 1)))
    pos = np.concatenate(pos_parts)
    rgb = np.clip(np.concatenate(col_parts), 0, 255)
    n_ecef = np.concatenate(nrm_parts)
    n_pts = len(pos)

    # face normals → ENU components (frame convention for quats and the
    # renderer's anti-smear mask)
    n_enu = n_ecef @ np.asarray(enu_rotation_at_origin, dtype=np.float64).T
    rot = quats_from_normals(n_enu)

    scale = np.full((n_pts, 3), radius, dtype=np.float32)
    scale[:, 2] = FLAT_SZ_M  # Σ = R·S²·Rᵀ with s_z→0: a true surface element

    sh = np.zeros((n_pts, 1, 3), dtype=np.float32)
    sh[:, 0, :] = ((rgb / 255.0).astype(np.float32) - 0.5) / _SH_DC

    return GaussianBatch(
        xyz_ecef=pos,
        t_epoch=np.full(n_pts, t_epoch, dtype=np.float64),
        scale=scale,
        rot=rot,
        alpha=np.full(n_pts, 0.92, dtype=np.float32),
        sh=sh,
        apn=np.full(n_pts, apn, dtype="<U10"),
        kind="splats",
        source=source,
    )


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
