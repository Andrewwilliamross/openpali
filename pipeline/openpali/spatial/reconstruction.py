"""Multimodal reconstruction: capture -> registered asset -> reviewed candidate
(MULTIMODAL-001).

The deterministic CPU stress fixture fabricates two partially overlapping,
noisy, occluded depth views of a synthetic block scene with mixed change and
no-change regions, displaces the second view by a WITHHELD rigid transform
(~1.5 m translation, ~3 degree rotation), and requires the PRODUCTION
registration pipeline (``core.spatial.registration``: SOR -> Mahalanobis ->
RANSAC coarse -> chi^2-gated ICP) to estimate that transform. Predeclared
gates: <=0.15 m translation error, <=0.5 degree rotation error, <=0.20 m
aligned RMSE measured on no-change control regions.

The aligned capture is fused and tiled through the same splat tiler as every
production asset and registered as a ``synthetic_fixture`` asset version —
which the release selector technically bars from non-fixture manifests.
Change hypotheses become ``spatial.observation_candidate`` rows whose
confidence derives from measured residual + coverage; ONLY a reviewed
acceptance appends a civic observation, and rejection/retraction stay
auditable.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.spatial.geodesy import enu_to_ecef, wgs84_to_ecef
from core.spatial.registration import (
    RegistrationReport,
    apply_rigid,
    mahalanobis_filter,
    register_capture,
    statistical_outlier_removal,
)
from core.spatial.schema import GaussianBatch
from core.spatial.splat_tiler import tile_batch
from openpali.domain.observations import (
    MilestoneLane,
    ObservationStatus,
    RecoveryObservation,
    SourceRecordRef,
    SubjectRef,
    SubjectType,
)
from openpali.domain.temporal import ExactDate
from openpali.ingestion.load import insert_observations
from openpali.spatial.registry import (
    add_relation,
    mark_ready,
    register_asset_version,
    version_id_from_hashes,
)
from openpali.storage.models import ObservationCandidate, ObservationRevision
from openpali.storage.objects import ObjectStore, SPATIAL_BUCKET

RECON_SOURCE = "fixture_reconstruction"
RECON_PROCESS_VERSION = "recon-fixture-v1"
RECON_SEED = 20250121

#: predeclared acceptance gates (MULTIMODAL-001) — committed before execution
GATE_MAX_TRANSLATION_ERROR_M = 0.15
GATE_MAX_ROTATION_ERROR_DEG = 0.5
GATE_MAX_ALIGNED_RMSE_M = 0.20

#: fixture anchor (synthetic; NOT a real parcel location claim)
FIXTURE_ORIGIN_LONLAT = (-118.52, 34.04)
FIXTURE_ORIGIN_ALT = 50.0
FIXTURE_PARCEL_APN = "9977000001"

#: withheld ground-truth displacement of view B (~1.5 m / 3 degrees)
TRUE_TRANSLATION = np.array([1.18, -0.86, 0.22])  # |t| = 1.476 m
TRUE_ROTATION_DEG = 3.0
TRUE_AXIS = np.array([0.12, -0.08, 0.99])


def _rotation_matrix(axis: np.ndarray, angle_deg: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = axis
    return np.array(
        [
            [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
            [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
            [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
        ]
    )


# ---------------------------------------------------------------------------
# scene generation
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FixtureScene:
    view_prior: np.ndarray  # (N,3) local ENU — reference epoch
    view_capture: np.ndarray  # (M,3) DISPLACED second epoch (withheld transform)
    truth_rotation: np.ndarray
    truth_translation: np.ndarray
    change_region: tuple[float, float, float, float]  # ENU xmin,ymin,xmax,ymax
    control_region: tuple[float, float, float, float]
    prior_nochange: np.ndarray  # prior points inside control (for aligned RMSE)


def _sample_box(rng: np.random.Generator, xmin, ymin, xmax, ymax, zmax, density) -> np.ndarray:
    """Point samples on a box's roof + walls (a crude structure scan)."""

    area_roof = (xmax - xmin) * (ymax - ymin)
    n_roof = max(int(area_roof * density), 8)
    roof = np.column_stack(
        [
            rng.uniform(xmin, xmax, n_roof),
            rng.uniform(ymin, ymax, n_roof),
            np.full(n_roof, zmax),
        ]
    )
    walls = []
    for (x0, y0, x1, y1) in (
        (xmin, ymin, xmax, ymin), (xmin, ymax, xmax, ymax),
        (xmin, ymin, xmin, ymax), (xmax, ymin, xmax, ymax),
    ):
        length = math.hypot(x1 - x0, y1 - y0)
        n_wall = max(int(length * zmax * density * 0.5), 4)
        t = rng.uniform(0, 1, n_wall)
        walls.append(
            np.column_stack(
                [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, rng.uniform(0, zmax, n_wall)]
            )
        )
    return np.vstack([roof, *walls])


