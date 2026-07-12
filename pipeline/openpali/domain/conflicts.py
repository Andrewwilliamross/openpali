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

from .observations import (
    MilestoneLane,
    ObservationStatus,
    RecoveryObservation,
    SourceRecordRef,
)
from .temporal import ExactDate

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


def detect_conflicts(
    observations: list[RecoveryObservation],
    *,
    detected_at: datetime,
) -> list[RecoveryObservation]:
    """Return derived CONFLICTING observations for contradictory assertions.

    Only distinct exact dates for the same unique milestone on the same
    subject conflict. Intervals overlapping an exact date are treated as
    consistent (they are censoring, not contradiction).
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
        if len(exact_dates) > 1:
            first = group[0]
            conflicts.append(
                RecoveryObservation(
                    subject=first.subject,
                    lane=first.lane,
                    event_type=event_type,
                    status=ObservationStatus.CONFLICTING,
                    occurred=first.occurred,
                    observed_at=detected_at,
                    source_record=SourceRecordRef(
                        source_id="openpali_conflict_detection",
                        native_key=f"{subject_id}:{event_type}",
                    ),
                    policy_version=CONFLICT_POLICY_VERSION,
                    label=(
                        f"Conflicting source assertions for {event_type}: "
                        + ", ".join(sorted(d.isoformat() for d in exact_dates))
                    ),
                    related_subjects=first.related_subjects,
                    detail=(
                        ("conflicting_dates", ",".join(sorted(d.isoformat() for d in exact_dates))),
                        ("conflicting_observations", ",".join(sorted(o.observation_id for o in group))),
                    ),
                )
            )
    return conflicts
