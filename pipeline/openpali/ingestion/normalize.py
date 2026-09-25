"""Pure normalization: raw source rows -> typed recovery observations.

These functions are the production semantics for every downstream artifact.
They are deliberately I/O-free so the golden fixture corpus exercises exactly
the code the platform runs. Invariants enforced here:

- scheduled/attempted/failed/canceled activity never yields a milestone;
- an inspection on a non-qualifying permit never touches the construction lane;
- a cleanup opt-out is a program choice, never completion;
- missing occurrence times stay unknown or interval-censored — the fire date,
  run date, and "today" never substitute for them;
- undocumented source values produce fail-closed interpretations, not guesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from palisades.apn import normalize_apn
from palisades.dates import from_epoch_ms, from_oracle

from openpali.domain.observations import (
    MilestoneLane,
    ObservationStatus,
    RecoveryObservation,
    SourceRecordRef,
    SubjectRef,
    SubjectType,
)
from openpali.domain.policy import (
    PermitClassification,
    PermitQualification,
    classify_permit,
)
from openpali.domain.taxonomy import (
    TAXONOMY_VERSION,
    CleanupAssertion,
    CountyProgressCategory,
    InspectionOutcomeCategory,
    Interpretation,
    PermitStatusCategory,
    interpret_county_progress,
    interpret_damage,
    interpret_dins_damage,
    interpret_inspection_status,
    interpret_malibu_marker,
    interpret_permit_status,
    interpret_roe_status,
)
from openpali.domain.temporal import (
    DateInterval,
    ExactDate,
    OccurrenceTime,
    UnknownDate,
    occurrence_from_source_date,
)

#: Palisades Fire start per CAL FIRE incident record (research/BRIEF.md).
#: Used ONLY as the earliest bound of the destruction interval — never as a
#: substitute for any missing recovery-event time.
PALISADES_FIRE_START = date(2025, 1, 7)

DERIVATION = TAXONOMY_VERSION


@dataclass(slots=True)
class NormalizedRecord:
    """Observations plus the interpretations that publication gates audit."""

    observations: list[RecoveryObservation] = field(default_factory=list)
    interpretations: list[Interpretation] = field(default_factory=list)

    def extend(self, other: "NormalizedRecord") -> None:
        self.observations.extend(other.observations)
        self.interpretations.extend(other.interpretations)

    @property
    def undocumented(self) -> list[Interpretation]:
        return [i for i in self.interpretations if not i.documented]


def _parcel_subject(apn: str) -> SubjectRef:
    return SubjectRef(SubjectType.PARCEL, apn)


def _permit_subject(permit_no: str) -> SubjectRef:
    return SubjectRef(SubjectType.PERMIT_APPLICATION, permit_no)


# ---------------------------------------------------------------------------
# County parcels / debris removal
# ---------------------------------------------------------------------------


def normalize_county_parcel(
    attrs: dict,
    *,
    observed_at: datetime,
    source_record: SourceRecordRef,
) -> NormalizedRecord:
    """County parcel row -> destruction, cleanup, and coarse progress evidence."""

    result = NormalizedRecord()
    apn = normalize_apn(attrs.get("APN") or attrs.get("AIN"))
    if not apn:
        return result
    subject = _parcel_subject(apn)

    damage = interpret_damage(attrs.get("DAMAGE"))
    result.interpretations.append(damage)
    if damage.documented and damage.category == "destroyed":
        result.observations.append(
            RecoveryObservation(
                subject=subject,
                lane=None,
                event_type="structure_destroyed",
                status=ObservationStatus.AGENCY_REPORTED,
                # Interval-censored: destroyed on or after the fire start and,
                # like every status-based assertion, no later than the time we
                # observed the assertion. The county row asserts no per-parcel
                # destruction date.
                occurred=DateInterval(PALISADES_FIRE_START, observed_at.date()),
                observed_at=observed_at,
                source_record=source_record,
                policy_version=DERIVATION,
                label="Structure destroyed in the Palisades Fire (county damage assessment)",
                detail=(("damage_raw", str(attrs.get("DAMAGE"))),),
            )
        )

    roe = interpret_roe_status(attrs.get("ROE_STATUS"))
    result.interpretations.append(roe)
    if roe.documented:
        if roe.category == CleanupAssertion.GOVERNMENT_CLEANUP_COMPLETE.value:
            fso_date = from_oracle(attrs.get("FSO_PKG_APPROVED_USACE"))
            result.observations.append(
                RecoveryObservation(
                    subject=subject,
                    lane=MilestoneLane.CLEANUP,
                    event_type="debris_removal_complete",
                    status=ObservationStatus.AGENCY_REPORTED,
                    occurred=occurrence_from_source_date(fso_date),
                    observed_at=observed_at,
                    source_record=source_record,
                    policy_version=DERIVATION,
                    label="Debris removal complete (government program final sign-off)",
                    detail=(("roe_status_raw", roe.raw or ""),),
                )
            )
        elif roe.category == CleanupAssertion.OPT_OUT_SELECTED.value:
            result.observations.append(
                RecoveryObservation(
                    subject=subject,
                    lane=MilestoneLane.CLEANUP,
                    event_type="cleanup_opt_out_selected",
                    status=ObservationStatus.AGENCY_REPORTED,
                    occurred=UnknownDate(),
                    observed_at=observed_at,
                    source_record=source_record,
                    policy_version=DERIVATION,
                    label=(
                        "Private cleanup path selected (opt-out) — completion "
                        "state unknown from public sources"
                    ),
                    detail=(("roe_status_raw", roe.raw or ""),),
                )
            )
        elif roe.category == CleanupAssertion.PROGRAM_INELIGIBLE.value:
            result.observations.append(
                RecoveryObservation(
                    subject=subject,
                    lane=MilestoneLane.CLEANUP,
                    event_type="cleanup_program_ineligible",
                    status=ObservationStatus.AGENCY_REPORTED,
                    occurred=UnknownDate(),
                    observed_at=observed_at,
                    source_record=source_record,
                    policy_version=DERIVATION,
                    label="Recorded ineligible for the government cleanup program",
                    detail=(("roe_status_raw", roe.raw or ""),),
                )
            )
        # NO_ROE / NO_ASSERTION: no observation — absence of evidence stays absent.

    progress = interpret_county_progress(attrs.get("REBUILD_PROGRESS"))
    result.interpretations.append(progress)
    if progress.documented and progress.category != "no_assertion":
        coarse_map = {
            CountyProgressCategory.APPLICATION_RECEIVED.value: (
                MilestoneLane.PERMITTING,
                "rebuild_application_submitted",
                "Rebuild application received (county dashboard, coarse)",
            ),
            CountyProgressCategory.PLANS_APPROVED.value: (
                MilestoneLane.DESIGN_REVIEW,
                "plan_check_approved",
                "Building plans approved (county dashboard, coarse)",
            ),
            CountyProgressCategory.PERMIT_ISSUED.value: (
                MilestoneLane.PERMITTING,
                "rebuild_permit_issued",
                "Building permit issued (county dashboard, coarse)",
            ),
            CountyProgressCategory.CONSTRUCTION_COMPLETED.value: (
                MilestoneLane.CONSTRUCTION,
                "construction_completed",
                "Construction completed (county dashboard, coarse)",
            ),
            CountyProgressCategory.CONSTRUCTION_IN_PROGRESS.value: (
                MilestoneLane.CONSTRUCTION,
                "construction_in_progress",
                "Construction in progress (county dashboard, coarse)",
            ),
        }
        lane, event_type, label = coarse_map[progress.category]
        result.observations.append(
            RecoveryObservation(
                subject=subject,
                lane=lane,
                event_type=event_type,
                status=ObservationStatus.AGENCY_REPORTED,
                occurred=UnknownDate(),
                observed_at=observed_at,
                source_record=source_record,
                policy_version=DERIVATION,
                label=label,
                detail=(
                    ("coarse", "true"),
                    ("source_field", "REBUILD_PROGRESS"),
                    ("progress_raw", progress.raw or ""),
                ),
            )
        )
    return result


# ---------------------------------------------------------------------------
# LADBS permits
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NormalizedPermit(NormalizedRecord):
    """Permit normalization plus its qualification for downstream joins."""

    permit_no: str = ""
    apn: str | None = None
    classification: PermitClassification | None = None


def normalize_ladbs_permit(
    attrs: dict,
    *,
    observed_at: datetime,
    source_record: SourceRecordRef,
) -> NormalizedPermit:
    result = NormalizedPermit()
    permit_no = str(attrs.get("PERMIT") or "").strip()
    apn = normalize_apn(attrs.get("APN"))
    result.permit_no = permit_no
    result.apn = apn

    classification = classify_permit(
        attrs.get("PERMIT_TYPE"), attrs.get("PALISADES_WF_REBUILD")
    )
    result.classification = classification
    result.interpretations.append(classification.permit_type)
    result.interpretations.append(classification.rebuild_flag)

    status = interpret_permit_status(attrs.get("PERMIT_STATUS"))
    result.interpretations.append(status)

    if not permit_no or not apn:
        return result

    subject = _permit_subject(permit_no)
    parcel = _parcel_subject(apn)
    related = (parcel,)
    submit = from_epoch_ms(attrs.get("SUBMIT_DATE"))
    pc_approved = from_epoch_ms(attrs.get("PC_APPROVED_DATE"))
    issue = from_epoch_ms(attrs.get("ISSUE_DATE"))
    cofo = from_epoch_ms(attrs.get("COFO_DATE"))
    status_date = from_epoch_ms(attrs.get("STATUS_DATE"))

    def observation(
        lane: MilestoneLane | None,
        event_type: str,
        obs_status: ObservationStatus,
        occurred: OccurrenceTime,
        label: str,
        detail: tuple[tuple[str, str], ...] = (),
    ) -> RecoveryObservation:
        return RecoveryObservation(
            subject=subject,
            lane=lane,
            event_type=event_type,
            status=obs_status,
            occurred=occurred,
            observed_at=observed_at,
            source_record=source_record,
            policy_version=classification.policy_version,
            label=label,
            related_subjects=related,
            detail=detail
            + (
                ("permit_type_raw", classification.permit_type.raw or ""),
                ("rebuild_flag_raw", classification.rebuild_flag.raw or ""),
                ("permit_status_raw", status.raw or ""),
            ),
        )

    qualification = classification.qualification
    if qualification is PermitQualification.QUALIFYING_REBUILD_APPLICATION:
        result.observations.append(
            observation(
                MilestoneLane.PERMITTING,
                "rebuild_application_submitted",
                ObservationStatus.AGENCY_REPORTED,
                occurrence_from_source_date(submit),
                "Qualifying rebuild application submitted",
            )
        )
        if pc_approved is not None:
            result.observations.append(
                observation(
                    MilestoneLane.DESIGN_REVIEW,
                    "plan_check_approved",
                    ObservationStatus.AGENCY_REPORTED,
                    ExactDate(pc_approved),
                    "Plan check approved",
                )
            )
        elif status.documented and status.category in (
            PermitStatusCategory.APPROVED_NOT_ISSUED.value,
            PermitStatusCategory.APPROVED_AND_ISSUED.value,
        ):
            # Status asserts approval without a plan-check date: the approval
            # happened by the observation time — interval-censored, never "today".
            result.observations.append(
                observation(
                    MilestoneLane.DESIGN_REVIEW,
                    "plan_check_approved",
                    ObservationStatus.AGENCY_REPORTED,
                    DateInterval(submit, observed_at.date()),
                    "Plan check approved (asserted by permit status; date unknown)",
                    detail=(("date_basis", "status_assertion"),),
                )
            )
        if issue is not None:
            result.observations.append(
                observation(
                    MilestoneLane.PERMITTING,
                    "rebuild_permit_issued",
                    ObservationStatus.ISSUED,
                    ExactDate(issue),
                    "Rebuild building permit issued",
                )
            )
        elif status.documented and status.category == PermitStatusCategory.APPROVED_AND_ISSUED.value:
            result.observations.append(
                observation(
                    MilestoneLane.PERMITTING,
                    "rebuild_permit_issued",
                    ObservationStatus.ISSUED,
                    DateInterval(submit, observed_at.date()),
                    "Rebuild building permit issued (asserted by permit status; date unknown)",
                    detail=(("date_basis", "status_assertion"),),
                )
            )
        if cofo is not None:
            result.observations.append(
                observation(
                    MilestoneLane.OCCUPANCY,
                    "certificate_of_occupancy_issued",
                    ObservationStatus.ISSUED,
                    ExactDate(cofo),
                    "Certificate of Occupancy issued",
                )
            )
        if status.documented and status.category in (
            PermitStatusCategory.PLANS_SUBMITTED.value,
            PermitStatusCategory.PLAN_CHECK_IN_PROGRESS.value,
            PermitStatusCategory.CORRECTIONS_ISSUED.value,
            PermitStatusCategory.APPLICATION_PENDING_FEES.value,
        ):
            result.observations.append(
                observation(
                    MilestoneLane.DESIGN_REVIEW,
                    status.category,
                    ObservationStatus.AGENCY_REPORTED,
                    occurrence_from_source_date(status_date),
                    f"Design review status: {status.raw}",
                )
            )
    elif qualification is PermitQualification.REBUILD_RELATED_ANCILLARY:
        earliest = min((d for d in (submit, issue) if d is not None), default=None)
        result.observations.append(
            observation(
                None,
                "ancillary_permit_activity",
                ObservationStatus.AGENCY_REPORTED,
                occurrence_from_source_date(earliest),
                f"Rebuild-related {classification.permit_type.raw} permit activity",
            )
        )
    elif qualification is PermitQualification.NOT_FIRE_REBUILD:
        earliest = min((d for d in (submit, issue) if d is not None), default=None)
        result.observations.append(
            observation(
                None,
                "non_rebuild_permit_activity",
                ObservationStatus.AGENCY_REPORTED,
                occurrence_from_source_date(earliest),
                f"{classification.permit_type.raw} permit activity (not flagged as fire rebuild)",
            )
        )
    elif qualification is PermitQualification.FLAG_MISSING:
        # Distinct event type: "the rebuild flag is absent" is surfaced as its
        # own fact, never silently merged with an explicit 'No'.
        earliest = min((d for d in (submit, issue) if d is not None), default=None)
        result.observations.append(
            observation(
                None,
                "permit_activity_flag_missing",
                ObservationStatus.AGENCY_REPORTED,
                occurrence_from_source_date(earliest),
                f"{classification.permit_type.raw} permit activity (rebuild flag missing from source)",
            )
        )
    # UNDOCUMENTED: no observations; the interpretations fail publication closed.
    return result


# ---------------------------------------------------------------------------
# LADBS wildfire inspections
# ---------------------------------------------------------------------------


def normalize_ladbs_inspection(
    attrs: dict,
    *,
    observed_at: datetime,
    source_record: SourceRecordRef,
    permit_classifications: dict[str, PermitClassification],
    permit_to_apn: dict[str, str],
) -> NormalizedRecord:
    """Inspection row -> outcome-aware observation.

    The full public INSP_STATUS domain today is exactly {'Insp Scheduled'}, so
    live data can only ever produce SCHEDULED activity. The PASSED/FAILED/
    CANCELED paths below are exercised by fixtures and guard future taxonomy
    expansion; they only take effect when the documented domain grows.
    """

    result = NormalizedRecord()
    permit_no = str(attrs.get("PERMIT") or "").strip()
    interpretation = interpret_inspection_status(attrs.get("INSP_STATUS"))
    result.interpretations.append(interpretation)
    if not permit_no or not interpretation.documented:
        return result

    apn = permit_to_apn.get(permit_no)
    classification = permit_classifications.get(permit_no)
    qualifying = (
        classification is not None
        and classification.qualification
        is PermitQualification.QUALIFYING_REBUILD_APPLICATION
    )
    insp_date = from_epoch_ms(attrs.get("INSP_DT"))
    insp_desc = str(attrs.get("INSP_DESC") or "").strip()
    subject = _permit_subject(permit_no)
    related = (_parcel_subject(apn),) if apn else ()

    status_map = {
        InspectionOutcomeCategory.SCHEDULED.value: ObservationStatus.SCHEDULED,
        InspectionOutcomeCategory.PASSED.value: ObservationStatus.PASSED,
        InspectionOutcomeCategory.PARTIAL.value: ObservationStatus.ATTEMPTED,
        InspectionOutcomeCategory.FAILED.value: ObservationStatus.FAILED,
        InspectionOutcomeCategory.NOT_READY.value: ObservationStatus.ATTEMPTED,
        InspectionOutcomeCategory.CANCELED.value: ObservationStatus.CANCELED,
    }
    obs_status = status_map.get(interpretation.category)
    if obs_status is None:
        return result

    if obs_status is ObservationStatus.SCHEDULED:
        # A scheduling assertion: the inspection has NOT occurred. The
        # scheduled-for date is an attribute, never an occurrence time.
        occurred: OccurrenceTime = UnknownDate()
        detail: tuple[tuple[str, str], ...] = (
            ("scheduled_for", insp_date.isoformat() if insp_date else ""),
            ("insp_desc", insp_desc),
            ("insp_status_raw", interpretation.raw or ""),
        )
        label = f"Inspection scheduled: {insp_desc}" if insp_desc else "Inspection scheduled"
    else:
        occurred = occurrence_from_source_date(insp_date)
        detail = (
            ("insp_desc", insp_desc),
            ("insp_status_raw", interpretation.raw or ""),
        )
        label = f"Inspection {interpretation.category}: {insp_desc}".strip()

    if qualifying:
        event_type = (
            "construction_inspection_passed"
            if obs_status is ObservationStatus.PASSED
            else "construction_inspection_activity"
        )
        lane: MilestoneLane | None = MilestoneLane.CONSTRUCTION
    else:
        event_type = "inspection_activity"
        lane = None

    result.observations.append(
        RecoveryObservation(
            subject=subject,
            lane=lane,
            event_type=event_type,
            status=obs_status,
            occurred=occurred,
            observed_at=observed_at,
            source_record=source_record,
            policy_version=DERIVATION,
            label=label,
            related_subjects=related,
            detail=detail,
            # One permit can carry several same-typed inspection assertions
            # (e.g. Foundation and Frame both scheduled): the description and
            # source date discriminate their deterministic IDs.
            discriminator=f"{insp_desc}|{insp_date.isoformat() if insp_date else ''}",
        )
    )
    return result


# ---------------------------------------------------------------------------
# CAL FIRE DINS structure damage assessments
# ---------------------------------------------------------------------------


def normalize_dins_structure(
    attrs: dict,
    *,
    observed_at: datetime,
    source_record: SourceRecordRef,
) -> NormalizedRecord:
    """One DINS record -> a structure-level damage assessment observation.

    DINS is structure-level, never parcel-level: a parcel can carry several
    assessed structures, and DINS counts are never compared directly with
    parcel counts. The public layer exposes no per-structure assessment date,
    so the occurrence is interval-censored [incident start, observed].
    """

    result = NormalizedRecord()
    global_id = str(attrs.get("GLOBALID") or "").strip()
    if not global_id:
        return result
    damage = interpret_dins_damage(attrs.get("DAMAGE"))
    result.interpretations.append(damage)
    if not damage.documented:
        return result

    incident_start = from_epoch_ms(attrs.get("INCIDENTSTARTDATE"))
    subject = SubjectRef(SubjectType.STRUCTURE, f"dins-{global_id}")
    apn = normalize_apn(attrs.get("APN"))
    related = (_parcel_subject(apn),) if apn else ()

    occurred: OccurrenceTime
    if incident_start is not None:
        occurred = DateInterval(incident_start, observed_at.date())
    else:
        occurred = DateInterval(None, observed_at.date())

    result.observations.append(
        RecoveryObservation(
            subject=subject,
            lane=None,
            event_type="structure_damage_assessed",
            status=ObservationStatus.AGENCY_REPORTED,
            occurred=occurred,
            observed_at=observed_at,
            source_record=source_record,
            policy_version=DERIVATION,
            label=(
                f"DINS damage assessment: {damage.raw} "
                f"({attrs.get('STRUCTURETYPE') or 'structure'})"
            ),
            related_subjects=related,
            detail=(
                ("damage_raw", damage.raw or ""),
                ("damage_category", damage.category),
                ("structure_type", str(attrs.get("STRUCTURETYPE") or "")),
                ("structure_category", str(attrs.get("STRUCTURECATEGORY") or "")),
                ("site_address", str(attrs.get("SITEADDRESS") or "")),
                ("city", str(attrs.get("CITY") or "")),
            ),
            discriminator=global_id,
        )
    )
    return result


# ---------------------------------------------------------------------------
# Malibu dashboard markers
# ---------------------------------------------------------------------------


def normalize_malibu_marker(
    row: dict,
    *,
    observed_at: datetime,
    source_record: SourceRecordRef,
) -> NormalizedRecord:
    result = NormalizedRecord()
    apn = normalize_apn(row.get("apn"))
    interpretation = interpret_malibu_marker(row.get("iconShape"))
    result.interpretations.append(interpretation)
    if not apn or not interpretation.documented:
        return result
    subject = _parcel_subject(apn)
    common_detail = (
        ("coarse", "true"),
        ("feed", "malibu_dashboard_marker_endpoint"),
        ("icon_shape_raw", interpretation.raw or ""),
    )
    if interpretation.category == "permit_issued":
        result.observations.append(
            RecoveryObservation(
                subject=subject,
                lane=MilestoneLane.PERMITTING,
                event_type="rebuild_permit_issued",
                status=ObservationStatus.AGENCY_REPORTED,
                occurred=UnknownDate(),
                observed_at=observed_at,
                source_record=source_record,
                policy_version=DERIVATION,
                label="Rebuild permit issued (Malibu dashboard, coarse)",
                detail=common_detail,
            )
        )
    else:
        result.observations.append(
            RecoveryObservation(
                subject=subject,
                lane=MilestoneLane.DESIGN_REVIEW,
                event_type="plan_check_in_progress",
                status=ObservationStatus.AGENCY_REPORTED,
                occurred=UnknownDate(),
                observed_at=observed_at,
                source_record=source_record,
                policy_version=DERIVATION,
                label=f"Malibu review status: {interpretation.raw} (coarse)",
                detail=common_detail,
            )
        )
    return result