def build_fixture_scene(seed: int = RECON_SEED) -> FixtureScene:
    rng = np.random.default_rng(seed)
    density = 14.0  # pts / m^2

    # sloped ground 60 x 60 m. The 8%/3% grade is realistic for the Palisades
    # hillside AND breaks the rotational symmetry of a flat plane — a flipped
    # hypothesis tilts the terrain the wrong way and loses RANSAC consensus.
    n_ground = int(60 * 60 * density * 0.35)
    gx = rng.uniform(-30, 30, n_ground)
    gy = rng.uniform(-30, 30, n_ground)
    ground = np.column_stack([gx, gy, 0.08 * gx + 0.03 * gy])

    def on_ground(box: np.ndarray) -> np.ndarray:
        box = box.copy()
        box[:, 2] += 0.08 * box[:, 0] + 0.03 * box[:, 1]
        return box

    # persistent structures (no change): deliberately ASYMMETRIC layout —
    # distinct footprints, heights, and positions with no 180-degree pairing
    keep_a = on_ground(_sample_box(rng, -24, -20, -12, -8, 5.5, density))
    keep_b = on_ground(_sample_box(rng, 2, 12, 26, 22, 2.8, density))
    keep_c = on_ground(_sample_box(rng, 16, -26, 26, -14, 9.0, density))
    # change region: structure present in the PRIOR epoch, removed in capture
    gone = on_ground(_sample_box(rng, -8, -24, 4, -12, 6.0, density))

    prior = np.vstack([ground, keep_a, keep_b, keep_c, gone])
    capture_true = np.vstack([ground, keep_a, keep_b, keep_c])  # removed

    def occlude(points: np.ndarray, azimuth_deg: float, width_deg: float) -> np.ndarray:
        ang = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
        gap = np.abs(((ang - azimuth_deg) + 180) % 360 - 180) < width_deg / 2
        return points[~gap]

    prior_v = occlude(prior, azimuth_deg=140.0, width_deg=40.0)
    capture_v = occlude(capture_true, azimuth_deg=-35.0, width_deg=40.0)

    prior_v = prior_v + rng.normal(0, 0.05, prior_v.shape)
    capture_v = capture_v + rng.normal(0, 0.08, capture_v.shape)

    # 4% outlier clutter in the capture (birds/vehicles/scan artifacts)
    n_out = int(len(capture_v) * 0.04)
    clutter = np.column_stack(
        [
            rng.uniform(-32, 32, n_out),
            rng.uniform(-32, 32, n_out),
            rng.uniform(0, 12, n_out),
        ]
    )
    capture_clean = capture_v.copy()
    capture_v = np.vstack([capture_v, clutter])
    rng.shuffle(capture_v, axis=0)

    rot = _rotation_matrix(TRUE_AXIS, TRUE_ROTATION_DEG)
    capture_displaced = capture_v @ rot.T + TRUE_TRANSLATION

    control = (-26.0, -22.0, -10.0, -6.0)  # around structure A: no change
    cx0, cy0, cx1, cy1 = control
    mask = (
        (prior_v[:, 0] >= cx0) & (prior_v[:, 0] <= cx1)
        & (prior_v[:, 1] >= cy0) & (prior_v[:, 1] <= cy1)
    )
    return FixtureScene(
        view_prior=prior_v,
        view_capture=capture_displaced,
        truth_rotation=rot,
        truth_translation=TRUE_TRANSLATION.copy(),
        change_region=(-8.0, -24.0, 4.0, -12.0),
        control_region=control,
        prior_nochange=prior_v[mask],
    )


# ---------------------------------------------------------------------------
# estimation + gates
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ReconstructionResult:
    report: RegistrationReport
    capture_filtered: np.ndarray  # the points production actually admits
    translation_error_m: float
    rotation_error_deg: float
    aligned_rmse_nochange_m: float
    gates: dict
    coverage_fraction: float
    occlusion: dict


