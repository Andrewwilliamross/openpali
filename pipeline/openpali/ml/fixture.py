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
from openpali.identity.ids import (
    IDENTITY_SEED_POLICY_VERSION,
    identity_seed_for_apn,
    property_id_from_apn,
    record_version_id,
)
from openpali.ingestion.load import insert_observations
from openpali.ingestion.snapshot import build_snapshot
from openpali.ingestion.acquire import ensure_source
from openpali.storage.models import (
    AcquisitionRun,
    ObservationRevision,
    ParcelVersion,
    PropertyIdentity,
    Source,
)
from openpali.storage.objects import ObjectStore

FIXTURE_SOURCE = "fixture_civic"
FIXTURE_APN_PREFIX = "99"
SEED = 424242
N_APPLICATIONS = 320
FIRE = date(2025, 1, 7)
# Versioned generator: a change to the fixture's generative semantics is a new
# acquisition lineage (new run ids -> new snapshot/dataset ids), never a
# silent mutation of immutable artifacts.
# v2: issuance observed by the first acquisition at/after occurrence
# (administrative censoring; PH-clean generator, no artificial cure class).
FIXTURE_VERSION = "fixture-v2"


def _fixture_record_version(session: Session, apn: str, run: AcquisitionRun) -> str:
    """Minimal source_record_version row backing a fixture parcel version."""

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from openpali.storage.models import SourceRecordVersion

    payload = {"APN": apn, "fixture": True}
    import hashlib as _hashlib
    from openpali.identity.ids import canonical_json

    payload_sha = _hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    version_id = record_version_id(FIXTURE_SOURCE, apn, payload_sha)
    session.execute(
        pg_insert(SourceRecordVersion)
        .values(
            record_version_id=version_id,
            source_id=FIXTURE_SOURCE,
            native_key=apn,
            acquisition_run_id=run.id,
            payload_sha256=payload_sha,
            payload=payload,
            first_observed_at=run.retrieved_at,
        )
        .on_conflict_do_nothing(index_elements=["record_version_id"])
    )
    return version_id


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
            f"{FIXTURE_SOURCE}:{acquired.isoformat()}:{FIXTURE_VERSION}".encode()
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

    def acquisition_for(when: date) -> AcquisitionRun | None:
        """First acquisition run at/after the event date — an event is only
        observable once a run has actually retrieved it. Events after the
        final run are unobserved everywhere (honest right-censoring)."""

        for run in runs:
            if run.retrieved_at.date() >= when:
                return run
        return None

    def ensure_fixture_parcel(apn: str, run: AcquisitionRun) -> None:
        """Full parcel identity so snapshots project fixture properties."""

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        property_id = property_id_from_apn(apn)
        session.execute(
            pg_insert(PropertyIdentity)
            .values(
                property_id=property_id,
                identity_seed=identity_seed_for_apn(apn),
                seed_policy_version=IDENTITY_SEED_POLICY_VERSION,
            )
            .on_conflict_do_nothing(index_elements=["identity_seed"])
        )
        session.flush()
        identity = session.execute(
            select(PropertyIdentity).where(PropertyIdentity.property_id == property_id)
        ).scalar_one()
        existing = session.execute(
            select(ParcelVersion).where(
                ParcelVersion.apn == apn, ParcelVersion.observed_to.is_(None)
            ).limit(1)
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ParcelVersion(
                    property_identity_id=identity.id,
                    apn=apn,
                    jurisdiction="FIXTURE",
                    situs_address=f"{apn} FIXTURE ST",
                    neighborhood="Fixtureland",
                    damage_class="Destroyed (>50%)",
                    record_version_id=_fixture_record_version(session, apn, run),
                    observed_from=run.retrieved_at,
                )
            )
            session.flush()

    observations: list[tuple[RecoveryObservation, AcquisitionRun]] = []
    for index, app in enumerate(applications):
        parcel = SubjectRef(SubjectType.PARCEL, app["apn"])
        ensure_fixture_parcel(app["apn"], runs[0])
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
        assert submit_run is not None  # submissions all precede the last run
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
        # Issuance is observed by the first acquisition at/after it occurs;
        # issuances past the acquisition window stay unobserved. Censoring is
        # therefore ADMINISTRATIVE (bitemporal window), not an artificial
        # "never issues" class — the generator remains proportional-hazards,
        # which is what the interpretable Cox challenger is supposed to learn.
        issue_run = acquisition_for(app["issued"])
        if issue_run is not None:
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
    ensure_fixture_parcel(late_parcel.id, month12)
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


