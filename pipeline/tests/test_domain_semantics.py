"""Unit tests for domain primitives: temporal truth, taxonomy fail-closed
behavior, qualification policy, conflicts, and retractions."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from openpali.domain.conflicts import detect_conflicts
from openpali.domain.observations import (
    MilestoneLane,
    ObservationStatus,
    RecoveryObservation,
    SourceRecordRef,
    SubjectRef,
    SubjectType,
)
from openpali.domain.policy import PermitQualification, classify_permit
from openpali.domain.revisions import Retraction, apply_retractions
from openpali.domain.taxonomy import (
    interpret_inspection_status,
    interpret_permit_status,
    interpret_rebuild_flag,
    interpret_roe_status,
)
from openpali.domain.temporal import (
    DateInterval,
    ExactDate,
    UnknownDate,
    occurrence_from_json,
    occurrence_from_source_date,
    occurrence_to_json,
)

OBSERVED = datetime(2026, 7, 1, tzinfo=timezone.utc)
SOURCE = SourceRecordRef("test_source", "row-1")


def _observation(event_type: str, occurred, status=ObservationStatus.ISSUED, subject_id="p-1"):
    return RecoveryObservation(
        subject=SubjectRef(SubjectType.PERMIT_APPLICATION, subject_id),
        lane=MilestoneLane.PERMITTING,
        event_type=event_type,
        status=status,
        occurred=occurred,
        observed_at=OBSERVED,
        source_record=SOURCE,
        policy_version="test-v1",
    )


class TestTemporal:
    def test_missing_date_maps_to_unknown_never_a_constant(self):
        assert isinstance(occurrence_from_source_date(None), UnknownDate)

    def test_interval_requires_a_bound(self):
        with pytest.raises(ValueError):
            DateInterval(None, None)

    def test_interval_rejects_inverted_bounds(self):
        with pytest.raises(ValueError):
            DateInterval(date(2026, 1, 2), date(2026, 1, 1))

    def test_roundtrip_json(self):
        for value in (
            ExactDate(date(2025, 3, 22)),
            DateInterval(date(2025, 1, 7), None),
            DateInterval(None, date(2026, 7, 1)),
            UnknownDate(),
        ):
            assert occurrence_from_json(occurrence_to_json(value)) == value


class TestTaxonomyFailClosed:
    def test_only_scheduled_is_documented_for_inspections(self):
        assert interpret_inspection_status("Insp Scheduled").documented
        assert interpret_inspection_status("Insp Scheduled").category == "scheduled"
        for surprise in ("Insp Completed", "Passed", "Final OK", ""):
            interpretation = interpret_inspection_status(surprise)
            assert not interpretation.documented or interpretation.raw is None

    def test_undocumented_roe_fails_closed(self):
        assert not interpret_roe_status("Brand New Status").documented

    def test_optout_is_documented_but_not_completion(self):
        interpretation = interpret_roe_status("Opt-Out and Manage Cleanup Independently")
        assert interpretation.documented
        assert interpretation.category == "opt_out_selected"

    def test_missing_rebuild_flag_is_typed_missing(self):
        interpretation = interpret_rebuild_flag(None)
        assert interpretation.documented
        assert interpretation.category == "missing"

    def test_permit_status_domain_complete(self):
        for value in (
            "Plans Submitted",
            "Plan Check in Progress",
            "Corrections Issued",
            "Application Pending Fees",
            "Plans Approved & Permit Not Issued",
            "Plans Approved & Permit Issued",
        ):
            assert interpret_permit_status(value).documented, value
        assert not interpret_permit_status("Permit Finaled").documented


class TestQualificationPolicy:
    def test_bldg_new_rebuild_qualifies(self):
        classification = classify_permit("Bldg-New", "Rebuild")
        assert classification.qualification is PermitQualification.QUALIFYING_REBUILD_APPLICATION

    def test_grading_rebuild_is_ancillary(self):
        classification = classify_permit("Grading", "Rebuild")
        assert classification.qualification is PermitQualification.REBUILD_RELATED_ANCILLARY

    def test_bldg_new_no_is_not_fire_rebuild(self):
        classification = classify_permit("Bldg-New", "No")
        assert classification.qualification is PermitQualification.NOT_FIRE_REBUILD

    def test_missing_flag_never_qualifies(self):
        classification = classify_permit("Bldg-New", None)
        assert classification.qualification is PermitQualification.FLAG_MISSING

    def test_undocumented_type_fails_closed(self):
        classification = classify_permit("Bldg-Moved", "Rebuild")
        assert classification.qualification is PermitQualification.UNDOCUMENTED
        assert not classification.documented


class TestConflicts:
    def test_distinct_exact_dates_conflict(self):
        observations = [
            _observation("rebuild_permit_issued", ExactDate(date(2025, 8, 1))),
            _observation("rebuild_permit_issued", ExactDate(date(2025, 9, 1))),
        ]
        conflicts = detect_conflicts(observations, detected_at=OBSERVED)
        assert len(conflicts) == 1
        assert conflicts[0].status is ObservationStatus.CONFLICTING

    def test_interval_and_exact_do_not_conflict(self):
        observations = [
            _observation("rebuild_permit_issued", ExactDate(date(2025, 8, 1))),
            _observation(
                "rebuild_permit_issued", DateInterval(date(2025, 2, 1), date(2026, 7, 1))
            ),
        ]
        assert detect_conflicts(observations, detected_at=OBSERVED) == []

    def test_different_subjects_do_not_conflict(self):
        observations = [
            _observation("rebuild_permit_issued", ExactDate(date(2025, 8, 1)), subject_id="a"),
            _observation("rebuild_permit_issued", ExactDate(date(2025, 9, 1)), subject_id="b"),
        ]
        assert detect_conflicts(observations, detected_at=OBSERVED) == []

    def test_repeatable_events_do_not_conflict(self):
        observations = [
            _observation("construction_inspection_passed", ExactDate(date(2025, 8, 1)),
                         status=ObservationStatus.PASSED),
            _observation("construction_inspection_passed", ExactDate(date(2025, 9, 1)),
                         status=ObservationStatus.PASSED),
        ]
        assert detect_conflicts(observations, detected_at=OBSERVED) == []


class TestRevisions:
    def test_retraction_moves_to_audit_not_deletion(self):
        observation = _observation("rebuild_permit_issued", ExactDate(date(2025, 8, 1)))
        retraction = Retraction(
            target_observation_id=observation.observation_id,
            reason="upstream correction",
            retracted_at=OBSERVED,
            source="test",
        )
        result = apply_retractions([observation], [retraction])
        assert result.active == ()
        assert len(result.retracted) == 1
        assert result.retracted[0].observation_id == observation.observation_id

    def test_dangling_retraction_surfaces(self):
        retraction = Retraction(
            target_observation_id="obs-doesnotexist",
            reason="mixed snapshot?",
            retracted_at=OBSERVED,
            source="test",
        )
        result = apply_retractions([], [retraction])
        assert result.dangling_retractions == (retraction,)


class TestDeterministicIds:
    def test_observation_id_is_content_derived(self):
        a = _observation("rebuild_permit_issued", ExactDate(date(2025, 8, 1)))
        b = _observation("rebuild_permit_issued", ExactDate(date(2025, 8, 1)))
        c = _observation("rebuild_permit_issued", ExactDate(date(2025, 8, 2)))
        assert a.observation_id == b.observation_id
        assert a.observation_id != c.observation_id