def filter_capture(capture: np.ndarray) -> np.ndarray:
    """The same admission filtering register_capture applies internally: the
    fused asset and every quality measurement use ONLY admitted points."""

    keep = statistical_outlier_removal(capture)
    kept = capture[keep]
    return kept[mahalanobis_filter(kept)]


def run_reconstruction(scene: FixtureScene) -> ReconstructionResult:
    """PRODUCTION estimation of the withheld transform + predeclared gates."""

    report = register_capture(scene.view_capture, scene.view_prior, voxel=1.0,
                              seed=RECON_SEED)

    # error vs withheld truth: estimated transform must UNDO the displacement
    # (capture = true_rot @ x + true_t  =>  inverse = rotᵀ, -rotᵀ t)
    inv_rot = scene.truth_rotation.T
    inv_trans = -inv_rot @ scene.truth_translation
    t_err = float(np.linalg.norm(report.translation - inv_trans))
    rel = report.rotation @ inv_rot.T
    angle = math.degrees(math.acos(min(1.0, max(-1.0, (np.trace(rel) - 1) / 2))))

    # aligned RMSE on the no-change CONTROL region of the ADMITTED capture —
    # registration quality, never diluted (or inflated) by genuine scene
    # change, and never contaminated by clutter the pipeline rejects
    from scipy.spatial import cKDTree

    capture_filtered = filter_capture(scene.view_capture)
    aligned = apply_rigid(capture_filtered, report.rotation, report.translation)
    cx0, cy0, cx1, cy1 = scene.control_region
    in_control = (
        (aligned[:, 0] >= cx0) & (aligned[:, 0] <= cx1)
        & (aligned[:, 1] >= cy0) & (aligned[:, 1] <= cy1)
    )
    control_pts = aligned[in_control]
    tree = cKDTree(scene.prior_nochange)
    d, _ = tree.query(control_pts, k=1)
    rmse = float(np.sqrt(np.mean(d**2))) if len(control_pts) else float("inf")

    gates = {
        "translation_error_m": {
            "value": round(t_err, 4), "max": GATE_MAX_TRANSLATION_ERROR_M,
            "passed": t_err <= GATE_MAX_TRANSLATION_ERROR_M,
        },
        "rotation_error_deg": {
            "value": round(angle, 4), "max": GATE_MAX_ROTATION_ERROR_DEG,
            "passed": angle <= GATE_MAX_ROTATION_ERROR_DEG,
        },
        "aligned_rmse_nochange_m": {
            "value": round(rmse, 4), "max": GATE_MAX_ALIGNED_RMSE_M,
            "passed": rmse <= GATE_MAX_ALIGNED_RMSE_M,
        },
    }
    coverage = float(report.icp.inlier_fraction)
    occlusion = {
        "prior_occluded_wedge_deg": 40.0,
        "capture_occluded_wedge_deg": 40.0,
        "capture_outlier_fraction": 0.04,
        "points_after_filtering": report.n_after_mahalanobis,
    }
    return ReconstructionResult(
        report=report,
        capture_filtered=capture_filtered,
        translation_error_m=t_err,
        rotation_error_deg=angle,
        aligned_rmse_nochange_m=rmse,
        gates=gates,
        coverage_fraction=coverage,
        occlusion=occlusion,
    )


# ---------------------------------------------------------------------------
# fuse + tile + register (fixture asset; barred from non-fixture releases)
# ---------------------------------------------------------------------------


def _enu_to_ecef_batch(enu: np.ndarray) -> np.ndarray:
    lon0, lat0 = FIXTURE_ORIGIN_LONLAT
    origin = wgs84_to_ecef(
        np.array(lon0), np.array(lat0), np.array(FIXTURE_ORIGIN_ALT)
    )
    return enu_to_ecef(enu, origin, lon0, lat0)


