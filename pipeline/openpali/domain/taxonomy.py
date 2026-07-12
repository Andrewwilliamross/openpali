"""Source-value taxonomy: documented domains and fail-closed interpretation.

Every mapping here is backed by primary-source evidence recorded in the
``EVIDENCE`` registry and in
``openpali-one-shot/state/evidence/domain-probe-2026-07-11.json`` (live groupBy
statistics + layer metadata retrieved 2026-07-11 through the cached adapter,
raw bytes in ``data/raw`` with sha256 provenance). A raw value outside the
documented domain interprets as UNDOCUMENTED; publication gates fail closed on
any UNDOCUMENTED occurrence (MISSION.md phase 0).

The interpreters never guess: reachability of an endpoint is not field
meaning, and a plausible-looking string is not a documented semantic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Version stamp for observation derivation; bump when any mapping changes.
TAXONOMY_VERSION = "taxonomy-v1"


@dataclass(frozen=True, slots=True)
class DomainEvidence:
    """Where a documented value set came from."""

    source_id: str
    field: str
    verified_on: str
    method: str
    reference: str


class InspectionOutcomeCategory(str, Enum):
    SCHEDULED = "scheduled"
    PASSED = "passed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELED = "canceled"
    NOT_READY = "not_ready"
    UNDOCUMENTED = "undocumented"


class PermitClass(str, Enum):
    NEW_BUILDING = "new_building"
    ANCILLARY = "ancillary"
    UNDOCUMENTED = "undocumented"


class RebuildFlag(str, Enum):
    REBUILD_RELATED = "rebuild_related"
    NOT_REBUILD = "not_rebuild"
    MISSING = "missing"
    UNDOCUMENTED = "undocumented"


class CleanupAssertion(str, Enum):
    GOVERNMENT_CLEANUP_COMPLETE = "government_cleanup_complete"
    OPT_OUT_SELECTED = "opt_out_selected"
    PROGRAM_INELIGIBLE = "program_ineligible"
    NO_ROE = "no_roe"
    NO_ASSERTION = "no_assertion"
    UNDOCUMENTED = "undocumented"


class PermitStatusCategory(str, Enum):
    """LADBS PERMIT_STATUS lifecycle categories (documented full domain)."""

    PLANS_SUBMITTED = "plans_submitted"
    PLAN_CHECK_IN_PROGRESS = "plan_check_in_progress"
    CORRECTIONS_ISSUED = "corrections_issued"
    APPLICATION_PENDING_FEES = "application_pending_fees"
    APPROVED_NOT_ISSUED = "approved_not_issued"
    APPROVED_AND_ISSUED = "approved_and_issued"
    UNDOCUMENTED = "undocumented"


class CountyProgressCategory(str, Enum):
    """County REBUILD_PROGRESS coarse assertions (unincorporated parcels)."""

    APPLICATION_RECEIVED = "application_received"
    PLANS_APPROVED = "plans_approved"
    PERMIT_ISSUED = "permit_issued"
    CONSTRUCTION_COMPLETED = "construction_completed"
    UNDOCUMENTED = "undocumented"


@dataclass(frozen=True, slots=True)
class Interpretation:
    """Typed result of interpreting one raw source value."""

    raw: str | None
    documented: bool
    category: str

    def to_json(self) -> dict:
        return {"raw": self.raw, "documented": self.documented, "category": self.category}


# ---------------------------------------------------------------------------
# Documented domains. Populated ONLY from recorded primary-source evidence.
# A deliberately partial map means "not yet documented" and everything outside
# it fails closed — that is intended behavior, not a stub.
# ---------------------------------------------------------------------------

EVIDENCE: list[DomainEvidence] = [
    DomainEvidence(
        source_id="ladbs_inspections",
        field="INSP_STATUS",
        verified_on="2026-07-11",
        method="live groupBy statistics on both public endpoints (lahub MapServer/4 and services5 FeatureServer/0)",
        reference="state/evidence/domain-probe-2026-07-11.json: only 'Insp Scheduled' (1,014 rows) exists; the public table exposes no completed/passed/failed outcome at all",
    ),
    DomainEvidence(
        source_id="ladbs_permits",
        field="PALISADES_WF_REBUILD",
        verified_on="2026-07-11",
        method="live groupBy statistics; cross-tab against PERMIT_TYPE",
        reference="state/evidence/domain-probe-2026-07-11.json: domain {'Rebuild': 1939, 'No': 3392}; 'Rebuild' spans many permit types (Grading 699, Bldg-Alter/Repair 67, Bldg-Addition 32, ...) so it flags rebuild-RELATED work, not the primary dwelling permit",
    ),
    DomainEvidence(
        source_id="ladbs_permits",
        field="PERMIT_TYPE",
        verified_on="2026-07-11",
        method="live groupBy statistics (16 values)",
        reference="state/evidence/domain-probe-2026-07-11.json",
    ),
    DomainEvidence(
        source_id="ladbs_permits",
        field="PERMIT_STATUS",
        verified_on="2026-07-11",
        method="live groupBy statistics (6 values)",
        reference="state/evidence/domain-probe-2026-07-11.json",
    ),
    DomainEvidence(
        source_id="county_base",
        field="ROE_STATUS",
        verified_on="2026-07-11",
        method="live groupBy statistics, FIRE_NAME='Palisades'",
        reference="state/evidence/domain-probe-2026-07-11.json; recovery.lacounty.gov debris guidance distinguishes government cleanup from private opt-out",
    ),
    DomainEvidence(
        source_id="county_base",
        field="REBUILD_PROGRESS",
        verified_on="2026-07-11",
        method="live groupBy statistics, FIRE_NAME='Palisades' (4 values)",
        reference="state/evidence/domain-probe-2026-07-11.json",
    ),
    DomainEvidence(
        source_id="county_base",
        field="DAMAGE",
        verified_on="2026-07-11",
        method="live groupBy statistics, FIRE_NAME='Palisades' (6 values)",
        reference="state/evidence/domain-probe-2026-07-11.json",
    ),
]

#: LADBS wildfire inspection INSP_STATUS -> outcome category. The full observed
#: public domain is exactly one value; anything else is a schema/domain change
#: that must fail closed until documented.
INSP_STATUS_DOMAIN: dict[str, InspectionOutcomeCategory] = {
    "insp scheduled": InspectionOutcomeCategory.SCHEDULED,
}

#: LADBS PERMIT_TYPE -> permit class (full documented domain, 2026-07-11).
PERMIT_TYPE_DOMAIN: dict[str, PermitClass] = {
    "bldg-new": PermitClass.NEW_BUILDING,
    "grading": PermitClass.ANCILLARY,
    "nonbldg-new": PermitClass.ANCILLARY,
    "bldg-alter/repair": PermitClass.ANCILLARY,
    "fire sprinkler": PermitClass.ANCILLARY,
    "swimming-pool/spa": PermitClass.ANCILLARY,
    "plumbing": PermitClass.ANCILLARY,
    "bldg-addition": PermitClass.ANCILLARY,
    "electrical": PermitClass.ANCILLARY,
    "bldg-demolition": PermitClass.ANCILLARY,
    "nonbldg-alter/repair": PermitClass.ANCILLARY,
    "hvac": PermitClass.ANCILLARY,
    "elevator": PermitClass.ANCILLARY,
    "sign": PermitClass.ANCILLARY,
    "nonbldg-addition": PermitClass.ANCILLARY,
    "nonbldg-demolition": PermitClass.ANCILLARY,
}

#: PALISADES_WF_REBUILD coded values (full documented domain, 2026-07-11).
PALISADES_WF_REBUILD_DOMAIN: dict[str, RebuildFlag] = {
    "rebuild": RebuildFlag.REBUILD_RELATED,
    "no": RebuildFlag.NOT_REBUILD,
}

#: LADBS PERMIT_STATUS (full documented domain, 2026-07-11).
PERMIT_STATUS_DOMAIN: dict[str, PermitStatusCategory] = {
    "plans submitted": PermitStatusCategory.PLANS_SUBMITTED,
    "plan check in progress": PermitStatusCategory.PLAN_CHECK_IN_PROGRESS,
    "corrections issued": PermitStatusCategory.CORRECTIONS_ISSUED,
    "application pending fees": PermitStatusCategory.APPLICATION_PENDING_FEES,
    "plans approved & permit not issued": PermitStatusCategory.APPROVED_NOT_ISSUED,
    "plans approved & permit issued": PermitStatusCategory.APPROVED_AND_ISSUED,
}

#: County ROE_STATUS (full documented domain, 2026-07-11). Only the completed
#: government final sign-off asserts finished debris removal. Opt-out selects a
#: private cleanup path and asserts nothing about completion. Ineligibility
#: assertions are program facts, not cleanup facts.
ROE_STATUS_DOMAIN: dict[str, CleanupAssertion] = {
    "final sign off - complete": CleanupAssertion.GOVERNMENT_CLEANUP_COMPLETE,
    "opt-out and manage cleanup independently": CleanupAssertion.OPT_OUT_SELECTED,
    "non-responsive opt-out": CleanupAssertion.OPT_OUT_SELECTED,
    "final sign off - ineligible": CleanupAssertion.PROGRAM_INELIGIBLE,
    "fema ineligible": CleanupAssertion.PROGRAM_INELIGIBLE,
    "no roe": CleanupAssertion.NO_ROE,
}

#: County REBUILD_PROGRESS (full documented domain, 2026-07-11).
COUNTY_REBUILD_PROGRESS_DOMAIN: dict[str, CountyProgressCategory] = {
    "rebuild applications received": CountyProgressCategory.APPLICATION_RECEIVED,
    "building plans approved": CountyProgressCategory.PLANS_APPROVED,
    "building permits issued": CountyProgressCategory.PERMIT_ISSUED,
    "construction completed": CountyProgressCategory.CONSTRUCTION_COMPLETED,
}

#: Malibu dashboard marker iconShape (full observed domain, live 2026-07-11,
#: 269 rows; see state/evidence/domain-probe-supplement-2026-07-11.md). The
#: feed is an undocumented internal endpoint of the official city dashboard;
#: derived observations must carry a coarse/unofficial-feed detail flag.
MALIBU_MARKER_DOMAIN: dict[str, str] = {
    "inplanning": "in_planning",
    "pendingbsreview": "pending_building_safety_review",
    "inbpc": "in_building_plan_check",
    "permitissued": "permit_issued",
}

#: County DEBRIS_CLEARED observed domain ('Yes' 308 / 'NA' 12,075 on
#: 2026-07-11). Its relationship to the ROE program is NOT documented, so it
#: is recorded but never milestone-bearing (see supplement evidence file).
DEBRIS_CLEARED_DOMAIN: dict[str, str] = {
    "yes": "asserted_cleared_undefined_program",
    "na": "not_applicable_or_unknown",
}

#: County DAMAGE classes (full documented domain, 2026-07-11).
DAMAGE_DOMAIN: dict[str, str] = {
    "destroyed (>50%)": "destroyed",
    "major (26-50%)": "major",
    "minor (10-25%)": "minor",
    "affected (1-9%)": "affected",
    "no damage": "no_damage",
    "no data/vacant": "no_data",
}


def _norm(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def _interpret(
    value: object,
    domain: dict[str, Enum],
    *,
    missing_category: Enum | None = None,
    undocumented_category: Enum,
) -> Interpretation:
    normalized = _norm(value)
    if normalized is None:
        if missing_category is not None:
            return Interpretation(raw=None, documented=True, category=missing_category.value)
        return Interpretation(raw=None, documented=False, category=undocumented_category.value)
    category = domain.get(normalized)
    if category is None:
        return Interpretation(
            raw=str(value), documented=False, category=undocumented_category.value
        )
    return Interpretation(raw=str(value), documented=True, category=category.value)


def interpret_inspection_status(value: object) -> Interpretation:
    return _interpret(
        value,
        INSP_STATUS_DOMAIN,
        undocumented_category=InspectionOutcomeCategory.UNDOCUMENTED,
    )


def interpret_permit_type(value: object) -> Interpretation:
    return _interpret(
        value,
        PERMIT_TYPE_DOMAIN,
        undocumented_category=PermitClass.UNDOCUMENTED,
    )


def interpret_rebuild_flag(value: object) -> Interpretation:
    return _interpret(
        value,
        PALISADES_WF_REBUILD_DOMAIN,
        missing_category=RebuildFlag.MISSING,
        undocumented_category=RebuildFlag.UNDOCUMENTED,
    )


def interpret_permit_status(value: object) -> Interpretation:
    return _interpret(
        value,
        PERMIT_STATUS_DOMAIN,
        undocumented_category=PermitStatusCategory.UNDOCUMENTED,
    )


def interpret_roe_status(value: object) -> Interpretation:
    return _interpret(
        value,
        ROE_STATUS_DOMAIN,
        missing_category=CleanupAssertion.NO_ASSERTION,
        undocumented_category=CleanupAssertion.UNDOCUMENTED,
    )


def interpret_county_progress(value: object) -> Interpretation:
    normalized = _norm(value)
    if normalized is None:
        return Interpretation(raw=None, documented=True, category="no_assertion")
    category = COUNTY_REBUILD_PROGRESS_DOMAIN.get(normalized)
    if category is None:
        return Interpretation(
            raw=str(value), documented=False, category=CountyProgressCategory.UNDOCUMENTED.value
        )
    return Interpretation(raw=str(value), documented=True, category=category.value)


def interpret_malibu_marker(value: object) -> Interpretation:
    normalized = _norm(value)
    if normalized is None:
        return Interpretation(raw=None, documented=False, category="undocumented")
    category = MALIBU_MARKER_DOMAIN.get(normalized)
    if category is None:
        return Interpretation(raw=str(value), documented=False, category="undocumented")
    return Interpretation(raw=str(value), documented=True, category=category)


def interpret_damage(value: object) -> Interpretation:
    normalized = _norm(value)
    if normalized is None:
        return Interpretation(raw=None, documented=False, category="undocumented")
    category = DAMAGE_DOMAIN.get(normalized)
    if category is None:
        return Interpretation(raw=str(value), documented=False, category="undocumented")
    return Interpretation(raw=str(value), documented=True, category=category)


def undocumented_values(interpretations: list[Interpretation]) -> list[str]:
    """Collect raw values that must block publication."""

    return sorted({i.raw or "<null>" for i in interpretations if not i.documented})
