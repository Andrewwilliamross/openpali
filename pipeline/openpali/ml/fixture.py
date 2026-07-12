"""Nontrivial temporal ML fixture + the N -> N+1 drill (ML-002/ML-003).

The fixture fabricates a ledger whose observations carry GENUINELY staggered
``observed_at`` acquisition times over a year (monthly fixture acquisition
runs), so the precommitted point-in-time-history gate passes and the complete
challenger/serialization/registry/serving path executes. Synthetic subjects
use a reserved source (``fixture_civic``) and APN prefix so they can never be
confused with, or leak into, real civic releases.

Ground truth embedded in the generator: issuance hazard IMPROVES for later
submissions (processing sped up over time) — a real calendar effect the Cox
challenger can learn and beat the KM baseline on.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from openpali.ingestion.snapshot import build_snapshot
from openpali.ingestion.acquire import ensure_source
from openpali.storage.models import AcquisitionRun, ObservationRevision, Source
from openpali.storage.objects import ObjectStore

FIXTURE_SOURCE = "fixture_civic"
FIXTURE_APN_PREFIX = "99"
SEED = 424242
N_APPLICATIONS = 320
FIRE = date(2025, 1, 7)


class _FixtureAdapterStub:
    source_id = FIXTURE_SOURCE
    title = "Deterministic temporal ML fixture ledger"
    jurisdiction = "FIXTURE"
    layer_url = "fixture://civic"
    terms_reference = "synthetic fixture data; never a public claim"


def _monthly_runs(session: Session, months: int, start: date) -> list[AcquisitionRun]:
    ensure_source(session, _FixtureAdapterStub(), criticality="fixture")
    runs = []
    for index in range(months):
        acquired = datetime(
            start.year, start.month, 15, 12, 0, tzinfo=timezone.utc
        ) + timedelta(days=31 * index)
        run_id = "run-fixture-" + hashlib.sha256(
            f"{FIXTURE_SOURCE}:{acquired.isoformat()}".encode()
        ).hexdigest()[:16]
        existing = session.execute(
            select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
        ).scalar_one_or_none()
        if existing is None:
            existing = AcquisitionRun(
                run_id=run_id,
                source_id=FIXTURE_SOURCE,
                parameters={"month_index": index},
                online=False,
                requested_at=acquired,
                retrieved_at=acquired,
                status="succeeded",
                record_count=0,
                health={"fixture": True},
            )
            session.add(existing)
            session.flush()
        runs.append(existing)
    return runs


def _application(rng: random.Random, index: int) -> dict:
    apn = f"{FIXTURE_APN_PREFIX}{index:08d}"
    permit_no = f"FX{index:05d}-10000-{index:05d}"
    submitted = FIRE + timedelta(days=rng.randint(30, 330))
    # Hazard improves with later submission: mean time drops from ~150d to ~70d.
    progress = (submitted - FIRE).days / 330
    mean_days = 150 - 80 * progress
    duration = max(int(rng.expovariate(1.0 / mean_days)), 7)
    issued = submitted + timedelta(days=duration)
    return {
        "apn": apn,
        "permit_no": permit_no,
        "submitted": submitted,
        "issued": issued,
    }


def _observation(
    subject: SubjectRef,
    lane,
    event_type: str,
    status: ObservationStatus,
    occurred: date,
    observed_at: datetime,
    related: tuple[SubjectRef, ...] = (),
    label: str = "",
) -> RecoveryObservation:
    return RecoveryObservation(
        subject=subject,
        lane=lane,
        event_type=event_type,
        status=status,
        occurred=ExactDate(occurred),
        observed_at=observed_at,
        source_record=SourceRecordRef(FIXTURE_SOURCE, subject.id),
        policy_version="fixture-v1",
        label=label or event_type,
        related_subjects=related,
    )


@dataclass(slots=True)
class FixtureResult:
    snapshot_n: str
    snapshot_n1: str
    runs_n: list[str]
    runs_n1: list[str]
    applications: int


def build_fixture_ledger(session: Session, store: ObjectStore) -> FixtureResult:
    """Create the staggered fixture ledger and the two drill snapshots.

    Snapshot N: first 11 monthly acquisitions. Snapshot N+1 adds month 12,
    which contains (a) a LATE-ARRIVING eligible application whose submission
    occurred months earlier, and (b) a retraction correcting one issuance.
    """

    rng = random.Random(SEED)
    runs = _monthly_runs(session, 12, FIRE + timedelta(days=40))
    applications = [_application(rng, i) for i in range(N_APPLICATIONS)]

    def acquisition_for(when: date) -> AcquisitionRun:
        for run in runs[:-1]:
            if run.retrieved_at.date() >= when:
                return run
        return runs[-2]  # last N-window run

    observations: list[tuple[RecoveryObservation, AcquisitionRun]] = []
    for index, app in enumerate(applications):
        parcel = SubjectRef(SubjectType.PARCEL, app["apn"])
        permit = SubjectRef(SubjectType.PERMIT_APPLICATION, app["permit_no"])
        # Parcel context observed in the FIRST run at/after fire (guarantees
        # feature availability at origin for the history gate).
        parcel_run = runs[0]
        observations.append(
            (
                _observation(
                    parcel, None, "structure_destroyed",
                    ObservationStatus.AGENCY_REPORTED, FIRE,
                    parcel_run.retrieved_at,
                    label="fixture destruction record",
                ),
                parcel_run,
            )
        )
        submit_run = acquisition_for(app["submitted"])
        observations.append(
            (
                _observation(
                    permit, MilestoneLane.PERMITTING, "rebuild_application_submitted",
                    ObservationStatus.AGENCY_REPORTED, app["submitted"],
                    submit_run.retrieved_at, related=(parcel,),
                ),
                submit_run,
            )
        )
        # ~25% remain unissued by the N cutoff (right-censored)
        if index % 4 != 0:
            issue_run = acquisition_for(app["issued"])
            observations.append(
                (
                    _observation(
                        permit, MilestoneLane.PERMITTING, "rebuild_permit_issued",
                        ObservationStatus.ISSUED, app["issued"],
                        issue_run.retrieved_at, related=(parcel,),
                    ),
                    issue_run,
                )
            )

    # N+1 additions: late-arriving eligible application (old submission,
    # first observed in month 12) + a correction/retraction.
    late_parcel = SubjectRef(SubjectType.PARCEL, f"{FIXTURE_APN_PREFIX}99999901")
    late_permit = SubjectRef(SubjectType.PERMIT_APPLICATION, "FXLATE-10000-00001")
    month12 = runs[-1]
    observations.append(
        (
            _observation(
                late_parcel, None, "structure_destroyed",
                ObservationStatus.AGENCY_REPORTED, FIRE, month12.retrieved_at,
            ),
            month12,
        )
    )
    observations.append(
        (
            _observation(
                late_permit, MilestoneLane.PERMITTING, "rebuild_application_submitted",
                ObservationStatus.AGENCY_REPORTED, FIRE + timedelta(days=90),
                month12.retrieved_at, related=(late_parcel,),
                label="late-arriving application (submission long before observation)",
            ),
            month12,
        )
    )

    inserted = 0
    for observation, run in observations:
        inserted += insert_observations(session, [observation], record_version=None)

    # retraction (month 12) of one issuance observed earlier
    retract_target = next(
        o for o, _ in observations
        if o.event_type == "rebuild_permit_issued"
    )
    revision_id = "rev-fixture-" + hashlib.sha256(
        retract_target.observation_id.encode()
    ).hexdigest()[:16]
    if session.execute(
        select(ObservationRevision).where(ObservationRevision.revision_id == revision_id)
    ).scalar_one_or_none() is None:
        session.add(
            ObservationRevision(
                revision_id=revision_id,
                target_observation_id=retract_target.observation_id,
                revision_type="retraction",
                reason="fixture correction: issuance recorded in error",
                source_id=FIXTURE_SOURCE,
                revised_at=month12.retrieved_at,
            )
        )
    session.flush()

    runs_n = [r.run_id for r in runs[:-1]]
    runs_n1 = [r.run_id for r in runs]
    cutoff_n = runs[-2].retrieved_at + timedelta(hours=1)
    cutoff_n1 = runs[-1].retrieved_at + timedelta(hours=1)
    snapshot_n = build_snapshot(session, runs_n, cutoff_n)
    snapshot_n1 = build_snapshot(session, runs_n1, cutoff_n1)
    session.commit()
    return FixtureResult(
        snapshot_n=snapshot_n.snapshot_id,
        snapshot_n1=snapshot_n1.snapshot_id,
        runs_n=runs_n,
        runs_n1=runs_n1,
        applications=N_APPLICATIONS,
    )