def fuse_and_register_asset(
    session: Session,
    store: ObjectStore,
    scene: FixtureScene,
    result: ReconstructionResult,
) -> tuple[str, str]:
    """Fuse aligned capture + prior, tile with the production tiler, register."""

    aligned = apply_rigid(result.capture_filtered, result.report.rotation,
                          result.report.translation)
    fused_enu = np.vstack([scene.view_prior, aligned])
    epoch_prior = datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp()
    epoch_capture = datetime(2025, 7, 1, tzinfo=timezone.utc).timestamp()
    t_epoch = np.concatenate(
        [
            np.full(len(scene.view_prior), epoch_prior),
            np.full(len(aligned), epoch_capture),
        ]
    )
    batch = GaussianBatch.from_points(
        _enu_to_ecef_batch(fused_enu),
        t_epoch,
        FIXTURE_PARCEL_APN,
        kind="splats",
        source=RECON_SOURCE,
    )
    # give the raw points a small surfel footprint so tiles are renderable
    batch.scale[:] = 0.18
    batch.alpha[:] = 0.9

    content_sha = hashlib.sha256(fused_enu.tobytes()).hexdigest()
    version_id = version_id_from_hashes(content_sha, RECON_PROCESS_VERSION)
    asset_id = "recon-fixture-scene"

    with tempfile.TemporaryDirectory(prefix="recon-fixture-") as tmp:
        tmp_path = Path(tmp)
        tiling = tile_batch(batch, tmp_path, leaf_max=12000, max_depth=7)
        (tmp_path / "manifest.json").write_text(json.dumps({
            "asset_id": asset_id,
            "version_id": version_id,
            "synthetic": True,
            "gates": result.gates,
            "registration": {
                "rmse_m": result.report.rmse,
                "inlier_fraction": result.report.icp.inlier_fraction,
                "iterations": result.report.icp.iterations,
            },
        }, indent=1))
        shas = []
        n_bytes = 0
        for path in sorted(tmp_path.rglob("*")):
            if not path.is_file():
                continue
            body = path.read_bytes()
            sha = hashlib.sha256(body).hexdigest()
            rel = path.relative_to(tmp_path).as_posix()
            store.ensure_bucket(SPATIAL_BUCKET)
            store.put_content(
                SPATIAL_BUCKET, f"assets/{asset_id}/{version_id}/{rel}", body,
                sha256=sha,
            )
            shas.append(f"{rel}:{sha}")
            n_bytes += len(body)
        combined = hashlib.sha256("\n".join(shas).encode()).hexdigest()

    register_asset_version(
        session,
        asset_id=asset_id,
        version_id=version_id,
        subject_type="fixture",
        subject_id=FIXTURE_PARCEL_APN,
        asset_kind="surfel_tiles",
        vintage_slot="fixture_two_epoch",
        source_id=RECON_SOURCE,
        observation_kind="synthetic_fixture_observation",
        rights_state="synthetic_fixture",
        horizontal_crs="local ENU about synthetic anchor",
        vertical_datum="synthetic",
        units="meters",
        transform={
            "estimated_rotation": result.report.rotation.tolist(),
            "estimated_translation": result.report.translation.tolist(),
            "estimator": "SOR->Mahalanobis->RANSAC->gated-ICP (production)",
            "process_version": RECON_PROCESS_VERSION,
        },
        registration_residual_m=result.aligned_rmse_nochange_m,
        acquisition_start=datetime(2025, 6, 1, tzinfo=timezone.utc),
        acquisition_end=datetime(2025, 7, 1, tzinfo=timezone.utc),
        processed_at=datetime.now(timezone.utc),
        resolution_m=0.3,
        coverage={
            "tiles": tiling.n_nodes,
            "points": len(batch),
            "inlier_fraction": result.coverage_fraction,
        },
        quality={"content_units": len(batch), "gates": result.gates,
                 "occlusion": result.occlusion, "bytes": n_bytes},
        lineage=[{"kind": "synthetic_scene", "seed": RECON_SEED,
                  "generator": RECON_PROCESS_VERSION}],
        object_uri=f"s3://{SPATIAL_BUCKET}/assets/{asset_id}/{version_id}/manifest.json",
        object_sha256=combined,
        format_version="3dtiles-splat-v1",
    )
    mark_ready(session, asset_id, version_id)
    return asset_id, version_id


# ---------------------------------------------------------------------------
# probabilistic candidates + review state machine
# ---------------------------------------------------------------------------


def _region_wkt(region: tuple[float, float, float, float]) -> str:
    """ENU rectangle -> approximate WGS84 polygon about the fixture anchor."""

    lon0, lat0 = FIXTURE_ORIGIN_LONLAT
    m_per_deg_lat = 111_132.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    x0, y0, x1, y1 = region
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    ring = ", ".join(
        f"{lon0 + x / m_per_deg_lon:.7f} {lat0 + y / m_per_deg_lat:.7f}"
        for x, y in pts
    )
    return f"SRID=4326;POLYGON(({ring}))"


