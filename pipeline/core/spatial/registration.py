"""Rigid spatial registration: noisy capture → absolute LARIAC-anchored space.

Pipeline (all stages fully implemented, numpy + scipy.spatial only):

    raw capture ──► SOR ──► Mahalanobis prefilter ──► RANSAC coarse ──► ICP fine
                   (k-NN     (global density gate)     (descriptor-      (trimmed,
                   distance                             matched 3-pt      χ²-gated
                   gate)                                Kabsch)           Kabsch loop)

The estimated transform is strictly rigid (SE(3)): x' = R @ x + t, det(R)=+1.
All solves use the Kabsch/SVD closed form with reflection correction.

Coordinates are local-ENU metres (callers convert from ECEF via geodesy.ecef_to_enu
about the parcel centroid — registering near the Earth's surface in raw ECEF is
numerically hostile and hides translation errors inside the 6.37e6 m offset).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

# χ² inverse-CDF at 0.975 for 3 dof — residual gate for ICP Mahalanobis filtering
_CHI2_975_3DOF = 9.348


# ---------------------------------------------------------------------------
# filtering
# ---------------------------------------------------------------------------


def statistical_outlier_removal(points: np.ndarray, *, k: int = 16,
                                std_ratio: float = 2.0) -> np.ndarray:
    """Classic SOR: drop points whose mean k-NN distance is an outlier.

    Returns the boolean keep-mask (so callers can filter colours/attributes
    in lockstep with positions).
    """
    pts = np.asarray(points, dtype=np.float64)
    n = len(pts)
    if n <= k + 1:
        return np.ones(n, dtype=bool)
    tree = cKDTree(pts)
    # k+1 because each point is its own nearest neighbour at distance 0
    dists, _ = tree.query(pts, k=k + 1)
    mean_knn = dists[:, 1:].mean(axis=1)
    mu, sigma = mean_knn.mean(), mean_knn.std()
    return mean_knn <= mu + std_ratio * sigma


def mahalanobis_filter(points: np.ndarray, *, chi2_threshold: float = 16.27) -> np.ndarray:
    """Global Mahalanobis gate against the cloud's own Gaussian fit.

    Rejects gross telemetry drift / GPS multipath points that sit far outside
    the capture's spatial distribution. Default threshold is χ²₀.₉₉₉(3) — only
    the extreme tail is cut, structure is preserved. Returns keep-mask.
    """
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 8:
        return np.ones(len(pts), dtype=bool)
    mu = pts.mean(axis=0)
    cov = np.cov(pts.T) + np.eye(3) * 1e-9  # regularise degenerate (planar) clouds
    cov_inv = np.linalg.inv(cov)
    d = pts - mu
    m2 = np.einsum("ni,ij,nj->n", d, cov_inv, d)
    return m2 <= chi2_threshold


# ---------------------------------------------------------------------------
# closed-form rigid solve
# ---------------------------------------------------------------------------


def kabsch(source: np.ndarray, target: np.ndarray,
           weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Optimal rigid (R, t) minimising Σ wᵢ‖R sᵢ + t − tᵢ‖² (Kabsch–Umeyama).

    SVD of the weighted cross-covariance; det correction guarantees a proper
    rotation (no reflection) even for degenerate/planar correspondence sets.
    """
    s = np.asarray(source, dtype=np.float64)
    t = np.asarray(target, dtype=np.float64)
    if weights is None:
        weights = np.ones(len(s))
    w = np.asarray(weights, dtype=np.float64)
    w = w / w.sum()
    mu_s = (w[:, None] * s).sum(axis=0)
    mu_t = (w[:, None] * t).sum(axis=0)
    sc = s - mu_s
    tc = t - mu_t
    h = (w[:, None] * sc).T @ tc  # 3×3 cross-covariance
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    diag = np.diag([1.0, 1.0, d])
    rot = vt.T @ diag @ u.T
    trans = mu_t - rot @ mu_s
    return rot, trans


def apply_rigid(points: np.ndarray, rot: np.ndarray, trans: np.ndarray) -> np.ndarray:
    return np.asarray(points, dtype=np.float64) @ rot.T + trans


# ---------------------------------------------------------------------------
# coarse registration: descriptor-matched RANSAC
# ---------------------------------------------------------------------------


def _voxel_downsample(points: np.ndarray, voxel: float) -> np.ndarray:
    """Centroid-per-voxel downsampling (deterministic)."""
    pts = np.asarray(points, dtype=np.float64)
    keys = np.floor(pts / voxel).astype(np.int64)
    # lexicographic unique voxels
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    sums = np.zeros((inverse.max() + 1, 3))
    counts = np.zeros(inverse.max() + 1)
    np.add.at(sums, inverse, pts)
    np.add.at(counts, inverse, 1.0)
    return sums / counts[:, None]


