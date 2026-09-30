"""Characterize existing OpenPali spatial code without changing its outputs.

Run from the repository root:
    pipeline/.venv/bin/python Docs/Research/experiments/spatial_summary_probe.py \
        --out Docs/Research/2026-09-29-systems-measurements.json

Synthetic regrouping probes establish numerical behavior, not scene accuracy.
The registration probe reuses the project's existing synthetic fixture.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pipeline"))

import laspy
import numpy as np

from core.spatial.geodesy import wgs84_to_ecef
from core.spatial.splat_tiler import merge_cluster, pack_splat, splat_covariances
from openpali.intelligence.visual import measure


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def header(path: Path) -> dict:
    with laspy.open(path) as reader:
        h = reader.header
        return {
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha_file(path),
            "points": int(h.point_count),
            "point_format": h.point_format.id,
            "point_record_bytes": h.point_format.size,
            "embedded_crs": str(h.parse_crs()),
            "vlrs": [{"user_id": v.user_id, "record_id": v.record_id} for v in h.vlrs],
            "evlrs": [{"user_id": v.user_id, "record_id": v.record_id} for v in (h.evlrs or [])],
            "copc_info_vlr_present": any(
                v.user_id == "copc" and v.record_id == 1 for v in h.vlrs
            ),
        }


def merge_probe() -> dict:
    # Three equally weighted Gaussian samples, one metre apart.
    pos = np.array([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]])
    scale = np.full((3, 3), 0.1)
    rot = np.tile([1., 0., 0., 0.], (3, 1))
    cov = splat_covariances(scale, rot)
    alpha = np.full(3, 0.8)
    dc = np.zeros((3, 3))
    epoch = np.array([0., 10., 20.])  # arbitrary synthetic seconds
    area = np.full(3, 0.01)

    def combine(indices):
        return merge_cluster(pos[indices], cov[indices], alpha[indices],
                             dc[indices], epoch[indices], area[indices], 100.)

    def staged(first, last):
        p, s, q, a, c, t = combine(first)
        s_area = np.sort(s)[1:].prod()
        return merge_cluster(
            np.stack([p, pos[last]]),
            np.concatenate([splat_covariances(s[None, :], q[None, :]),
                            cov[last:last + 1]]),
            np.array([a, alpha[last]]), np.stack([c, dc[last]]),
            np.array([t, epoch[last]]), np.array([s_area, area[last]]), 100.)

    direct, left, right = combine([0, 1, 2]), staged([0, 1], 2), staged([1, 2], 0)

    # Additive sufficient statistics, with the SAME alpha weights as the
    # direct input calculation. This is a reference algebra, not a proposed
    # interpretation of alpha as sensor confidence.
    def stats(indices):
        w = alpha[indices]
        x = pos[indices]
        return (w.sum(), np.einsum("n,ni->i", w, x),
                np.einsum("n,nij->ij", w, cov[indices])
                + np.einsum("n,ni,nj->ij", w, x, x))

    exact = stats([0, 1, 2])
    groups = [stats([0, 1]), stats([2])]
    grouped = tuple(sum(g[k] for g in groups) for k in range(3))
    reference_error = max(float(np.max(np.abs(np.asarray(a) - np.asarray(b))))
                          for a, b in zip(exact, grouped))

    def output(r):
        return {"position_m": r[0].tolist(), "scale_m": r[1].tolist(),
                "alpha": r[3], "synthetic_time_seconds": r[5]}

    payload = pack_splat(pos, scale, rot, alpha, dc)
    return {
        "input": "three equal-alpha isotropic Gaussians at x=0,1,2 metres",
        "cap_radius_m": 100.,
        "direct": output(direct), "merge_01_then_2": output(left),
        "merge_12_then_0": output(right),
        "direct_vs_staged_position_difference_m": float(np.linalg.norm(direct[0] - left[0])),
        "left_vs_right_position_difference_m": float(np.linalg.norm(left[0] - right[0])),
        "additive_statistics_max_absolute_difference": reference_error,
        "packed_bytes": len(payload), "packed_bytes_per_record": len(payload) // 3,
        "packed_fields_from_source": ["position_f32x3", "scale_f32x3", "rgba_u8x4", "quaternion_u8x4"],
        "limitations": ["not a rendering or geometric accuracy benchmark",
                        "regrouping exercises merge_cluster; the production octree uses a fixed spatial grouping",
                        "render opacity is not a sensor confidence weight"],
    }


def run(skip_registration: bool) -> dict:
    baseline = json.loads((ROOT / "Docs/Research/2026-09-24-visual-baseline.json").read_text())
    crop = baseline["parcel_crop"]
    tile = ROOT / crop["tile_path"]
    path = ROOT / crop["crop_path"]
    started = time.perf_counter()
    measured = measure(path, crop["acquisition_date"], crop["crop_sha256"],
                       crs_override="EPSG:6340", crs_evidence=crop["capture_date_evidence"])
    elapsed = time.perf_counter() - started
    previous = json.loads((ROOT / "Docs/Research/2026-09-24-lidar-measurements.json").read_text())
    compare = ["ground_points", "surface_points", "normalized_points",
               "ground_support_fraction", "height_quantiles_m"]
    origin = wgs84_to_ecef(np.array([-118.53]), np.array([34.05]), np.array([100.]))[0]
    result = {
        "schema": "systems-characterization-v1",
        "produced_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree": "modified; source hashes below identify the inspected implementations",
        "environment": {"system": platform.system(), "machine": platform.machine(),
                        "python": platform.python_version(), "numpy": np.__version__, "laspy": laspy.__version__},
        "source_hashes": {name: sha_file(ROOT / name) for name in [
            "pipeline/core/spatial/splat_tiler.py", "pipeline/core/spatial/schema.py",
            "pipeline/core/spatial/registration.py", "pipeline/openpali/intelligence/visual.py",
            "pipeline/openpali/spatial/reconstruction.py", "Docs/Research/experiments/spatial_summary_probe.py"]},
        "real_lidar": {"tile_header": header(tile), "crop_header": header(path),
                       "reproduced_measurement": measured,
                       "matches_recorded_fields": {k: measured[k] == previous[k] for k in compare},
                       "one_run_seconds_including_crop_hash_read_decode_and_query": elapsed,
                       "crop_fraction_of_tile_points": crop["points_in_crop"] / crop["tile_points_read"],
                       "full_scan_points_per_retained_point": crop["tile_points_read"] / crop["points_in_crop"]},
        "synthetic_merge": merge_probe(),
        "precision": {"ecef_origin_m": origin.tolist(),
                      "float32_spacing_m_at_ecef_origin": np.abs(np.spacing(origin.astype(np.float32))).tolist(),
                      "float32_spacing_m_at_local_100_m": float(np.spacing(np.float32(100.)))},
    }
    if not skip_registration:
        from openpali.spatial.reconstruction import build_fixture_scene, run_reconstruction
        started = time.perf_counter()
        reconstruction = run_reconstruction(build_fixture_scene())
        result["synthetic_registration"] = {
            "seed": 20250121, "gates": reconstruction.gates,
            "elapsed_seconds_one_run": time.perf_counter() - started,
            "scope": "existing synthetic fixture only; no real sensor capture or GPU measured"}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-registration", action="store_true")
    args = parser.parse_args()
    result = run(args.skip_registration)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
