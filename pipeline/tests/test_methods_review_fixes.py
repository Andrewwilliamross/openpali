"""Regression tests for the CP1 methods-review findings (B1, S1, S3, S4, S5)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from openpali.domain.conflicts import detect_conflicts
from openpali.domain.observations import (
    ObservationStatus,
    RecoveryObservation,
    SourceRecordRef,
    SubjectRef,
    SubjectType,
)
from openpali.domain.policy import classify_permit
from openpali.domain.temporal import DateInterval, ExactDate, UnknownDate
from openpali.ingestion import normalize

OBSERVED = datetime(2026, 7, 1, tzinfo=timezone.utc)
SOURCE = SourceRecordRef("ladbs_inspections", "row-1")


def _iso_ms(iso: str) -> int:
    d = date.fromisoformat(iso)
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _inspection(desc: str, status: str, dt_iso: str | None):
    classifications = {"P-1": classify_permit("Bldg-New", "Rebuild")}
    return normalize.normalize_ladbs_inspection(
        {
            "PERMIT": "P-1",
            "INSP_DESC": desc,
            "INSP_STATUS": status,
            "INSP_DT": _iso_ms(dt_iso) if dt_iso else None,
        },
        observed_at=OBSERVED,
        source_record=SOURCE,
        permit_classifications=classifications,
        permit_to_apn={"P-1": "4400001001"},
    )


class TestB1InspectionIdentity:
    def test_two_scheduled_inspections_have_distinct_ids(self):
        a = _inspection("Foundation", "Insp Scheduled", "2026-06-20").observations[0]
        b = _inspection("Frame", "Insp Scheduled", "2026-06-28").observations[0]
        assert a.observation_id != b.observation_id

    def test_same_inspection_reprocessed_is_identical(self):
        a = _inspection("Foundation", "Insp Scheduled", "2026-06-20").observations[0]
        b = _inspection("Foundation", "Insp Scheduled", "2026-06-20").observations[0]
        assert a.observation_id == b.observation_id


class TestS5FutureOutcomeBranches:
    """The public INSP_STATUS domain is exactly {'Insp Scheduled'} today; these
    tests exercise the outcome branches directly so a future documented-domain
    expansion lands on verified code."""

    @pytest.fixture(autouse=True)
    def _expanded_domain(self, monkeypatch):
        from openpali.domain import taxonomy

        expanded = dict(taxonomy.INSP_STATUS_DOMAIN)
        expanded.update(
            {
                "insp passed": taxonomy.InspectionOutcomeCategory.PASSED,
                "insp failed": taxonomy.InspectionOutcomeCategory.FAILED,
                "insp cancelled": taxonomy.InspectionOutcomeCategory.CANCELED,
                "insp partial": taxonomy.InspectionOutcomeCategory.PARTIAL,
            }
        )
        monkeypatch.setattr(taxonomy, "INSP_STATUS_DOMAIN", expanded)

    def test_passed_on_qualifying_permit_is_construction_milestone(self):
        observation = _inspection("Final", "Insp Passed", "2026-05-01").observations[0]
        assert observation.event_type == "construction_inspection_passed"
        assert observation.status is ObservationStatus.PASSED
        assert isinstance(observation.occurred, ExactDate)

    def test_failed_is_activity_never_milestone(self):
        observation = _inspection("Final", "Insp Failed", "2026-05-01").observations[0]
        assert observation.event_type == "construction_inspection_activity"
        assert observation.status is ObservationStatus.FAILED
        assert not observation.counts_as_milestone()

    def test_canceled_is_activity(self):
        observation = _inspection("Final", "Insp Cancelled", None).observations[0]
        assert observation.status is ObservationStatus.CANCELED
        assert isinstance(observation.occurred, UnknownDate)

    def test_partial_maps_to_attempted(self):
        observation = _inspection("Final", "Insp Partial", "2026-05-01").observations[0]
        assert observation.status is ObservationStatus.ATTEMPTED


def _milestone(occurred, subject_id="p-1"):
    return RecoveryObservation(
        subject=SubjectRef(SubjectType.PERMIT_APPLICATION, subject_id),
        lane=None,
        event_type="rebuild_permit_issued",
        status=ObservationStatus.ISSUED,
        occurred=occurred,
        observed_at=OBSERVED,
        source_record=SOURCE,
        policy_version="test",
    )


class TestS1IntervalConflicts:
    def test_interval_excluding_exact_date_conflicts(self):
        observations = [
            _milestone(ExactDate(date(2026, 5, 1))),
            _milestone(DateInterval(date(2026, 6, 1), date(2026, 6, 30))),
        ]
        assert len(detect_conflicts(observations, detected_at=OBSERVED)) == 1

    def test_interval_containing_exact_date_is_consistent(self):
        observations = [
            _milestone(ExactDate(date(2026, 6, 15))),
            _milestone(DateInterval(date(2026, 6, 1), date(2026, 6, 30))),
        ]
        assert detect_conflicts(observations, detected_at=OBSERVED) == []

    def test_disjoint_intervals_conflict(self):
        observations = [
            _milestone(DateInterval(date(2026, 1, 1), date(2026, 2, 1))),
            _milestone(DateInterval(date(2026, 3, 1), date(2026, 4, 1))),
        ]
        assert len(detect_conflicts(observations, detected_at=OBSERVED)) == 1

    def test_unknown_constrains_nothing(self):
        observations = [
            _milestone(ExactDate(date(2026, 6, 15))),
            _milestone(UnknownDate()),
        ]
        assert detect_conflicts(observations, detected_at=OBSERVED) == []


class TestS3S4Semantics:
    def test_destruction_interval_is_bounded_by_observation(self):
        record = normalize.normalize_county_parcel(
            {"APN": "4400001001", "DAMAGE": "Destroyed (>50%)", "ROE_STATUS": "No ROE"},
            observed_at=OBSERVED,
            source_record=SourceRecordRef("county_base", "4400001001"),
        )
        destroyed = [o for o in record.observations if o.event_type == "structure_destroyed"]
        assert destroyed and isinstance(destroyed[0].occurred, DateInterval)
        assert destroyed[0].occurred.latest_date == OBSERVED.date()

    def test_flag_missing_gets_distinct_event_type(self):
        record = normalize.normalize_ladbs_permit(
            {
                "PERMIT": "P-9",
                "APN": "4400-009-009",
                "PERMIT_TYPE": "Bldg-New",
                "PALISADES_WF_REBUILD": None,
                "PERMIT_STATUS": "Plans Submitted",
            },
            observed_at=OBSERVED,
            source_record=SourceRecordRef("ladbs_permits", "P-9"),
        )
        types = {o.event_type for o in record.observations}
        assert "permit_activity_flag_missing" in types
        assert "non_rebuild_permit_activity" not in types