def reset_drill_state(session: Session) -> None:
    """Remove prior drill review-state so the drill is rerunnable.

    Candidates and drill-accepted observations are synthetic drill artifacts:
    the fixture asset is barred from representative releases and these
    observations belong to no snapshot membership or publication, so deleting
    them never touches release-qualified state. The fused fixture ASSET rows
    and objects are content-addressed get-or-create and survive — the fixture
    release manifest may pin them.
    """

    from sqlalchemy import text

    # candidates first: accepted candidates hold an FK to the observation
    session.execute(text(
        "DELETE FROM spatial.observation_candidate "
        "WHERE rights_state = 'synthetic_fixture'"
    ))
    session.execute(text(
        "DELETE FROM civic.observation_revision WHERE source_id = :src"
    ), {"src": RECON_SOURCE})
    session.execute(text(
        "DELETE FROM civic.recovery_observation WHERE source_id = :src"
    ), {"src": RECON_SOURCE})
    session.flush()


def propose_candidates(
    session: Session,
    scene: FixtureScene,
    result: ReconstructionResult,
    asset: tuple[str, str],
) -> list[str]:
    """Derive change/no-change hypotheses with residual/coverage-based
    confidence. Candidates NEVER write civic observations here."""

    aligned = apply_rigid(result.capture_filtered, result.report.rotation,
                          result.report.translation)

    def occupancy_above(points: np.ndarray, region, z_min=1.5) -> int:
        x0, y0, x1, y1 = region
        inside = (
            (points[:, 0] >= x0) & (points[:, 0] <= x1)
            & (points[:, 1] >= y0) & (points[:, 1] <= y1)
            & (points[:, 2] >= z_min)
        )
        return int(inside.sum())

    quality_factor = math.exp(
        -result.aligned_rmse_nochange_m / GATE_MAX_ALIGNED_RMSE_M
    )
    candidates: list[tuple[str, str, float, tuple]] = []

    prior_n = occupancy_above(scene.view_prior, scene.change_region)
    now_n = occupancy_above(aligned, scene.change_region)
    removal_evidence = max(0.0, 1.0 - now_n / max(prior_n, 1))
    conf_change = min(0.99, removal_evidence * result.coverage_fraction * quality_factor)
    candidates.append(
        ("structure_removed_between_epochs", "physical_structure_absent",
         conf_change, scene.change_region))

    prior_c = occupancy_above(scene.view_prior, scene.control_region)
    now_c = occupancy_above(aligned, scene.control_region)
    persistence = min(now_c / max(prior_c, 1), 1.0)
    conf_control = min(0.99, persistence * result.coverage_fraction * quality_factor)
    candidates.append(
        ("structure_persists_between_epochs", "physical_structure_present",
         conf_control, scene.control_region))

    ids: list[str] = []
    for hypothesis, event_type, confidence, region in candidates:
        candidate_id = "cand-" + hashlib.sha256(
            f"{asset[0]}:{asset[1]}:{hypothesis}".encode()
        ).hexdigest()[:20]
        existing = session.execute(
            select(ObservationCandidate).where(
                ObservationCandidate.candidate_id == candidate_id
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ObservationCandidate(
                    candidate_id=candidate_id,
                    proposing_run_id=None,
                    model_version=RECON_PROCESS_VERSION,
                    asset_id=asset[0],
                    asset_version_id=asset[1],
                    subject_type="parcel",
                    subject_id=FIXTURE_PARCEL_APN,
                    region=_region_wkt(region),
                    hypothesis=hypothesis,
                    proposed_event_type=event_type,
                    proposed_occurred={
                        "kind": "interval",
                        "earliest": "2025-06-01",
                        "latest": "2025-07-01",
                        "basis": "between the two fixture capture epochs",
                    },
                    confidence=confidence,
                    confidence_method=(
                        "occupancy-delta x ICP inlier coverage x "
                        "exp(-rmse/gate) [measured residual, not asserted]"
                    ),
                    coverage_fraction=result.coverage_fraction,
                    occlusion=result.occlusion,
                    quality=result.gates,
                    registration_residual_m=result.aligned_rmse_nochange_m,
                    process_version=RECON_PROCESS_VERSION,
                    rights_state="synthetic_fixture",
                    privacy_state="synthetic_no_privacy_content",
                    review_state="pending",
                )
            )
        ids.append(candidate_id)
    session.flush()
    return ids


class CandidateReviewError(Exception):
    pass


def review_candidate(
    session: Session,
    candidate_id: str,
    decision: str,
    *,
    reviewer: str,
    reason: str,
) -> str | None:
    """The ONLY path from candidate to civic observation.

    accepted  -> appends ONE civic observation (returns its id)
    rejected  -> terminal, auditable, no observation
    retracted -> only from accepted; appends an ObservationRevision
    """

    candidate = session.execute(
        select(ObservationCandidate).where(
            ObservationCandidate.candidate_id == candidate_id
        )
    ).scalar_one()

    if decision == "accepted":
        if candidate.review_state != "pending":
            raise CandidateReviewError(
                f"cannot accept from state {candidate.review_state}"
            )
        occurred = candidate.proposed_occurred
        from openpali.domain.temporal import DateInterval
        from datetime import date as _date

        observation = RecoveryObservation(
            subject=SubjectRef(SubjectType.PARCEL, candidate.subject_id),
            lane=MilestoneLane.CONSTRUCTION,
            event_type=candidate.proposed_event_type,
            status=ObservationStatus.OBSERVED,
            occurred=DateInterval(
                _date.fromisoformat(occurred["earliest"]),
                _date.fromisoformat(occurred["latest"]),
            ),
            observed_at=datetime.now(timezone.utc),
            source_record=SourceRecordRef(RECON_SOURCE, candidate.candidate_id),
            policy_version=RECON_PROCESS_VERSION,
            label=(
                f"reviewed reconstruction evidence: {candidate.hypothesis} "
                f"(confidence {candidate.confidence:.2f}, "
                f"residual {candidate.registration_residual_m:.3f} m)"
            ),
            detail=(
                ("candidate_id", candidate.candidate_id),
                ("confidence_method", candidate.confidence_method or ""),
                ("reviewer", reviewer),
            ),
        )
        insert_observations(session, [observation], record_version=None)
        candidate.review_state = "accepted"
        candidate.reviewer = reviewer
        candidate.review_reason = reason
        candidate.reviewed_at = datetime.now(timezone.utc)
        candidate.accepted_observation_id = observation.observation_id
        session.flush()
        return observation.observation_id

    if decision == "rejected":
        if candidate.review_state != "pending":
            raise CandidateReviewError(
                f"cannot reject from state {candidate.review_state}"
            )
        candidate.review_state = "rejected"
        candidate.reviewer = reviewer
        candidate.review_reason = reason
        candidate.reviewed_at = datetime.now(timezone.utc)
        session.flush()
        return None

    if decision == "retracted":
        if candidate.review_state != "accepted" or not candidate.accepted_observation_id:
            raise CandidateReviewError("only an accepted candidate can be retracted")
        revision_id = "rev-recon-" + hashlib.sha256(
            candidate.accepted_observation_id.encode()
        ).hexdigest()[:16]
        if session.execute(
            select(ObservationRevision).where(
                ObservationRevision.revision_id == revision_id
            )
        ).scalar_one_or_none() is None:
            session.add(
                ObservationRevision(
                    revision_id=revision_id,
                    target_observation_id=candidate.accepted_observation_id,
                    revision_type="retraction",
                    reason=reason,
                    source_id=RECON_SOURCE,
                    revised_at=datetime.now(timezone.utc),
                )
            )
        candidate.review_state = "retracted"
        candidate.reviewer = reviewer
        candidate.review_reason = reason
        candidate.reviewed_at = datetime.now(timezone.utc)
        session.flush()
        return None

    raise CandidateReviewError(f"unknown decision: {decision}")


# ---------------------------------------------------------------------------
# GPU worker boundary (typed refusal without hardware)
# ---------------------------------------------------------------------------


def gpu_probe() -> dict:
    """Production entrypoint for the optional GPU reconstruction worker.

    Without qualifying hardware it returns a TYPED unsupported_hardware
    result — never a crash, never a silent CPU fallback pretending to be the
    GPU path.
    """

    import shutil
    from pathlib import Path as _Path

    detail: dict = {}
    nvidia_devices = sorted(str(p) for p in _Path("/dev").glob("nvidia*"))
    detail["nvidia_devices"] = nvidia_devices
    detail["nvidia_smi"] = shutil.which("nvidia-smi")
    if nvidia_devices and detail["nvidia_smi"]:
        return {"status": "supported", "backend": "cuda", "detail": detail}
    return {
        "status": "unsupported_hardware",
        "requirement": "NVIDIA GPU with driver (nvidia-smi + /dev/nvidia*)",
        "behavior": (
            "GPU reconstruction jobs refuse with this typed result; the CPU "
            "fixture path remains the executable proof of the pipeline"
        ),
        "detail": detail,
    }
