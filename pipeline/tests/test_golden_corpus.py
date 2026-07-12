"""Golden semantic-truth corpus (TRUTH-001 phase-0 exit gate).

Runs the REAL production normalization/projection code over raw-shaped fixture
rows, asserts the machine-checkable expectations embedded in the corpus, and
reconciles every lane signal against an independently written reference
implementation (differential test).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from openpali.domain.conflicts import detect_conflicts
from openpali.domain.lanes import filter_parcel_universe, project_lanes
from openpali.domain.observations import (
    MilestoneLane,
    RecoveryObservation,
    SourceRecordRef,
    SubjectType,
)
from openpali.domain.policy import PermitQualification
from openpali.domain.revisions import Retraction, apply_retractions
from openpali.domain.taxonomy import undocumented_values
from openpali.domain.temporal import DateInterval, ExactDate, UnknownDate
from openpali.ingestion import normalize

CORPUS_PATH = Path(__file__).parent / "fixtures" / "sources" / "golden_corpus.json"

_DATE_FIELDS = (
    "SUBMIT_DATE",
    "PC_APPROVED_DATE",
    "ISSUE_DATE",
    "COFO_DATE",
    "STATUS_DATE",
    "INSP_DT",
)


def _iso_to_epoch_ms(iso: str | None) -> int | None:
    if not iso:
        return None
    d = date.fromisoformat(iso)
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _transport_encode(row: dict) -> dict:
    """Convert readable *_iso fixture fields to ArcGIS epoch-ms transport."""

    encoded = dict(row)
    for field in _DATE_FIELDS:
        iso_key = f"{field}_iso"
        if iso_key in encoded:
            encoded[field] = _iso_to_epoch_ms(encoded.pop(iso_key))
    return encoded


def load_corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text())


class CaseRun:
    """Production pipeline execution for one corpus case."""

    def __init__(self, case: dict, observed_at: datetime) -> None:
        self.observed_at = observed_at
        self.interpretations = []
        self.observations: list[RecoveryObservation] = []
        self.permit_to_apn: dict[str, str] = {}
        self.classifications: dict[str, object] = {}
        self.unjoined_permits = 0
        self.orphan_inspections = 0

        for raw in case.get("county", []):
            record = normalize.normalize_county_parcel(
                _transport_encode(raw),
                observed_at=observed_at,
                source_record=SourceRecordRef("county_base", str(raw.get("APN"))),
            )
            self.observations.extend(record.observations)
            self.interpretations.extend(record.interpretations)

        for raw in case.get("permits", []):
            record = normalize.normalize_ladbs_permit(
                _transport_encode(raw),
                observed_at=observed_at,
                source_record=SourceRecordRef("ladbs_permits", str(raw.get("PERMIT"))),
            )
            self.observations.extend(record.observations)
            self.interpretations.extend(record.interpretations)
            if record.permit_no:
                self.classifications[record.permit_no] = record.classification
                if record.apn:
                    self.permit_to_apn[record.permit_no] = record.apn
                else:
                    self.unjoined_permits += 1

        for raw in case.get("inspections", []):
            permit_no = str(raw.get("PERMIT") or "").strip()
            record = normalize.normalize_ladbs_inspection(
                _transport_encode(raw),
                observed_at=observed_at,
                source_record=SourceRecordRef("ladbs_inspections", permit_no),
                permit_classifications=self.classifications,
                permit_to_apn=self.permit_to_apn,
            )
            self.observations.extend(record.observations)
            self.interpretations.extend(record.interpretations)
            if permit_no and permit_no not in self.permit_to_apn:
                self.orphan_inspections += 1

        for raw in case.get("malibu", []):
            record = normalize.normalize_malibu_marker(
                raw,
                observed_at=observed_at,
                source_record=SourceRecordRef("malibu_dash", str(raw.get("apn"))),
            )
            self.observations.extend(record.observations)
            self.interpretations.extend(record.interpretations)

        retractions = []
        for raw in case.get("retractions", []):
            target_id = raw.get("target_observation_id")
            if not target_id:
                target_id = self._resolve_target(
                    raw["target_event_type"], raw["target_subject"]
                )
            retractions.append(
                Retraction(
                    target_observation_id=target_id,
                    reason=raw["reason"],
                    retracted_at=observed_at,
                    source=raw["source"],
                )
            )
        self.revision = apply_retractions(self.observations, retractions)
        self.conflicts = detect_conflicts(
            list(self.revision.active), detected_at=observed_at
        )
        self.active = list(self.revision.active) + self.conflicts

    def _resolve_target(self, event_type: str, subject_id: str) -> str:
        for observation in self.observations:
            if observation.event_type != event_type:
                continue
            ids = [observation.subject.id] + [s.id for s in observation.related_subjects]
            if subject_id in ids:
                return observation.observation_id
        raise AssertionError(f"fixture retraction target not found: {event_type} {subject_id}")

    def parcel_state(self, apn: str):
        return project_lanes(filter_parcel_universe(apn, self.active))

    def parcel_observations(self, apn: str) -> list[RecoveryObservation]:
        return filter_parcel_universe(apn, self.active)

    @property
    def qualifying_applications(self) -> int:
        return sum(
            1
            for permit_no, classification in self.classifications.items()
            if classification is not None
            and classification.qualification
            is PermitQualification.QUALIFYING_REBUILD_APPLICATION
            and permit_no in self.permit_to_apn
        )


def _occurred_kind(observation: RecoveryObservation) -> str:
    if isinstance(observation.occurred, ExactDate):
        return "exact"
    if isinstance(observation.occurred, DateInterval):
        return "interval"
    if isinstance(observation.occurred, UnknownDate):
        return "unknown"
    raise AssertionError("unreachable")


def _case_ids():
    return list(load_corpus()["cases"].keys())


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_corpus()


@pytest.mark.parametrize("case_name", _case_ids())
def test_corpus_case(corpus: dict, case_name: str) -> None:
    case = corpus["cases"][case_name]
    observed_at = datetime.fromisoformat(corpus["observed_at"])
    run = CaseRun(case, observed_at)
    expect = case["expect"]

    assert run.qualifying_applications == expect["qualifying_applications"], case_name

    undocumented = undocumented_values(run.interpretations)
    assert undocumented == expect.get("undocumented", []), (case_name, undocumented)
    if expect.get("publication_must_fail"):
        assert undocumented, "expected fail-closed undocumented values"

    if "conflicts" in expect:
        assert len(run.conflicts) == expect["conflicts"], case_name
    if "retracted_count" in expect:
        assert len(run.revision.retracted) == expect["retracted_count"], case_name
    if "dangling_retractions" in expect:
        assert len(run.revision.dangling_retractions) == expect["dangling_retractions"]
    if "unjoined_permits" in expect:
        assert run.unjoined_permits == expect["unjoined_permits"], case_name
    if "orphan_inspections" in expect:
        assert run.orphan_inspections == expect["orphan_inspections"], case_name
    if "distinct_permit_subjects" in expect:
        permit_subjects = {
            o.subject.id
            for o in run.active
            if o.subject.type is SubjectType.PERMIT_APPLICATION
        }
        assert len(permit_subjects) == expect["distinct_permit_subjects"], case_name

    for apn, parcel_expect in expect.get("parcels", {}).items():
        state = run.parcel_state(apn)
        universe = run.parcel_observations(apn)
        for lane_name, signal in parcel_expect.get("lanes", {}).items():
            projection = state.lane(MilestoneLane(lane_name))
            assert projection.signal.value == signal, (
                case_name,
                apn,
                lane_name,
                projection.signal.value,
            )
        if "permitting_milestones" in parcel_expect:
            projection = state.lane(MilestoneLane.PERMITTING)
            assert list(projection.reached_milestones) == parcel_expect[
                "permitting_milestones"
            ], (case_name, apn)
        if "construction_reached" in parcel_expect:
            projection = state.lane(MilestoneLane.CONSTRUCTION)
            assert list(projection.reached_milestones) == parcel_expect[
                "construction_reached"
            ], (case_name, apn)
        for event_type, kind in parcel_expect.get("occurred_kinds", {}).items():
            matches = [
                o
                for o in universe
                if o.event_type == event_type and o.status.value != "conflicting"
            ]
            assert matches, (case_name, apn, event_type)
            assert {_occurred_kind(o) for o in matches} == {kind}, (
                case_name,
                apn,
                event_type,
            )
        if "context_event_types" in parcel_expect:
            context_ids = set(state.context_observation_ids)
            context_types = sorted(
                {o.event_type for o in universe if o.observation_id in context_ids}
            )
            assert context_types == sorted(parcel_expect["context_event_types"]), (
                case_name,
                apn,
                context_types,
            )
        for event_type, scheduled_for in parcel_expect.get("scheduled_for", {}).items():
            matches = [o for o in universe if o.event_type == event_type]
            assert matches, (case_name, apn, event_type)
            details = dict(matches[0].detail)
            assert details.get("scheduled_for") == scheduled_for, (case_name, apn)

    for forbidden in expect.get("forbidden_occurrence_dates", []):
        forbidden_date = date.fromisoformat(forbidden)
        for observation in run.active:
            if observation.event_type == "structure_destroyed":
                continue
            if isinstance(observation.occurred, ExactDate):
                assert observation.occurred.value != forbidden_date, (
                    case_name,
                    observation.event_type,
                    "fabricated exact occurrence date",
                )


# ---------------------------------------------------------------------------
# Independent reference implementation (differential reconciliation).
# Deliberately written from the documented rules, not from the domain code.
# ---------------------------------------------------------------------------

_IN_PROGRESS_STATUSES = {
    "plans submitted",
    "plan check in progress",
    "corrections issued",
    "application pending fees",
}
_APPROVED_STATUSES = {
    "plans approved & permit not issued",
    "plans approved & permit issued",
}


def _ref_normalize_apn(raw: object) -> str | None:
    digits = "".join(c for c in str(raw or "") if c.isdigit())
    return digits[:10] if len(digits) >= 10 else None


def independent_lane_signals(case: dict) -> dict[str, dict[str, str]]:
    """Second implementation of the lane-signal definitions over raw rows."""

    parcels: dict[str, dict[str, str]] = {}
    lanes = ("cleanup", "design_review", "permitting", "construction", "occupancy")

    def ensure(apn: str) -> dict[str, str]:
        return parcels.setdefault(apn, {lane: "no_public_evidence" for lane in lanes})

    def upgrade(apn: str, lane: str, signal: str) -> None:
        order = [
            "no_public_evidence",
            "activity_scheduled",
            "activity_attempted",
            "in_progress",
            "milestone_reached",
            "conflicting",
        ]
        current = ensure(apn)[lane]
        if order.index(signal) > order.index(current):
            parcels[apn][lane] = signal

    retracted_events = {
        (r.get("target_event_type"), r.get("target_subject"))
        for r in case.get("retractions", [])
        if r.get("target_event_type")
    }

    for row in case.get("county", []):
        apn = _ref_normalize_apn(row.get("APN"))
        if not apn:
            continue
        ensure(apn)
        roe = str(row.get("ROE_STATUS") or "").lower()
        if roe == "final sign off - complete" and (
            "debris_removal_complete",
            apn,
        ) not in retracted_events:
            upgrade(apn, "cleanup", "milestone_reached")
        progress = str(row.get("REBUILD_PROGRESS") or "").lower()
        if progress == "rebuild applications received":
            upgrade(apn, "permitting", "milestone_reached")
        elif progress == "building plans approved":
            upgrade(apn, "design_review", "milestone_reached")
        elif progress == "building permits issued":
            upgrade(apn, "permitting", "milestone_reached")
        elif progress == "construction completed":
            upgrade(apn, "construction", "milestone_reached")

    qualifying: dict[str, str] = {}
    issue_dates: dict[tuple[str, str], set[str]] = {}
    for row in case.get("permits", []):
        apn = _ref_normalize_apn(row.get("APN"))
        permit_no = str(row.get("PERMIT") or "").strip()
        ptype = str(row.get("PERMIT_TYPE") or "").lower()
        flag = str(row.get("PALISADES_WF_REBUILD") or "").lower()
        status = str(row.get("PERMIT_STATUS") or "").lower()
        if not apn or not permit_no:
            continue
        ensure(apn)
        if ptype == "bldg-new" and flag == "rebuild":
            qualifying[permit_no] = apn
            upgrade(apn, "permitting", "milestone_reached")  # submission asserted
            if row.get("PC_APPROVED_DATE_iso") or status in _APPROVED_STATUSES:
                upgrade(apn, "design_review", "milestone_reached")
            elif status in _IN_PROGRESS_STATUSES:
                upgrade(apn, "design_review", "in_progress")
            if row.get("ISSUE_DATE_iso") or status == "plans approved & permit issued":
                if row.get("ISSUE_DATE_iso"):
                    issue_dates.setdefault((permit_no, "issue"), set()).add(
                        row["ISSUE_DATE_iso"]
                    )
            if row.get("COFO_DATE_iso"):
                upgrade(apn, "occupancy", "milestone_reached")

    for (permit_no, _), dates in issue_dates.items():
        if len(dates) > 1:
            upgrade(qualifying[permit_no], "permitting", "conflicting")

    for row in case.get("inspections", []):
        permit_no = str(row.get("PERMIT") or "").strip()
        status = str(row.get("INSP_STATUS") or "").lower()
        apn = qualifying.get(permit_no)
        if apn and status == "insp scheduled":
            upgrade(apn, "construction", "activity_scheduled")

    for row in case.get("malibu", []):
        apn = _ref_normalize_apn(row.get("apn"))
        shape = str(row.get("iconShape") or "").lower()
        if not apn or apn not in parcels:
            continue
        if shape == "permitissued":
            upgrade(apn, "permitting", "milestone_reached")
        elif shape in ("inplanning", "pendingbsreview", "inbpc"):
            upgrade(apn, "design_review", "in_progress")

    return parcels


@pytest.mark.parametrize("case_name", _case_ids())
def test_independent_implementation_agrees(corpus: dict, case_name: str) -> None:
    case = corpus["cases"][case_name]
    if case["expect"].get("publication_must_fail"):
        pytest.skip("undocumented-domain case: production emits nothing by design")
    observed_at = datetime.fromisoformat(corpus["observed_at"])
    run = CaseRun(case, observed_at)
    reference = independent_lane_signals(case)
    for apn, expected_lanes in reference.items():
        state = run.parcel_state(apn)
        production = {
            projection.lane.value: projection.signal.value for projection in state.lanes
        }
        assert production == expected_lanes, (case_name, apn, production, expected_lanes)
