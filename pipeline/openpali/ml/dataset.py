"""Point-in-time learning dataset builder (ML-001).

Fixed first target (frozen in the architecture blueprint): for a qualifying
fire-rebuild application at its documented submission time, censoring-aware
time to first issuance of that same application and probability of issuance
within 180 days. One risk unit = one qualifying application; property-level
aggregation never happens silently.

Point-in-time discipline: a feature value enters a row ONLY when its source
observation was first acquired (``observed_at``) at or before that row's
origin. Filesystem dates, current-row presence, retrospective status, and
occurrence/outcome dates never establish historical availability. The
representative ledger — acquired in one burst — therefore fails the
precommitted history gate below and the challenger emits
``INSUFFICIENT_POINT_IN_TIME_HISTORY``; the naive and censoring-aware
baselines remain valid because they use outcome data only.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from openpali.domain.conflicts import CONFLICT_SOURCE_ID
from openpali.identity.ids import canonical_json, dataset_id as derive_dataset_id
from openpali.storage.models import (
    CivicSnapshot,
    DatasetVersion,
    RecoveryObservationRow,
    SnapshotMember,
)
from openpali.storage.objects import ARTIFACT_BUCKET, ObjectStore

TARGET_POLICY = "issuance-180d-v1"
COHORT_POLICY = "qualifying-rebuild-v1"
# v2: parcel-context availability is source-agnostic (any non-derived parcel
# observation establishes point-in-time availability, not only county_base)
FEATURE_SCHEMA_VERSION = "features-v2"
LABEL_POLICY_VERSION = "labels-v1"
# v2 (methods review): folds are CONTIGUOUS CHRONOLOGICAL blocks of the
# origin-sorted training rows. v1 interleaved rows (index % k) — a stratified
# split mislabeled rolling-origin, whose evaluation rows had temporal
# neighbors on both sides in the fit set (optimistic for calendar covariates).
SPLIT_POLICY = "rolling-origin-v2"
HORIZON_DAYS = 180

#: Competing-event policy, PREDECLARED: the public LADBS layer exposes no
#: withdrawal/cancellation/expiration status today, so those events are
#: treated as right-censoring until a documented status field exposes them.
#: When such a field appears it becomes a competing event and this policy
#: version bumps.
COMPETING_EVENT_POLICY = "withdrawal-as-censoring-v1"

#: Precommitted point-in-time-history gate (methods-review audited): fitting a
#: covariate challenger requires that the ledger demonstrates real historical
#: feature availability — at least MIN_DISTINCT_DATES distinct acquisition
#: dates spanning at least MIN_SPAN_DAYS, and at least MIN_COVERAGE of
#: applications having >=1 feature observation observed at or before their
#: origin. Committed BEFORE any representative evaluation (ML-002).
GATE_MIN_DISTINCT_DATES = 3
GATE_MIN_SPAN_DAYS = 60
GATE_MIN_ORIGIN_COVERAGE = 0.5

#: Final untouched evaluation block: the last N days of origins are excluded
#: from every tuning loop and used exactly once (ML-001/ML-002).
FINAL_BLOCK_DAYS = 60
ROLLING_FOLDS = 3


@dataclass(slots=True)
class DatasetBuildResult:
    dataset_id: str
    row_count: int
    eligible: int
    excluded_missing_submission: int
    events: int
    censored: int
    availability: dict
    gate: dict
    object_uri: str | None
    object_sha256: str | None
    created: bool


def _member_observations(session: Session, snapshot_id: str) -> list[RecoveryObservationRow]:
    member_ids = select(SnapshotMember.member_id).where(
        SnapshotMember.snapshot_id == snapshot_id,
        SnapshotMember.member_type == "observation",
    )
    return list(
        session.execute(
            select(RecoveryObservationRow).where(
                RecoveryObservationRow.observation_id.in_(member_ids)
            )
        ).scalars()
    )


def _parcel_for(observation: RecoveryObservationRow) -> str | None:
    for related in observation.related_subjects:
        if related.get("type") == "parcel":
            return related.get("id")
    return None


def build_dataset(
    session: Session,
    store: ObjectStore,
    snapshot_id: str,
) -> DatasetBuildResult:
    """Create the immutable dataset for one snapshot. Idempotent by content."""

    snapshot = session.execute(
        select(CivicSnapshot).where(CivicSnapshot.snapshot_id == snapshot_id)
    ).scalar_one()
    cutoff: datetime = snapshot.cutoff
    cutoff_date: date = cutoff.date()

    dataset_identifier = derive_dataset_id(
        snapshot_id, COHORT_POLICY, TARGET_POLICY,
        f"{FEATURE_SCHEMA_VERSION}+{SPLIT_POLICY}",  # split semantics are identity
        cutoff.isoformat(),
    )
    existing = session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_identifier)
    ).scalar_one_or_none()

    observations = _member_observations(session, snapshot_id)

    # --- risk set: one row per qualifying application -----------------------
    applications: dict[str, dict] = {}
    for row in observations:
        if row.subject_type != "permit_application":
            continue
        entry = applications.setdefault(row.subject_id, {"application_id": row.subject_id})
        if row.event_type == "rebuild_application_submitted":
            entry["submitted_kind"] = row.occurred_kind
            entry["submission_observed_at"] = row.observed_at
            if row.occurred_kind == "exact":
                entry["submitted"] = row.occurred_earliest
            entry["parcel_apn"] = _parcel_for(row) or entry.get("parcel_apn")
        elif row.event_type == "rebuild_permit_issued" and row.occurred_kind == "exact":
            entry["issued"] = row.occurred_earliest

    # Parcel-context observations establish feature availability. Any SOURCE
    # observation on the parcel counts (derived conflict markers do not) —
    # the point-in-time discipline lives in the observed_at comparison below,
    # not in which feed asserted the parcel.
    parcel_observed_at: dict[str, datetime] = {}
    for row in observations:
        if (
            row.subject_type == "parcel"
            and row.source_id != CONFLICT_SOURCE_ID
        ):
            when = parcel_observed_at.get(row.subject_id)
            if when is None or row.observed_at < when:
                parcel_observed_at[row.subject_id] = row.observed_at

    rows: list[dict] = []
    excluded_missing_submission = 0
    feature_available_count = 0
    for entry in applications.values():
        if "submitted_kind" not in entry:
            continue  # issuance-only records are not eligible risk units
        submitted = entry.get("submitted")
        if submitted is None:
            excluded_missing_submission += 1
            continue
        issued = entry.get("issued")
        event = int(issued is not None and issued >= submitted)
        duration = (
            (issued - submitted).days if event else max((cutoff_date - submitted).days, 0)
        )
        origin_dt = datetime(
            submitted.year, submitted.month, submitted.day, tzinfo=cutoff.tzinfo
        )
        apn = entry.get("parcel_apn")
        # POINT-IN-TIME availability: parcel features usable only when the
        # parcel observation predates the origin.
        parcel_available = bool(
            apn and apn in parcel_observed_at and parcel_observed_at[apn] <= origin_dt
        )
        if parcel_available:
            feature_available_count += 1
        rows.append(
            {
                "application_id": entry["application_id"],
                "parcel_apn": apn,
                "origin_date": submitted.isoformat(),
                "duration_days": duration,
                "event_issued": event,
                "horizon_days": HORIZON_DAYS,
                "submission_month": submitted.month,
                "submission_days_since_fire": (submitted - date(2025, 1, 7)).days,
                "parcel_features_available_at_origin": parcel_available,
                "feature_missing_parcel": not parcel_available,
            }
        )

    rows.sort(key=lambda r: (r["origin_date"], r["application_id"]))

    # --- deterministic rolling-origin splits + untouched final block --------
    # Training rows (already origin-sorted) are cut into ROLLING_FOLDS
    # contiguous chronological blocks: fold_0 earliest ... fold_{k-1} latest.
    # Forward evaluation = fit on earlier blocks, evaluate on a later one.
    final_block_start = cutoff_date - timedelta(days=FINAL_BLOCK_DAYS)
    train_rows = [r for r in rows if date.fromisoformat(r["origin_date"]) < final_block_start]
    n_train = len(train_rows)
    for index, row in enumerate(train_rows):
        block = min(index * ROLLING_FOLDS // max(n_train, 1), ROLLING_FOLDS - 1)
        row["split"] = f"fold_{block}"
    for row in rows:
        if date.fromisoformat(row["origin_date"]) >= final_block_start:
            row["split"] = "final_holdout"

    # --- precommitted point-in-time history gate -----------------------------
    distinct_dates = sorted(
        {when.date() for when in parcel_observed_at.values()}
        | {
            e["submission_observed_at"].date()
            for e in applications.values()
            if "submission_observed_at" in e
        }
    )
    span_days = (distinct_dates[-1] - distinct_dates[0]).days if len(distinct_dates) > 1 else 0
    coverage = feature_available_count / len(rows) if rows else 0.0
    gate = {
        "policy": "point-in-time-history-gate-v1",
        "distinct_acquisition_dates": len(distinct_dates),
        "span_days": span_days,
        "origin_feature_coverage": round(coverage, 4),
        "requires": {
            "min_distinct_dates": GATE_MIN_DISTINCT_DATES,
            "min_span_days": GATE_MIN_SPAN_DAYS,
            "min_origin_coverage": GATE_MIN_ORIGIN_COVERAGE,
        },
        "passed": (
            len(distinct_dates) >= GATE_MIN_DISTINCT_DATES
            and span_days >= GATE_MIN_SPAN_DAYS
            and coverage >= GATE_MIN_ORIGIN_COVERAGE
        ),
    }

    availability = {
        "applications_total": len(applications),
        "eligible_with_exact_submission": len(rows),
        "excluded_missing_submission_date": excluded_missing_submission,
        "parcel_feature_available_at_origin": feature_available_count,
        "late_entry_note": (
            "every observation in this ledger carries its true first-acquisition "
            "time; features whose observations postdate an application's origin "
            "are withheld from that row"
        ),
    }

    if existing is not None:
        return DatasetBuildResult(
            dataset_id=dataset_identifier,
            row_count=existing.row_count or 0,
            eligible=len(rows),
            excluded_missing_submission=excluded_missing_submission,
            events=sum(r["event_issued"] for r in rows),
            censored=sum(1 - r["event_issued"] for r in rows),
            availability=availability,
            gate=gate,
            object_uri=existing.object_uri,
            object_sha256=existing.object_sha256,
            created=False,
        )

    # --- immutable parquet + data card ---------------------------------------
    object_uri = object_sha = None
    if rows:
        table = pa.Table.from_pylist(rows)
        sink = io.BytesIO()
        pq.write_table(table, sink)
        payload = sink.getvalue()
        object_sha = hashlib.sha256(payload).hexdigest()
        key = f"features/{dataset_identifier}/{FEATURE_SCHEMA_VERSION}/dataset.parquet"
        store.ensure_bucket(ARTIFACT_BUCKET)
        stored = store.put_content(ARTIFACT_BUCKET, key, payload, sha256=object_sha)
        object_uri = stored.uri

        data_card = {
            "dataset_id": dataset_identifier,
            "snapshot_id": snapshot_id,
            "cutoff": cutoff.isoformat(),
            "target": TARGET_POLICY,
            "cohort": COHORT_POLICY,
            "competing_event_policy": COMPETING_EVENT_POLICY,
            "unit": "one qualifying fire-rebuild permit application",
            "origin": "documented submission date (exact-dated only; exclusions counted)",
            "event": "first issuance of the same application",
            "censoring": "right-censored at snapshot cutoff",
            "horizon_days": HORIZON_DAYS,
            "rows": len(rows),
            "events": sum(r["event_issued"] for r in rows),
            "availability": availability,
            "gate": gate,
            "split_policy": {
                "name": SPLIT_POLICY,
                "rolling_folds": ROLLING_FOLDS,
                "final_holdout_days": FINAL_BLOCK_DAYS,
                "note": "final_holdout is never exposed to iterative tuning",
            },
            "excluded_fields": [
                "address", "raw APN text beyond join key", "post-cutoff status",
                "source-provided days-to-outcome",
            ],
        }
        card_bytes = canonical_json(data_card).encode()
        store.put_content(
            ARTIFACT_BUCKET,
            f"features/{dataset_identifier}/{FEATURE_SCHEMA_VERSION}/data-card.json",
            card_bytes,
            sha256=hashlib.sha256(card_bytes).hexdigest(),
            media_type="application/json",
        )

    session.execute(
        pg_insert(DatasetVersion)
        .values(
            dataset_id=dataset_identifier,
            snapshot_id=snapshot_id,
            cutoff=cutoff,
            cohort_policy=COHORT_POLICY,
            target_policy=TARGET_POLICY,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            label_policy_version=LABEL_POLICY_VERSION,
            split_policy=SPLIT_POLICY,
            object_uri=object_uri,
            object_sha256=object_sha,
            row_count=len(rows),
            leakage_audit={
                "current_status_fields": "never read",
                "post_cutoff_observations": "excluded by snapshot membership",
                "later_milestone_dates": "labels only, never features",
                "source_days_to_outcome": "excluded",
            },
            sufficiency={"availability": availability, "gate": gate},
        )
        .on_conflict_do_nothing(index_elements=["dataset_id"])
    )
    session.flush()

    return DatasetBuildResult(
        dataset_id=dataset_identifier,
        row_count=len(rows),
        eligible=len(rows),
        excluded_missing_submission=excluded_missing_submission,
        events=sum(r["event_issued"] for r in rows),
        censored=sum(1 - r["event_issued"] for r in rows),
        availability=availability,
        gate=gate,
        object_uri=object_uri,
        object_sha256=object_sha,
        created=True,
    )


def load_dataset_rows(store: ObjectStore, dataset: DatasetVersion) -> list[dict]:
    """Re-read the immutable parquet artifact (hash-verified)."""

    if not dataset.object_uri or not dataset.object_sha256:
        return []
    key = dataset.object_uri.split("/", 3)[3]
    payload = store.get_verified(ARTIFACT_BUCKET, key, dataset.object_sha256)
    table = pq.read_table(io.BytesIO(payload))
    return table.to_pylist()
