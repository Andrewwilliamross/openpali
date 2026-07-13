"""Same-snapshot contradiction detection.

A milestone that can only happen once per subject (a specific permit being
issued, a certificate of occupancy for one application, final debris sign-off
for one parcel) asserted with two different exact dates in one snapshot is a
contradiction. It must surface as CONFLICTING evidence — never be silently
collapsed to either date.

Cross-source reconciliation (e.g. LADBS vs Socrata) extends this in the
analytics layer; the primitive lives here so fixtures and ingestion share it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from datetime import date as _date

from .observations import (
    MilestoneLane,
    ObservationStatus,
    RecoveryObservation,
    SourceRecordRef,
)
from .temporal import DateInterval, ExactDate

#: Event types that may occur at most once per (subject, event_type).
UNIQUE_MILESTONE_EVENTS: frozenset[str] = frozenset(
    {
        "rebuild_permit_issued",
        "certificate_of_occupancy_issued",
        "plan_check_approved",
        "debris_removal_complete",
    }
)

CONFLICT_POLICY_VERSION = "conflicts-v1"
CONFLICT_SOURCE_ID = "openpali_conflict_detection"


def _bounds(observation: RecoveryObservation) -> tuple[_date | None, _date | None]:
    """Occurrence constraint as [earliest, latest]; None = unbounded side."""

    occurred = observation.occurred
    if isinstance(occurred, ExactDate):
        return occurred.value, occurred.value
    if isinstance(occurred, DateInterval):
        return occurred.earliest_date, occurred.latest_date
    return None, None  # UnknownDate constrains nothing


def _constraints_incompatible(group: list[RecoveryObservation]) -> bool:
    """True when the intersection of all occurrence constraints is empty.

    Two distinct exact dates conflict; an interval that excludes an asserted
    exact date conflicts; overlapping intervals and unknowns are consistent
    (censoring, not contradiction)."""

    lower: _date | None = None
    upper: _date | None = None
    for observation in group:
        earliest, latest = _bounds(observation)
        if earliest is not None and (lower is None or earliest > lower):
            lower = earliest
        if latest is not None and (upper is None or latest < upper):
            upper = latest
    return lower is not None and upper is not None and lower > upper


def detect_conflicts(
    observations: list[RecoveryObservation],
    *,
    detected_at: datetime,
) -> list[RecoveryObservation]:
    """Return derived CONFLICTING observations for contradictory assertions.

    A unique milestone's occurrence constraints (exact dates and intervals)
    must admit at least one common date; an empty intersection is a
    contradiction. Unknown times constrain nothing.
    """

    grouped: dict[tuple, list[RecoveryObservation]] = defaultdict(list)
    for observation in observations:
        if (
            observation.event_type in UNIQUE_MILESTONE_EVENTS
            and observation.counts_as_milestone()
        ):
            key = (observation.subject.type, observation.subject.id, observation.event_type)
            grouped[key].append(observation)

    conflicts: list[RecoveryObservation] = []
    for (_, subject_id, event_type), group in grouped.items():
        exact_dates = {
            o.occurred.value for o in group if isinstance(o.occurred, ExactDate)
        }
        if _constraints_incompatible(group):
            first = group[0]
            described = sorted(
                f"[{e or '..'}..{l or '..'}]"
                for e, l in ((_bounds(o)) for o in group)
            )
            conflicts.append(
                RecoveryObservation(
                    subject=first.subject,
                    lane=first.lane,
                    event_type=event_type,
                    status=ObservationStatus.CONFLICTING,
                    occurred=first.occurred,
                    observed_at=detected_at,
                    source_record=SourceRecordRef(
                        source_id=CONFLICT_SOURCE_ID,
                        native_key=f"{subject_id}:{event_type}",
                    ),
                    policy_version=CONFLICT_POLICY_VERSION,
                    label=(
                        f"Conflicting source assertions for {event_type}: "
                        + ", ".join(described)
                    ),
                    related_subjects=first.related_subjects,
                    detail=(
                        ("conflicting_constraints", ",".join(described)),
                        ("conflicting_dates", ",".join(sorted(d.isoformat() for d in exact_dates))),
                        ("conflicting_observations", ",".join(sorted(o.observation_id for o in group))),
                    ),
                )
            )
    return conflicts