def _geometric_descriptors(points: np.ndarray, *, k: int = 12) -> np.ndarray:
    """Per-point local-geometry descriptor (5-D), rotation/translation invariant
    in the horizontal plane (gravity-aligned captures — true for buildings):

      [ height above cloud floor,
        mean k-NN distance        (local density),
        λ1/λ0, λ2/λ0              (local covariance shape: planarity/linearity),
        vertical extent of the k-NN neighbourhood ]
    """
    pts = np.asarray(points, dtype=np.float64)
    n = len(pts)
    k = min(k, n - 1)
    tree = cKDTree(pts)
    dists, idx = tree.query(pts, k=k + 1)
    desc = np.zeros((n, 5))
    floor = pts[:, 2].min()
    desc[:, 0] = pts[:, 2] - floor
    desc[:, 1] = dists[:, 1:].mean(axis=1)
    for i in range(n):
        nb = pts[idx[i]]
        cov = np.cov((nb - nb.mean(axis=0)).T)
        ev = np.sort(np.maximum(np.linalg.eigvalsh(cov), 0.0))[::-1]  # λ0≥λ1≥λ2
        if ev[0] > 1e-12:
            desc[i, 2] = ev[1] / ev[0]
            desc[i, 3] = ev[2] / ev[0]
        desc[i, 4] = np.ptp(nb[:, 2])
    # normalise each channel to unit variance so no single feature dominates
    sd = desc.std(axis=0)
    sd[sd < 1e-12] = 1.0
    return desc / sd


def ransac_coarse_align(source: np.ndarray, target: np.ndarray, *,
                        voxel: float = 1.0, inlier_threshold: float | None = None,
                        max_iterations: int = 4000, seed: int = 7,
                        ) -> tuple[np.ndarray, np.ndarray, float]:
    """Global coarse alignment: descriptor-matched 3-point RANSAC.

    1. Voxel-downsample both clouds to building scale.
    2. Compute local geometric descriptors; propose correspondences by nearest
       neighbour in descriptor space (source → target).
    3. RANSAC: sample 3 correspondences, demand congruent triangles (rigid
       motions preserve pairwise distances), solve Kabsch, count inliers by
       3-D nearest-neighbour distance, keep the best hypothesis.
    4. Re-solve Kabsch on the full inlier set of the winning hypothesis.

    Returns (R, t, inlier_fraction).
    """
    rng = np.random.default_rng(seed)
    src = _voxel_downsample(source, voxel)
    tgt = _voxel_downsample(target, voxel)
    if inlier_threshold is None:
        inlier_threshold = 2.5 * voxel

    d_src = _geometric_descriptors(src)
    d_tgt = _geometric_descriptors(tgt)
    desc_tree = cKDTree(d_tgt)
    _, match = desc_tree.query(d_src, k=1)
    corr_s, corr_t = src, tgt[match]  # candidate correspondence pairs

    tgt_tree = cKDTree(tgt)
    n = len(corr_s)
    if n < 3:
        raise ValueError("not enough points for coarse registration")

    best_rot, best_trans = np.eye(3), np.zeros(3)
    best_inliers = -1
    for _ in range(max_iterations):
        pick = rng.choice(n, size=3, replace=False)
        s3, t3 = corr_s[pick], corr_t[pick]
        # congruence pre-check: rigid transforms preserve pairwise distances
        ds = np.array([np.linalg.norm(s3[0] - s3[1]),
                       np.linalg.norm(s3[1] - s3[2]),
                       np.linalg.norm(s3[0] - s3[2])])
        dt = np.array([np.linalg.norm(t3[0] - t3[1]),
                       np.linalg.norm(t3[1] - t3[2]),
                       np.linalg.norm(t3[0] - t3[2])])
        if ds.min() < voxel or np.any(np.abs(ds - dt) > inlier_threshold):
            continue
        rot, trans = kabsch(s3, t3)
        moved = apply_rigid(src, rot, trans)
        d_nn, _ = tgt_tree.query(moved, k=1, distance_upper_bound=inlier_threshold)
        inliers = int(np.isfinite(d_nn).sum())
        if inliers > best_inliers:
            best_inliers = inliers
            best_rot, best_trans = rot, trans

    # final polish: Kabsch over all NN-inlier pairs of the best hypothesis
    moved = apply_rigid(src, best_rot, best_trans)
    d_nn, j = tgt_tree.query(moved, k=1, distance_upper_bound=inlier_threshold)
    ok = np.isfinite(d_nn)
    if ok.sum() >= 3:
        best_rot2, best_trans2 = kabsch(src[ok], tgt[j[ok]])
        best_rot, best_trans = best_rot2, best_trans2
    return best_rot, best_trans, float(ok.sum()) / max(len(src), 1)


# ---------------------------------------------------------------------------
# fine registration: trimmed ICP with Mahalanobis residual gating
# ---------------------------------------------------------------------------


