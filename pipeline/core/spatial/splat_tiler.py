"""Hierarchical 3DGS level-of-detail tiling: Gaussian batches → streamable tiles.

Raw splat binaries across thousands of parcels cannot be loaded wholesale by a
browser. This module compiles a GaussianBatch into a multi-resolution octree
pyramid serialised as a 3D Tiles v1.1 tileset:

    tiles/
      tileset.json            3D Tiles 1.1 (box volumes, REPLACE refinement,
                              ENU→ECEF root transform, geometricError pyramid)
      L<level>/<x>_<y>_<z>.splat   per-node binary payload

Internal (coarse) nodes carry **downsampled** representatives produced by
opacity-weighted centroid clustering with proper covariance merging — the
merged Gaussian's shape is the second moment of its cluster, so wide viewports
see a faithful low-frequency version of the scene. Leaf nodes carry the raw,
full-density primitives. Spherical-harmonics bands above DC are pruned at
internal nodes (colour detail is invisible at those screen-space error levels).

.splat payload layout (little-endian, 32 bytes per Gaussian — the de-facto
antimatter15 web-splat format):

    float32[3]  position (local ENU metres, about the tileset origin)
    float32[3]  scale    (metres)
    uint8[4]    colour   r, g, b, a            (DC band → sRGB-ish, alpha)
    uint8[4]    rotation quaternion w, x, y, z (q*128+128 quantisation)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .geodesy import ecef_to_enu, ecef_to_wgs84, enu_to_ecef_matrix
from .schema import GaussianBatch

_SH_DC = 0.2820948  # Y_0^0


# ---------------------------------------------------------------------------
# quaternion / covariance algebra (vectorised)
# ---------------------------------------------------------------------------


def quats_to_matrices(q: np.ndarray) -> np.ndarray:
    """(N, 4) wxyz unit quaternions → (N, 3, 3) rotation matrices."""
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    m = np.empty((len(q), 3, 3))
    m[:, 0, 0] = 1 - 2 * (y * y + z * z)
    m[:, 0, 1] = 2 * (x * y - w * z)
    m[:, 0, 2] = 2 * (x * z + w * y)
    m[:, 1, 0] = 2 * (x * y + w * z)
    m[:, 1, 1] = 1 - 2 * (x * x + z * z)
    m[:, 1, 2] = 2 * (y * z - w * x)
    m[:, 2, 0] = 2 * (x * z - w * y)
    m[:, 2, 1] = 2 * (y * z + w * x)
    m[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return m


def matrix_to_quat(r: np.ndarray) -> np.ndarray:
    """Single (3, 3) proper rotation → wxyz quaternion (Shepperd's method)."""
    tr = np.trace(r)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        return np.array([0.25 * s, (r[2, 1] - r[1, 2]) / s,
                         (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s])
    i = int(np.argmax(np.diag(r)))
    if i == 0:
        s = np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = [(r[2, 1] - r[1, 2]) / s, 0.25 * s,
             (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s]
    elif i == 1:
        s = np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = [(r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s,
             0.25 * s, (r[1, 2] + r[2, 1]) / s]
    else:
        s = np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = [(r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s,
             (r[1, 2] + r[2, 1]) / s, 0.25 * s]
    q = np.asarray(q)
    return q / np.linalg.norm(q)


def splat_covariances(scale: np.ndarray, rot: np.ndarray) -> np.ndarray:
    """(N,3) scales + (N,4) quats → (N,3,3) world covariances Σ = R S² Rᵀ."""
    r = quats_to_matrices(rot.astype(np.float64))
    s2 = scale.astype(np.float64) ** 2
    return np.einsum("nij,nj,nkj->nik", r, s2, r)


# ---------------------------------------------------------------------------
# cluster merge (the LOD downsampling primitive)
# ---------------------------------------------------------------------------


def merge_cluster(pos: np.ndarray, cov: np.ndarray, alpha: np.ndarray,
                  sh_dc: np.ndarray, t_epoch: np.ndarray,
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, np.ndarray, float]:
    """Merge a cluster of Gaussians into one representative.

    Mixture second moment:  Σ* = Σᵢ wᵢ (Σᵢ + dᵢdᵢᵀ),  dᵢ = xᵢ − μ*
    so the merged ellipsoid covers both the members' own extents and their
    spatial spread. Decomposed back into (scale, quaternion) by eigen-solve.
    """
    w = np.maximum(alpha.astype(np.float64), 1e-4)
    w = w / w.sum()
    mu = (w[:, None] * pos).sum(axis=0)
    d = pos - mu
    sigma = np.einsum("n,nij->ij", w, cov) + np.einsum("n,ni,nj->ij", w, d, d)
    evals, evecs = np.linalg.eigh(sigma)  # ascending
    evals = np.maximum(evals, 1e-12)
    if np.linalg.det(evecs) < 0:  # keep a proper rotation
        evecs[:, 0] = -evecs[:, 0]
    scale = np.sqrt(evals)
    quat = matrix_to_quat(evecs)
    merged_alpha = float(np.clip((alpha.astype(np.float64) * w).sum() / w.sum(), 0.0, 1.0))
    merged_dc = (w[:, None] * sh_dc).sum(axis=0)
    merged_t = float((w * t_epoch).sum())
    return mu, scale, quat, merged_alpha, merged_dc, merged_t


def downsample_node(pos: np.ndarray, cov: np.ndarray, alpha: np.ndarray,
                    sh_dc: np.ndarray, t_epoch: np.ndarray, *,
                    cube_min: np.ndarray, cube_size: float, grid: int = 24,
                    ) -> tuple[np.ndarray, ...]:
    """Voxel-cluster a node's subtree points into ≤ grid³ representatives."""
    voxel = cube_size / grid
    keys = np.clip(np.floor((pos - cube_min) / voxel).astype(np.int64), 0, grid - 1)
    flat = keys[:, 0] * grid * grid + keys[:, 1] * grid + keys[:, 2]
    order = np.argsort(flat, kind="stable")
    flat_sorted = flat[order]
    boundaries = np.flatnonzero(np.diff(flat_sorted)) + 1
    groups = np.split(order, boundaries)

    out_pos, out_scale, out_rot, out_alpha, out_dc, out_t = [], [], [], [], [], []
    for g in groups:
        mu, sc, q, a, dc, t = merge_cluster(pos[g], cov[g], alpha[g], sh_dc[g], t_epoch[g])
        out_pos.append(mu)
        out_scale.append(sc)
        out_rot.append(q)
        out_alpha.append(a)
        out_dc.append(dc)
        out_t.append(t)
    return (np.asarray(out_pos), np.asarray(out_scale), np.asarray(out_rot),
            np.asarray(out_alpha, dtype=np.float64), np.asarray(out_dc),
            np.asarray(out_t))


# ---------------------------------------------------------------------------
# binary payload
# ---------------------------------------------------------------------------


def pack_splat(pos: np.ndarray, scale: np.ndarray, rot: np.ndarray,
               alpha: np.ndarray, sh_dc: np.ndarray) -> bytes:
    """Pack Gaussians into the 32-byte .splat wire format."""
    n = len(pos)
    rgb = np.clip(0.5 + sh_dc * _SH_DC, 0.0, 1.0)
    rec = np.empty(n, dtype=[("pos", "<f4", 3), ("scale", "<f4", 3),
                             ("rgba", "u1", 4), ("rot", "u1", 4)])
    rec["pos"] = pos.astype(np.float32)
    rec["scale"] = scale.astype(np.float32)
    rec["rgba"][:, :3] = np.round(rgb * 255).astype(np.uint8)
    rec["rgba"][:, 3] = np.round(np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    q = rot / np.linalg.norm(rot, axis=1, keepdims=True)
    rec["rot"] = np.clip(np.round(q * 128 + 128), 0, 255).astype(np.uint8)
    return rec.tobytes()


# ---------------------------------------------------------------------------
# octree build + tileset emission
# ---------------------------------------------------------------------------


@dataclass
class TilingResult:
    tileset_path: Path
    n_nodes: int
    n_leaves: int
    levels: int
    total_bytes: int
    origin_lonlat: tuple[float, float]
    origin_alt_m: float = 0.0  # ellipsoidal altitude of the ENU origin


def tile_batch(batch: GaussianBatch, out_dir: Path, *, leaf_max: int = 12000,
               max_depth: int = 8, node_budget_grid: int = 24) -> TilingResult:
    """Compile one GaussianBatch into a 3D Tiles 1.1 splat pyramid."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- local frame: ENU about the batch centroid (3D Tiles root transform) ----
    centroid_ecef = batch.xyz_ecef.mean(axis=0)
    lon0, lat0, h0 = ecef_to_wgs84(centroid_ecef[None, :])
    lon0, lat0, h0 = float(lon0[0]), float(lat0[0]), float(h0[0])
    pos = ecef_to_enu(batch.xyz_ecef, centroid_ecef, lon0, lat0)
    cov = splat_covariances(batch.scale, batch.rot)
    alpha = batch.alpha.astype(np.float64)
    sh_dc = batch.sh[:, 0, :].astype(np.float64)
    t_epoch = batch.t_epoch

    # root cube: cubic bounding volume (octree subdivision stays isotropic)
    lo = pos.min(axis=0)
    hi = pos.max(axis=0)
    size = float((hi - lo).max()) * 1.0001 + 1e-6
    root_min = (lo + hi) / 2 - size / 2

    stats = {"nodes": 0, "leaves": 0, "bytes": 0, "max_level": 0}

    def build(idx: np.ndarray, level: int, ix: int, iy: int, iz: int) -> dict:
        cube_size = size / (1 << level)
        cube_min = root_min + np.array([ix, iy, iz]) * cube_size
        center = cube_min + cube_size / 2
        half = cube_size / 2
        stats["nodes"] += 1
        stats["max_level"] = max(stats["max_level"], level)

        is_leaf = len(idx) <= leaf_max or level >= max_depth
        if is_leaf:
            payload = pack_splat(pos[idx], batch.scale[idx], batch.rot[idx],
                                 alpha[idx], sh_dc[idx])
            stats["leaves"] += 1
        else:
            p, s, q, a, dc, _t = downsample_node(
                pos[idx], cov[idx], alpha[idx], sh_dc[idx], t_epoch[idx],
                cube_min=cube_min, cube_size=cube_size, grid=node_budget_grid)
            payload = pack_splat(p, s, q, a, dc)

        rel = f"L{level}/{ix}_{iy}_{iz}.splat"
        f = out_dir / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(payload)
        stats["bytes"] += len(payload)

        node: dict = {
            "boundingVolume": {"box": [float(center[0]), float(center[1]), float(center[2]),
                                       half, 0, 0, 0, half, 0, 0, 0, half]},
            # screen-space error driver: a node's content stands in for detail
            # at its cube scale; leaves are exact (error 0)
            "geometricError": 0.0 if is_leaf else cube_size / 4.0,
            "refine": "REPLACE",
            "content": {"uri": rel},
            # terrain-clamp anchor: the octree cube bottom is unrelated to where
            # content sits (cubes are isotropic, sized by the max extent) — the
            # client must clamp on the CONTENT's lowest point
            "extras": {"contentMinZ": float(pos[idx][:, 2].min())},
        }
        if not is_leaf:
            children = []
            local = pos[idx] - cube_min
            octant = ((local[:, 0] >= half).astype(int)
                      | ((local[:, 1] >= half).astype(int) << 1)
                      | ((local[:, 2] >= half).astype(int) << 2))
            for o in range(8):
                sub = idx[octant == o]
                if len(sub) == 0:
                    continue
                children.append(build(sub, level + 1,
                                      ix * 2 + (o & 1), iy * 2 + ((o >> 1) & 1),
                                      iz * 2 + ((o >> 2) & 1)))
            node["children"] = children
        return node

    root = build(np.arange(len(batch)), 0, 0, 0, 0)
    root["transform"] = [float(v) for v in
                         enu_to_ecef_matrix(lon0, lat0, h0).T.reshape(-1)]  # column-major

    tileset = {
        "asset": {"version": "1.1", "generator": "openpali splat_tiler"},
        "geometricError": size,
        "extensionsUsed": ["OPENPALI_splat_content"],
        "root": root,
    }
    ts_path = out_dir / "tileset.json"
    ts_path.write_text(json.dumps(tileset))
    return TilingResult(
        tileset_path=ts_path,
        n_nodes=stats["nodes"],
        n_leaves=stats["leaves"],
        levels=stats["max_level"] + 1,
        total_bytes=stats["bytes"],
        origin_lonlat=(lon0, lat0),
        origin_alt_m=h0,
    )
