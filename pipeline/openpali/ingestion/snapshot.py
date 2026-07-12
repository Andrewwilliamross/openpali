"""Snapshot builder: immutable cutoff + membership + lane projections.

Point-in-time rule (DATA-002): a snapshot with cutoff T contains only
observations first observed at or before T; retractions revised at or before T
remove their targets from the ACTIVE set while the audit trail remains.
Rebuilding the same snapshot (same inputs, policies, cutoff) is a no-op.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from openpali.domain.conflicts import detect_conflicts
from openpali.domain.lanes import (
    PROJECTION_POLICY_VERSION,
    lane_signal_map,
    milestone_facts,
    project_lanes,
)
from openpali.domain.observations import (
    MilestoneLane,
    ObservationStatus,
    RecoveryObservation,
    SourceRecordRef,
    SubjectRef,
    SubjectType,
)
from openpali.domain.policy import QUALIFYING_REBUILD_POLICY_VERSION
from openpali.domain.taxonomy import TAXONOMY_VERSION
from openpali.domain.temporal import (
    DateInterval,
    ExactDate,
    UnknownDate,
)
from openpali.identity.ids import snapshot_id_from_inputs
from openpali.ingestion.load import insert_observations
from openpali.storage.models import (
    AcquisitionRun,
    CivicSnapshot,
    ObservationRevision,
    ParcelVersion,
    RecoveryObservationRow,
    SnapshotMember,
    SnapshotPropertyState,
)

SNAPSHOT_SCHEMA_VERSION = "civic-v1"


def policy_versions() -> dict[str, str]:
    return {
        "taxonomy": TAXONOMY_VERSION,
        "projection": PROJECTION_POLICY_VERSION,
        "qualifying_rebuild": QUALIFYING_REBUILD_POLICY_VERSION,
        "snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
    }


@dataclass(slots=True)
class SnapshotResult:
    snapshot_id: str
    created: bool
    properties: int
    observations: int
    conflicts: int


def _row_to_domain(row: RecoveryObservationRow) -> RecoveryObservation:
    if row.occurred_kind == "exact":
        occurred = ExactDate(row.occurred_earliest)
    elif row.occurred_kind == "interval":
        occurred = DateInterval(row.occurred_earliest, row.occurred_latest)
    else:
        occurred = UnknownDate()
    return RecoveryObservation(
        subject=SubjectRef(SubjectType(row.subject_type), row.subject_id),
        lane=MilestoneLane(row.lane) if row.lane else None,
        event_type=row.event_type,
        status=ObservationStatus(row.status),
        occurred=occurred,
        observed_at=row.observed_at,
        source_record=SourceRecordRef(row.source_id, row.subject_id),
        policy_version=row.policy_version,
        label=row.label,
        related_subjects=tuple(
            SubjectRef(SubjectType(s["type"]), s["id"]) for s in row.related_subjects
        ),
        detail=tuple((k, str(v)) for k, v in (row.detail or {}).items()),
    )


def build_snapshot(
    session: Session,
    input_run_ids: list[str],
    cutoff: datetime,
    *,
    code_commit: str | None = None,
) -> SnapshotResult:
    policies = policy_versions()
    snapshot_id = snapshot_id_from_inputs(
        input_run_ids, policies, cutoff.isoformat(), SNAPSHOT_SCHEMA_VERSION
    )
    existing = session.execute(
        select(CivicSnapshot).where(CivicSnapshot.snapshot_id == snapshot_id)
    ).scalar_one_or_none()
    if existing is not None and existing.status in {"built", "published"}:
        properties = session.execute(
            select(SnapshotPropertyState)
            .where(SnapshotPropertyState.snapshot_id == snapshot_id)
        ).scalars()
        count = sum(1 for _ in properties)
        return SnapshotResult(snapshot_id, created=False, properties=count,
                              observations=0, conflicts=0)

    input_hash = hashlib.sha256("\n".join(sorted(input_run_ids)).encode()).hexdigest()
    snapshot = existing or CivicSnapshot(
        snapshot_id=snapshot_id,
        cutoff=cutoff,
        code_commit=code_commit,
        input_runs=sorted(input_run_ids),
        input_runs_sha256=input_hash,
        policy_versions=policies,
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        status="building",
    )
    if existing is None:
        session.add(snapshot)
        session.flush()

    # Sources covered by the input runs bound the observation universe.
    source_ids = set(
        session.execute(
            select(AcquisitionRun.source_id).where(
                AcquisitionRun.run_id.in_(input_run_ids)
            )
        ).scalars()
    )

    observation_rows = list(
        session.execute(
            select(RecoveryObservationRow).where(
                RecoveryObservationRow.source_id.in_(source_ids),
                RecoveryObservationRow.observed_at <= cutoff,
            )
        ).scalars()
    )
    retracted_ids = set(
        session.execute(
            select(ObservationRevision.target_observation_id).where(
                ObservationRevision.revision_type == "retraction",
                ObservationRevision.revised_at <= cutoff,
            )
        ).scalars()
    )

    active_rows = [r for r in observation_rows if r.observation_id not in retracted_ids]
    # IMPORTANT: membership always references the STORED observation_id.
    # Domain objects are reconstructed only for projection/conflict logic —
    # their recomputed IDs can differ from stored IDs (e.g. the discriminator
    # is part of the deterministic ID but not a persisted column).
    pairs: list[tuple[str, RecoveryObservation]] = [
        (r.observation_id, _row_to_domain(r)) for r in active_rows
    ]

    # Same-snapshot contradiction detection; derived conflicts are persisted
    # (deterministic IDs; detection time = cutoff) and join the membership.
    conflicts = detect_conflicts([obs for _, obs in pairs], detected_at=cutoff)
    if conflicts:
        insert_observations(session, conflicts, record_version=None)
    pairs.extend((conflict.observation_id, conflict) for conflict in conflicts)

    # Group observations by parcel APN (subject or related parcel).
    by_apn: dict[str, list[tuple[str, RecoveryObservation]]] = {}
    for stored_id, observation in pairs:
        apns = set()
        if observation.subject.type is SubjectType.PARCEL:
            apns.add(observation.subject.id)
        for ref in observation.related_subjects:
            if ref.type is SubjectType.PARCEL:
                apns.add(ref.id)
        for apn in apns:
            by_apn.setdefault(apn, []).append((stored_id, observation))

    # Current parcel versions as of the cutoff.
    parcel_rows = list(
        session.execute(
            select(ParcelVersion).where(
                ParcelVersion.observed_from <= cutoff,
            )
        ).scalars()
    )
    latest_parcel: dict[str, ParcelVersion] = {}
    for parcel in parcel_rows:
        if parcel.observed_to is not None and parcel.observed_to <= cutoff:
            continue
        best = latest_parcel.get(parcel.apn)
        if best is None or parcel.observed_from > best.observed_from:
            latest_parcel[parcel.apn] = parcel

    members: list[dict] = []
    state_rows: list[dict] = []
    for apn, parcel in latest_parcel.items():
        parcel_pairs = by_apn.get(apn, [])
        observations = [obs for _, obs in parcel_pairs]
        state = project_lanes(observations)
        milestones = milestone_facts(state)
        signals = lane_signal_map(state)
        conflict_count = sum(
            1 for o in observations if o.status is ObservationStatus.CONFLICTING
        )
        exact_dates = [
            o.occurred.value for o in observations
            if isinstance(o.occurred, ExactDate)
        ]
        from openpali.identity.ids import property_id_from_apn

        property_id = property_id_from_apn(apn)
        state_rows.append(
            {
                "snapshot_id": snapshot_id,
                "property_id": property_id,
                "apn": apn,
                "jurisdiction": parcel.jurisdiction,
                "address": parcel.situs_address,
                "neighborhood": parcel.neighborhood,
                "projection_policy_version": PROJECTION_POLICY_VERSION,
                "lane_signals": signals,
                "milestones": milestones,
                "observation_count": len(observations),
                "conflict_count": conflict_count,
                "last_evidence_date": max(exact_dates) if exact_dates else None,
            }
        )
        members.append(
            {"snapshot_id": snapshot_id, "member_type": "parcel_version",
             "member_id": parcel.record_version_id}
        )
        for stored_id, _ in parcel_pairs:
            members.append(
                {"snapshot_id": snapshot_id, "member_type": "observation",
                 "member_id": stored_id}
            )

    # Chunked bulk inserts: psycopg allows at most 65,535 bound parameters
    # per statement (5,877 parcels x 12 columns exceeds it).
    def _chunked(model, rows: list[dict], index_elements: list[str], chunk: int = 500) -> None:
        for start in range(0, len(rows), chunk):
            session.execute(
                pg_insert(model)
                .values(rows[start : start + chunk])
                .on_conflict_do_nothing(index_elements=index_elements)
            )

    if state_rows:
        _chunked(SnapshotPropertyState, state_rows, ["snapshot_id", "property_id"])
    if members:
        # Deduplicate (an observation may relate to several parcels).
        unique = {(m["member_type"], m["member_id"]): m for m in members}
        _chunked(
            SnapshotMember,
            list(unique.values()),
            ["snapshot_id", "member_type", "member_id"],
            chunk=5000,
        )

    snapshot.status = "built"
    snapshot.staged_at = cutoff
    session.flush()
    return SnapshotResult(
        snapshot_id=snapshot_id,
        created=True,
        properties=len(state_rows),
        observations=len(pairs) - len(conflicts),
        conflicts=len(conflicts),
    )
