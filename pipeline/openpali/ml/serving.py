"""Gated batch serving (ML-003).

Predictions are produced as an immutable batch artifact per snapshot and
written to ``ml.prediction`` under an ``ml.prediction_set`` row that pins
model/dataset/snapshot/target. The API serves those stored values; nothing is
trained or computed per request. When no reviewed champion is compatible, a
TYPED insufficiency prediction set is recorded instead — publication never
blocks on a failed or gated challenger.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from openpali.ml.dataset import HORIZON_DAYS, load_dataset_rows
from openpali.ml.experiments import INSUFFICIENT, reload_model
from openpali.storage.models import (
    CivicSnapshot,
    DatasetVersion,
    ExperimentRun,
    ModelVersion,
    Prediction,
    PredictionSet,
    PromotionDecision,
)
from openpali.storage.objects import ObjectStore

TARGET_SIGNATURE = "p_issued_180d@submission-v1"

#: features derivable from the application row's own origin — available for
#: every row by construction, independent of the parcel-history gate
ORIGIN_DERIVED_FEATURES = {"submission_days_since_fire", "submission_month"}


def _snapshot_is_fixture(session: Session, snapshot_id: str) -> bool:
    snapshot = session.execute(
        select(CivicSnapshot).where(CivicSnapshot.snapshot_id == snapshot_id)
    ).scalar_one()
    return all(str(r).startswith("run-fixture-") for r in snapshot.input_runs)


def _champion_domain_compatible(
    session: Session, champion: ModelVersion, snapshot_id: str
) -> bool:
    """A fixture-trained champion may never serve civic data (and vice
    versa): synthetic lineage cannot become a public fact."""

    experiment = session.execute(
        select(ExperimentRun).where(
            ExperimentRun.experiment_run_id == champion.experiment_run_id
        )
    ).scalar_one()
    dataset = session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == experiment.dataset_id)
    ).scalar_one()
    return _snapshot_is_fixture(session, dataset.snapshot_id) == _snapshot_is_fixture(
        session, snapshot_id
    )


@dataclass(slots=True)
class ServingResult:
    prediction_set_id: str
    status: str
    rows: int
    model_id: str | None
    insufficiency_reason: str | None


def current_champion(session: Session) -> ModelVersion | None:
    """The champion is the model named by the LATEST promotion decision with
    decision='promoted' (append-only history; champion state never mutates a
    model row)."""

    decision = session.execute(
        select(PromotionDecision)
        .where(PromotionDecision.decision == "promoted")
        .order_by(PromotionDecision.decided_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if decision is None:
        return None
    return session.execute(
        select(ModelVersion).where(ModelVersion.model_id == decision.proposed_model_id)
    ).scalar_one_or_none()


def build_prediction_set(
    session: Session,
    store: ObjectStore,
    snapshot_id: str,
    dataset_id: str,
) -> ServingResult:
    dataset = session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
    ).scalar_one()
    gate_passed = bool((dataset.sufficiency or {}).get("gate", {}).get("passed"))
    champion = current_champion(session)

    # domain gate: an incompatible (e.g. fixture-trained) champion is no
    # champion at all for this snapshot
    if champion is not None and not _champion_domain_compatible(
        session, champion, snapshot_id
    ):
        champion = None

    # feature-availability gate (methods review): the FULL history gate only
    # blocks serving when the champion actually consumes gated (parcel)
    # features. Origin-derived covariates are available for every row by
    # construction, so a compatible reviewed champion using only those may
    # serve even when parcel-history coverage dips.
    features_ok = True
    if champion is not None:
        inputs = set((champion.signature or {}).get("inputs") or [])
        features_ok = inputs <= ORIGIN_DERIVED_FEATURES or gate_passed

    set_id = "pset-" + hashlib.sha256(
        f"{snapshot_id}:{dataset_id}:{champion.model_id if champion else 'none'}".encode()
    ).hexdigest()[:20]
    existing = session.execute(
        select(PredictionSet).where(PredictionSet.prediction_set_id == set_id)
    ).scalar_one_or_none()
    if existing is not None:
        return ServingResult(
            prediction_set_id=set_id,
            status=existing.status,
            rows=existing.row_count,
            model_id=existing.model_id,
            insufficiency_reason=existing.insufficiency_reason,
        )

    if champion is None or not features_ok:
        reason = INSUFFICIENT if not gate_passed else "no_reviewed_champion"
        session.execute(
            pg_insert(PredictionSet)
            .values(
                prediction_set_id=set_id,
                model_id=None,
                insufficiency_reason=reason,
                dataset_id=dataset_id,
                snapshot_id=snapshot_id,
                target_signature=TARGET_SIGNATURE,
                row_count=0,
                status="insufficient",
            )
            .on_conflict_do_nothing(index_elements=["prediction_set_id"])
        )
        session.flush()
        return ServingResult(
            prediction_set_id=set_id, status="insufficient", rows=0,
            model_id=None, insufficiency_reason=reason,
        )

    model = reload_model(store, champion)  # fresh-process deserialization
    rows = load_dataset_rows(store, dataset)
    training_range = (champion.signature or {}).get("training_range") or {}
    generated_at = datetime.now(timezone.utc)
    prediction_rows: list[dict] = []
    for row in rows:
        origin = date.fromisoformat(row["origin_date"])
        # After the horizon has elapsed, serving reports observed outcome or
        # current status — never a recycled origin probability (ML-001).
        followup_complete = row["duration_days"] > HORIZON_DAYS or (
            row["event_issued"] == 1 and row["duration_days"] <= HORIZON_DAYS
        )
        if followup_complete:
            continue
        estimate = 1.0 - model.survival(row, HORIZON_DAYS)
        # extrapolation disclosure: covariates beyond the champion's training
        # range are marked — an extrapolated estimate never masquerades as an
        # interpolated one (methods review)
        extrapolated = [
            feature
            for feature, bounds in training_range.items()
            if feature in row
            and not (bounds[0] <= float(row[feature]) <= bounds[1])
        ]
        basis = {
            "origin_date": row["origin_date"],
            "estimated_at": "submission",
            "note": "estimated at submission, not a current ETA",
            "features": {"submission_days_since_fire": row["submission_days_since_fire"]},
        }
        if extrapolated:
            basis["extrapolated_features"] = extrapolated
            basis["note"] += (
                "; covariates outside the champion's training range — "
                "treat with extra caution"
            )
        prediction_rows.append(
            {
                "prediction_set_id": set_id,
                "subject_type": "permit_application",
                "subject_id": row["application_id"],
                "target": TARGET_SIGNATURE,
                "horizon_days": HORIZON_DAYS,
                "estimate": float(estimate),
                "interval_low": None,
                "interval_high": None,
                "basis": basis,
                "generated_at": generated_at,
            }
        )
    session.execute(
        pg_insert(PredictionSet)
        .values(
            prediction_set_id=set_id,
            model_id=champion.model_id,
            insufficiency_reason=None,
            dataset_id=dataset_id,
            snapshot_id=snapshot_id,
            target_signature=TARGET_SIGNATURE,
            row_count=len(prediction_rows),
            status="served",
        )
        .on_conflict_do_nothing(index_elements=["prediction_set_id"])
    )
    for start in range(0, len(prediction_rows), 500):
        session.execute(
            pg_insert(Prediction)
            .values(prediction_rows[start:start + 500])
            .on_conflict_do_nothing(
                index_elements=["prediction_set_id", "subject_type", "subject_id", "target"]
            )
        )
    session.flush()
    return ServingResult(
        prediction_set_id=set_id, status="served", rows=len(prediction_rows),
        model_id=champion.model_id, insufficiency_reason=None,
    )