@dataclass
class ICPResult:
    rotation: np.ndarray  # (3, 3)
    translation: np.ndarray  # (3,)
    rmse: float
    iterations: int
    converged: bool
    inlier_fraction: float


def icp_refine(source: np.ndarray, target: np.ndarray, *,
               init_rot: np.ndarray | None = None,
               init_trans: np.ndarray | None = None,
               max_iterations: int = 60, max_corr_dist: float = 2.0,
               tolerance: float = 1e-6) -> ICPResult:
    """Point-to-point ICP with per-iteration Mahalanobis residual gating.

    Each iteration:
      1. NN correspondences within max_corr_dist (kd-tree).
      2. Fit a Gaussian to the residual vectors; gate at χ²₀.₉₇₅(3) Mahalanobis
         distance — anisotropic trimming that rejects drifted correspondences
         without a fixed scalar cutoff.
      3. Kabsch on the gated set; update the cumulative transform.
      4. Converged when |Δrmse| < tolerance.
    """
    src0 = np.asarray(source, dtype=np.float64)
    tgt = np.asarray(target, dtype=np.float64)
    rot = np.eye(3) if init_rot is None else np.asarray(init_rot, dtype=np.float64)
    trans = np.zeros(3) if init_trans is None else np.asarray(init_trans, dtype=np.float64)

    tree = cKDTree(tgt)
    prev_rmse = np.inf
    rmse = np.inf
    inlier_frac = 0.0
    it = 0
    for it in range(1, max_iterations + 1):
        moved = apply_rigid(src0, rot, trans)
        d_nn, j = tree.query(moved, k=1, distance_upper_bound=max_corr_dist)
        ok = np.isfinite(d_nn)
        if ok.sum() < 6:
            return ICPResult(rot, trans, float("inf"), it, False, 0.0)

        res = tgt[j[ok]] - moved[ok]  # residual vectors
        mu = res.mean(axis=0)
        cov = np.cov(res.T) + np.eye(3) * 1e-12
        cov_inv = np.linalg.inv(cov)
        dm = res - mu
        m2 = np.einsum("ni,ij,nj->n", dm, cov_inv, dm)
        gate = m2 <= _CHI2_975_3DOF

        s_in = src0[ok][gate]
        t_in = tgt[j[ok]][gate]
        if len(s_in) < 6:
            s_in, t_in = src0[ok], tgt[j[ok]]  # gate too aggressive — fall back
        rot, trans = kabsch(s_in, t_in)

        moved = apply_rigid(src0, rot, trans)
        d_nn, _ = tree.query(moved, k=1, distance_upper_bound=max_corr_dist)
        ok2 = np.isfinite(d_nn)
        rmse = float(np.sqrt(np.mean(d_nn[ok2] ** 2))) if ok2.any() else float("inf")
        inlier_frac = float(ok2.mean())
        if abs(prev_rmse - rmse) < tolerance:
            return ICPResult(rot, trans, rmse, it, True, inlier_frac)
        prev_rmse = rmse

    return ICPResult(rot, trans, rmse, it, False, inlier_frac)


# ---------------------------------------------------------------------------
# end-to-end
# ---------------------------------------------------------------------------


@dataclass
class RegistrationReport:
    rotation: np.ndarray
    translation: np.ndarray
    rmse: float
    n_input: int
    n_after_sor: int
    n_after_mahalanobis: int
    coarse_inlier_fraction: float
    icp: ICPResult

    @property
    def accepted(self) -> bool:
        """Quality gate for admitting a capture into the canonical store."""
        return self.icp.converged and self.rmse < 0.75 and self.icp.inlier_fraction > 0.5


def register_capture(capture: np.ndarray, prior: np.ndarray, *,
                     voxel: float = 1.0, seed: int = 7) -> RegistrationReport:
    """Full pipeline: filter a noisy capture and rigidly align it to the
    LARIAC-derived prior. Both inputs are local-ENU metres about the same origin."""
    capture = np.asarray(capture, dtype=np.float64)
    n0 = len(capture)

    keep = statistical_outlier_removal(capture)
    capture_sor = capture[keep]
    keep2 = mahalanobis_filter(capture_sor)
    clean = capture_sor[keep2]
    if len(clean) < 16:
        raise ValueError(f"capture too sparse after filtering ({len(clean)} pts)")

    rot_c, trans_c, frac = ransac_coarse_align(clean, prior, voxel=voxel, seed=seed)
    icp = icp_refine(clean, prior, init_rot=rot_c, init_trans=trans_c,
                     max_corr_dist=3.0 * voxel)
    return RegistrationReport(
        rotation=icp.rotation,
        translation=icp.translation,
        rmse=icp.rmse,
        n_input=n0,
        n_after_sor=len(capture_sor),
        n_after_mahalanobis=len(clean),
        coarse_inlier_fraction=frac,
        icp=icp,
    )
