"""Regression for the county value observed in the September 2026 source probe."""

from datetime import datetime, timezone

from openpali.domain.lanes import LaneSignal, milestone_facts, project_lanes
from openpali.domain.observations import MilestoneLane, ObservationStatus, SourceRecordRef
from openpali.domain.temporal import UnknownDate
from openpali.ingestion.normalize import normalize_county_parcel


def normalize_progress(value):
    return normalize_county_parcel(
        {"APN": "4412013017", "DAMAGE": "Destroyed (>50%)", "REBUILD_PROGRESS": value},
        observed_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        source_record=SourceRecordRef("county_base", "4412013017"),
    )


def test_county_work_underway_is_visible_without_inventing_an_inspection_or_completion():
    record = normalize_progress("Rebuild In Construction")
    assert not record.undocumented
    observation = next(o for o in record.observations if o.lane is MilestoneLane.CONSTRUCTION)
    assert observation.status is ObservationStatus.AGENCY_REPORTED
    assert isinstance(observation.occurred, UnknownDate)
    assert dict(observation.detail)["progress_raw"] == "Rebuild In Construction"
    state = project_lanes(record.observations)
    construction = state.lane(MilestoneLane.CONSTRUCTION)
    assert construction.signal is LaneSignal.IN_PROGRESS
    assert construction.in_progress_ids == (observation.observation_id,)
    assert construction.reached_milestones == ()
    assert not milestone_facts(state)["construction_evidence"]
    assert not milestone_facts(state)["cofo_issued"]


def test_county_completion_retains_its_distinct_milestone():
    state = project_lanes(normalize_progress("Construction Completed").observations)
    assert state.lane(MilestoneLane.CONSTRUCTION).signal is LaneSignal.MILESTONE_REACHED
    assert milestone_facts(state)["construction_evidence"]
    assert not milestone_facts(state)["cofo_issued"]


def test_unseen_county_values_still_require_interpretation():
    record = normalize_progress("Inspection Approved Tomorrow")
    assert record.undocumented
    state = project_lanes(record.observations)
    assert state.lane(MilestoneLane.CONSTRUCTION).signal is LaneSignal.NO_PUBLIC_EVIDENCE