def reset_fixture(session: Session) -> None:
    """Remove ALL fixture-derived rows so the drill rebuilds from scratch.

    Strictly scoped to fixture identifiers (fixture source, FX permits, the
    reserved APN prefix, fixture-run snapshots); real civic evidence is
    append-only and untouched.
    """

    from sqlalchemy import delete, text

    fixture_snapshots = [
        row[0]
        for row in session.execute(text(
            "SELECT snapshot_id FROM civic.snapshot "
            "WHERE input_runs_sha256 IN ("
            "  SELECT input_runs_sha256 FROM civic.snapshot s2 WHERE NOT EXISTS ("
            "    SELECT 1 FROM jsonb_array_elements_text(s2.input_runs) r(run_id) "
            "    WHERE r.run_id NOT LIKE 'run-fixture-%'))"
        ))
    ]
    if fixture_snapshots:
        session.execute(text(
            "DELETE FROM ml.prediction WHERE prediction_set_id IN "
            "(SELECT prediction_set_id FROM ml.prediction_set WHERE snapshot_id = ANY(:s))"
        ), {"s": fixture_snapshots})
        session.execute(text(
            "DELETE FROM ml.prediction_set WHERE snapshot_id = ANY(:s)"
        ), {"s": fixture_snapshots})
        session.execute(text(
            "DELETE FROM ml.promotion_decision WHERE proposed_model_id IN "
            "(SELECT model_id FROM ml.model_version WHERE experiment_run_id IN "
            " (SELECT experiment_run_id FROM ml.experiment_run WHERE dataset_id IN "
            "  (SELECT dataset_id FROM ml.dataset_version WHERE snapshot_id = ANY(:s))))"
        ), {"s": fixture_snapshots})
        session.execute(text(
            "DELETE FROM ml.model_version WHERE experiment_run_id IN "
            "(SELECT experiment_run_id FROM ml.experiment_run WHERE dataset_id IN "
            " (SELECT dataset_id FROM ml.dataset_version WHERE snapshot_id = ANY(:s)))"
        ), {"s": fixture_snapshots})
        session.execute(text(
            "DELETE FROM ml.experiment_run WHERE dataset_id IN "
            "(SELECT dataset_id FROM ml.dataset_version WHERE snapshot_id = ANY(:s))"
        ), {"s": fixture_snapshots})
        session.execute(text(
            "DELETE FROM ml.dataset_version WHERE snapshot_id = ANY(:s)"
        ), {"s": fixture_snapshots})
        session.execute(text(
            "DELETE FROM civic.snapshot_property_state WHERE snapshot_id = ANY(:s)"
        ), {"s": fixture_snapshots})
        session.execute(text(
            "DELETE FROM civic.snapshot_member WHERE snapshot_id = ANY(:s)"
        ), {"s": fixture_snapshots})
        session.execute(text(
            "DELETE FROM civic.snapshot WHERE snapshot_id = ANY(:s)"
        ), {"s": fixture_snapshots})
    session.execute(text(
        "DELETE FROM civic.observation_revision WHERE source_id = :src"
    ), {"src": FIXTURE_SOURCE})
    session.execute(text(
        "DELETE FROM civic.recovery_observation WHERE source_id = :src"
    ), {"src": FIXTURE_SOURCE})
    session.execute(text(
        "DELETE FROM civic.recovery_observation WHERE source_id = 'openpali_conflict_detection' "
        "AND (subject_id LIKE 'FX%' OR subject_id LIKE :apn)"
    ), {"apn": f"{FIXTURE_APN_PREFIX}%"})
    session.execute(text(
        "DELETE FROM civic.parcel_version WHERE jurisdiction = 'FIXTURE'"
    ))
    session.execute(text(
        "DELETE FROM civic.property_identity WHERE identity_seed LIKE :seed "
        "AND NOT EXISTS (SELECT 1 FROM civic.parcel_version pv "
        "WHERE pv.property_identity_id = civic.property_identity.id)"
    ), {"seed": f"county_apn:{FIXTURE_APN_PREFIX}%"})
    session.execute(text(
        "DELETE FROM source.source_record_version WHERE source_id = :src"
    ), {"src": FIXTURE_SOURCE})
    session.flush()
