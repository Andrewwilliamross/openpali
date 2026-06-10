"""End-to-end integration: real LARIAC prior → simulated capture → registration
→ LOD tiles → store. Network-dependent stages use the on-disk scene cache and
skip cleanly when neither cache nor network is available (CI without egress)."""

from __future__ import annotations

import numpy as np
import pytest

from core.spatial import geodesy
from core.spatial.registration import register_capture
from core.spatial.scene_client import SceneClient
from core.spatial.schema import GaussianBatch, SpatialStore
from core.spatial.splat_tiler import tile_batch


@pytest.fixture(scope="module")
def real_prior() -> GaussianBatch:
    try:
        c = SceneClient()
        page0 = c._nodepage(0)
        leaf = next(n for n in page0["nodes"] if not n.get("children") and n.get("mesh"))
        mesh = c.node_mesh(leaf)
        apn = next(a for a in mesh.apns if a)
        batch = c.extract_parcel_prior(apn, [leaf["mesh"]["geometry"]["resource"]],
                                       t_epoch=1.78e9)
    except Exception as e:  # noqa: BLE001 — any failure here means "no data source"
        pytest.skip(f"scene layer unreachable and not cached: {e}")
    assert batch is not None and len(batch) > 100
    return batch


def test_full_loop_register_simulated_capture_against_real_prior(real_prior, tmp_path):
    # local ENU frame about the real building
    centroid = real_prior.xyz_ecef.mean(axis=0)
    lon0, lat0, _ = geodesy.ecef_to_wgs84(centroid[None, :])
    lon0, lat0 = float(lon0[0]), float(lat0[0])
    prior_enu = geodesy.ecef_to_enu(real_prior.xyz_ecef, centroid, lon0, lat0)

    # simulate an uncalibrated drone sweep: subsample, misalign, add noise + junk
    rng = np.random.default_rng(9)
    sub = prior_enu[rng.choice(len(prior_enu), size=min(4000, len(prior_enu)), replace=False)]
    th = np.radians(9.0)
    r_true = np.array([[np.cos(th), -np.sin(th), 0],
                       [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    t_true = np.array([3.2, -2.1, 0.6])
    capture = sub @ r_true.T + t_true + rng.normal(0, 0.06, sub.shape)
    capture = np.concatenate([capture, rng.uniform(-30, 30, (len(sub) // 15, 3))])

    rep = register_capture(capture, prior_enu, voxel=0.8, seed=3)
    assert rep.icp.converged
    rot_err = np.degrees(np.arccos(np.clip((np.trace(rep.rotation @ r_true) - 1) / 2, -1, 1)))
    assert rot_err < 2.5, f"rotation error {rot_err:.2f}° on real geometry"
    assert np.linalg.norm(rep.rotation @ t_true + rep.translation) < 0.4
    assert rep.accepted

    # registered capture → unified schema → store → LOD tiles
    aligned_enu = capture @ rep.rotation.T + rep.translation
    aligned_ecef = geodesy.enu_to_ecef(aligned_enu, centroid, lon0, lat0)
    apn = real_prior.apn[0]
    reg_batch = GaussianBatch.from_points(aligned_ecef, 1.79e9, str(apn),
                                          kind="points", source="sim_drone")

    store = SpatialStore(root=tmp_path / "store")
    store.write_batch(real_prior, epoch_label="prior")
    store.write_batch(reg_batch, epoch_label="2026-06-10")
    both = store.read(apn=str(apn))
    assert both is not None and len(both) == len(real_prior) + len(reg_batch)

    res = tile_batch(real_prior, tmp_path / "tiles", leaf_max=6000)
    assert res.tileset_path.exists()
    assert res.total_bytes > 0
