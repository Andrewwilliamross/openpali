"""Recovery observations: the append-only unit of public evidence.

An observation is one assertion, from one source record, about one subject,
in one milestone lane, with an explicit outcome status and explicit
occurrence/observation times. Projections (parcel state, metrics, forecasts)
are computed views over observations and never stored as replacement facts.

Identity note: parcel, property, structure, permit application, inspection,
source record, recovery observation, acquisition run, model run, and spatial
asset are distinct concepts (SYSTEM.md invariants). ``SubjectRef`` keeps them
distinct at the type level.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .temporal import OccurrenceTime, occurrence_to_json


class SubjectType(str, Enum):
    PARCEL = "parcel"
    PROPERTY = "property"
    STRUCTURE = "structure"
    PERMIT_APPLICATION = "permit_application"
    INSPECTION = "inspection"
    CLEANUP_CASE = "cleanup_case"


class MilestoneLane(str, Enum):
    """Parallel recovery lanes. No forced total order across lanes.

    Observations whose evidence is not lane-specific (destruction record,
    ancillary permit activity, non-rebuild permits) carry ``lane=None`` and are
    timeline/context evidence only.
    """

    CLEANUP = "cleanup"
    DESIGN_REVIEW = "design_review"
    PERMITTING = "permitting"
    CONSTRUCTION = "construction"
    OCCUPANCY = "occupancy"


class ObservationStatus(str, Enum):
    """Outcome/assertion status. Members are deliberately distinct and none is
    ever coerced into another (scheduled is not attempted; attempted is not
    passed; opt-out selection is not completion)."""

    SCHEDULED = "scheduled"
    ATTEMPTED = "attempted"
    FAILED = "failed"
    PASSED = "passed"
    CANCELED = "canceled"
    ISSUED = "issued"
    ACCEPTED = "accepted"
    OBSERVED = "observed"
    AGENCY_REPORTED = "agency_reported"
    INFERRED = "inferred"
    RETRACTED = "retracted"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


#: Statuses that may ever count as "the milestone was reached".
MILESTONE_BEARING_STATUSES = frozenset(
    {
        ObservationStatus.PASSED,
        ObservationStatus.ISSUED,
        ObservationStatus.ACCEPTED,
        ObservationStatus.OBSERVED,
        ObservationStatus.AGENCY_REPORTED,
    }
)

#: Statuses that describe activity but never a reached milestone.
NON_MILESTONE_STATUSES = frozenset(
    {
        ObservationStatus.SCHEDULED,
        ObservationStatus.ATTEMPTED,
        ObservationStatus.FAILED,
        ObservationStatus.CANCELED,
        ObservationStatus.INFERRED,
        ObservationStatus.RETRACTED,
        ObservationStatus.CONFLICTING,
        ObservationStatus.UNAVAILABLE,
        ObservationStatus.UNKNOWN,
    }
)


@dataclass(frozen=True, slots=True)
class SubjectRef:
    type: SubjectType
    id: str

    def to_json(self) -> dict:
        return {"type": self.type.value, "id": self.id}


@dataclass(frozen=True, slots=True)
class SourceRecordRef:
    """Pointer to the exact source assertion behind an observation."""

    source_id: str
    native_key: str
    payload_sha256: str | None = None

    def to_json(self) -> dict:
        return {
            "source_id": self.source_id,
            "native_key": self.native_key,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class RecoveryObservation:
    """One appendable evidence assertion.

    ``observation_id`` is deterministic: it derives from the source-record
    identity, subject, event type, taxonomy/policy version, and occurrence
    encoding — never from a random surrogate (DATA-002 proof requirement).
    """

    subject: SubjectRef
    lane: MilestoneLane | None
    event_type: str
    status: ObservationStatus
    occurred: OccurrenceTime
    observed_at: datetime
    source_record: SourceRecordRef
    policy_version: str
    label: str = ""
    related_subjects: tuple[SubjectRef, ...] = field(default_factory=tuple)
    detail: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    #: Distinguishes multiple same-typed assertions about one subject from one
    #: source record family (e.g. two scheduled inspections on one permit with
    #: different descriptions/dates). Enters the deterministic ID.
    discriminator: str | None = None

    @property
    def observation_id(self) -> str:
        canonical = json.dumps(
            {
                "subject": self.subject.to_json(),
                "lane": self.lane.value if self.lane else None,
                "event_type": self.event_type,
                "status": self.status.value,
                "occurred": occurrence_to_json(self.occurred),
                "source_record": {
                    "source_id": self.source_record.source_id,
                    "native_key": self.source_record.native_key,
                },
                "policy_version": self.policy_version,
                "discriminator": self.discriminator,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "obs-" + hashlib.sha256(canonical.encode()).hexdigest()[:24]

    def counts_as_milestone(self) -> bool:
        return self.status in MILESTONE_BEARING_STATUSES

    def to_json(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "subject": self.subject.to_json(),
            "lane": self.lane.value if self.lane else None,
            "event_type": self.event_type,
            "status": self.status.value,
            "occurred": occurrence_to_json(self.occurred),
            "observed_at": self.observed_at.isoformat(),
            "source_record": self.source_record.to_json(),
            "policy_version": self.policy_version,
            "label": self.label,
            "related_subjects": [s.to_json() for s in self.related_subjects],
            "detail": dict(self.detail),
        }
