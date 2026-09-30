"""Parallel milestone-lane projection.

The projection is a versioned *view* over observations (never a stored fact).
It answers, per lane: what milestone evidence exists, what agency-reported
work is in progress, what activity is merely scheduled/attempted/failed, and
what remains unknown or conflicting.

Replaces the prototype's forced 0-5 stage ladder in which any recognized
inspection description advanced a parcel to "under construction".

Projection classes for one observation:

1. milestone   — event type registered in ``LANE_MILESTONES`` for its lane AND
                 a milestone-bearing status;
2. in-progress — event type registered in ``LANE_IN_PROGRESS_EVENTS`` with a
                 milestone-bearing status (agency-reported work underway);
3. activity    — SCHEDULED / ATTEMPTED / FAILED / CANCELED status (never
                 progress);
4. conflicting — CONFLICTING status;
5. context     — everything else (destruction records, opt-out selections,
                 ancillary permits, unregistered event types). Context shapes
                 no lane signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .observations import (
    MilestoneLane,
    ObservationStatus,
    RecoveryObservation,
)

#: Version stamp carried by every projection output. Bump on any change to
#: the rules in this module and record the change in methodology docs.
PROJECTION_POLICY_VERSION = "lanes-v2"


class LaneSignal(str, Enum):
    """Strongest defensible public statement about one lane."""

    NO_PUBLIC_EVIDENCE = "no_public_evidence"
    ACTIVITY_SCHEDULED = "activity_scheduled"
    ACTIVITY_ATTEMPTED = "activity_attempted"
    IN_PROGRESS = "in_progress"
    MILESTONE_REACHED = "milestone_reached"
    CONFLICTING = "conflicting"


#: Milestone-bearing event types per lane, least to most advanced.
LANE_MILESTONES: dict[MilestoneLane, tuple[str, ...]] = {
    MilestoneLane.CLEANUP: ("debris_removal_complete",),
    MilestoneLane.DESIGN_REVIEW: ("plan_check_approved",),
    MilestoneLane.PERMITTING: (
        "rebuild_application_submitted",
        "rebuild_permit_issued",
    ),
    MilestoneLane.CONSTRUCTION: (
        "construction_inspection_passed",
        "construction_completed",
    ),
    MilestoneLane.OCCUPANCY: ("certificate_of_occupancy_issued",),
}

#: Agency-reported in-progress event types per lane.
LANE_IN_PROGRESS_EVENTS: dict[MilestoneLane, tuple[str, ...]] = {
    MilestoneLane.CLEANUP: ("cleanup_in_process",),
    MilestoneLane.DESIGN_REVIEW: (
        "plans_submitted",
        "plan_check_in_progress",
        "corrections_issued",
        "application_pending_fees",
    ),
    MilestoneLane.PERMITTING: (),
    MilestoneLane.CONSTRUCTION: ("construction_in_progress",),
    MilestoneLane.OCCUPANCY: (),
}

#: Event types that are recorded as evidence but can never shape a lane signal
#: (program choices, ancillary permits, destruction and incident records).
NON_ADVANCING_EVENT_TYPES = frozenset(
    {
        "structure_destroyed",
        "cleanup_opt_out_selected",
        "cleanup_program_ineligible",
        "ancillary_permit_activity",
        "non_rebuild_permit_activity",
        "permit_activity_flag_missing",
        "inspection_activity",
    }
)


@dataclass(frozen=True, slots=True)
class LaneProjection:
    lane: MilestoneLane
    signal: LaneSignal
    reached_milestones: tuple[str, ...]
    evidence_observation_ids: tuple[str, ...]
    in_progress_ids: tuple[str, ...]
    scheduled_or_attempted_ids: tuple[str, ...]
    conflicting_ids: tuple[str, ...]
    policy_version: str = PROJECTION_POLICY_VERSION

    def to_json(self) -> dict:
        return {
            "lane": self.lane.value,
            "signal": self.signal.value,
            "reached_milestones": list(self.reached_milestones),
            "evidence": list(self.evidence_observation_ids),
            "in_progress": list(self.in_progress_ids),
            "scheduled_or_attempted": list(self.scheduled_or_attempted_ids),
            "conflicting": list(self.conflicting_ids),
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class ParcelLaneState:
    """All-lane projection for one subject universe, plus context evidence."""

    lanes: tuple[LaneProjection, ...] = field(default_factory=tuple)
    context_observation_ids: tuple[str, ...] = field(default_factory=tuple)
    policy_version: str = PROJECTION_POLICY_VERSION

    def lane(self, lane: MilestoneLane) -> LaneProjection:
        for projection in self.lanes:
            if projection.lane is lane:
                return projection
        raise KeyError(lane)

    def to_json(self) -> dict:
        return {
            "policy_version": self.policy_version,
            "lanes": [p.to_json() for p in self.lanes],
            "context": list(self.context_observation_ids),
        }


#: Public milestone facts derived from a lane state (booleans, not a ranking).
def milestone_facts(state: "ParcelLaneState | None") -> dict[str, bool]:
    if state is None:
        return {
            "cleanup_complete": False,
            "plan_check_approved": False,
            "application_submitted": False,
            "permit_issued": False,
            "construction_evidence": False,
            "cofo_issued": False,
        }
    reached = {
        projection.lane: projection.reached_milestones for projection in state.lanes
    }
    return {
        "cleanup_complete": "debris_removal_complete" in reached[MilestoneLane.CLEANUP],
        "plan_check_approved": "plan_check_approved" in reached[MilestoneLane.DESIGN_REVIEW],
        "application_submitted": "rebuild_application_submitted" in reached[MilestoneLane.PERMITTING],
        "permit_issued": "rebuild_permit_issued" in reached[MilestoneLane.PERMITTING],
        "construction_evidence": bool(reached[MilestoneLane.CONSTRUCTION]),
        "cofo_issued": "certificate_of_occupancy_issued" in reached[MilestoneLane.OCCUPANCY],
    }


#: Compact per-lane keys shared by artifacts, DB projections, and the API.
LANE_SIGNAL_KEYS: dict[MilestoneLane, str] = {
    MilestoneLane.CLEANUP: "lane_cleanup",
    MilestoneLane.DESIGN_REVIEW: "lane_design",
    MilestoneLane.PERMITTING: "lane_permit",
    MilestoneLane.CONSTRUCTION: "lane_constr",
    MilestoneLane.OCCUPANCY: "lane_occup",
}


def lane_signal_map(state: "ParcelLaneState | None") -> dict[str, str]:
    if state is None:
        return {key: LaneSignal.NO_PUBLIC_EVIDENCE.value for key in LANE_SIGNAL_KEYS.values()}
    return {
        LANE_SIGNAL_KEYS[projection.lane]: projection.signal.value
        for projection in state.lanes
    }


def filter_parcel_universe(
    apn: str, observations: list[RecoveryObservation]
) -> list[RecoveryObservation]:
    """Observations about a parcel: subject is the parcel or relates to it."""

    from .observations import SubjectType  # local to avoid import cycle noise

    selected: list[RecoveryObservation] = []
    for observation in observations:
        if (
            observation.subject.type is SubjectType.PARCEL
            and observation.subject.id == apn
        ):
            selected.append(observation)
            continue
        if any(
            related.type is SubjectType.PARCEL and related.id == apn
            for related in observation.related_subjects
        ):
            selected.append(observation)
    return selected


def project_lanes(observations: list[RecoveryObservation]) -> ParcelLaneState:
    """Project one subject's observations onto parallel lanes.

    Retraction handling: an observation with status RETRACTED is context. The
    storage layer additionally removes the retracted target from the active
    set before projection; the projection itself never resurrects it.
    """

    context_ids: list[str] = [
        o.observation_id for o in observations if o.lane is None
    ]
    projections: list[LaneProjection] = []
    for lane in MilestoneLane:
        lane_observations = [o for o in observations if o.lane is lane]
        milestone_order = LANE_MILESTONES[lane]
        in_progress_types = LANE_IN_PROGRESS_EVENTS[lane]
        reached: list[str] = []
        evidence_ids: list[str] = []
        in_progress_ids: list[str] = []
        pending_ids: list[str] = []
        conflict_ids: list[str] = []
        saw_attempt = False
        saw_scheduled = False
        for observation in lane_observations:
            if observation.status is ObservationStatus.CONFLICTING:
                conflict_ids.append(observation.observation_id)
                continue
            if observation.status in (
                ObservationStatus.SCHEDULED,
                ObservationStatus.ATTEMPTED,
                ObservationStatus.FAILED,
                ObservationStatus.CANCELED,
            ):
                pending_ids.append(observation.observation_id)
                saw_scheduled = saw_scheduled or observation.status is ObservationStatus.SCHEDULED
                saw_attempt = saw_attempt or observation.status in (
                    ObservationStatus.ATTEMPTED,
                    ObservationStatus.FAILED,
                )
                continue
            if observation.event_type in NON_ADVANCING_EVENT_TYPES:
                context_ids.append(observation.observation_id)
                continue
            if observation.counts_as_milestone() and observation.event_type in milestone_order:
                reached.append(observation.event_type)
                evidence_ids.append(observation.observation_id)
                continue
            if observation.counts_as_milestone() and observation.event_type in in_progress_types:
                in_progress_ids.append(observation.observation_id)
                continue
            # Unregistered event type: context only. Never progress.
            context_ids.append(observation.observation_id)

        reached_sorted = tuple(m for m in milestone_order if m in reached)
        if conflict_ids:
            signal = LaneSignal.CONFLICTING
        elif reached_sorted:
            signal = LaneSignal.MILESTONE_REACHED
        elif in_progress_ids:
            signal = LaneSignal.IN_PROGRESS
        elif saw_attempt:
            signal = LaneSignal.ACTIVITY_ATTEMPTED
        elif saw_scheduled:
            signal = LaneSignal.ACTIVITY_SCHEDULED
        else:
            signal = LaneSignal.NO_PUBLIC_EVIDENCE

        projections.append(
            LaneProjection(
                lane=lane,
                signal=signal,
                reached_milestones=reached_sorted,
                evidence_observation_ids=tuple(evidence_ids),
                in_progress_ids=tuple(in_progress_ids),
                scheduled_or_attempted_ids=tuple(pending_ids),
                conflicting_ids=tuple(conflict_ids),
            )
        )
    return ParcelLaneState(
        lanes=tuple(projections),
        context_observation_ids=tuple(context_ids),
    )


__all__ = [
    "LaneProjection",
    "LaneSignal",
    "LANE_MILESTONES",
    "LANE_IN_PROGRESS_EVENTS",
    "NON_ADVANCING_EVENT_TYPES",
    "ParcelLaneState",
    "PROJECTION_POLICY_VERSION",
    "project_lanes",
]
