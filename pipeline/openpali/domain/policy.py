"""Versioned qualification policies.

The qualifying fire-rebuild application cohort is the load-bearing population
for permitting-lane milestones, community metrics, and the first ML target.

Evidence basis (state/evidence/domain-probe-2026-07-11.json):
``PALISADES_WF_REBUILD='Rebuild'`` marks rebuild-RELATED permits of many types
(Grading, Bldg-Alter/Repair, ...), so the flag alone is not a primary-rebuild
definition. A qualifying primary rebuild application is
``PERMIT_TYPE='Bldg-New' AND PALISADES_WF_REBUILD='Rebuild'`` (1,135 records on
2026-07-11). ``Bldg-New`` with flag ``No`` (750 records) is explicitly NOT a
fire rebuild and must not advance a destroyed parcel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .taxonomy import (
    Interpretation,
    PermitClass,
    RebuildFlag,
    interpret_permit_type,
    interpret_rebuild_flag,
)

QUALIFYING_REBUILD_POLICY_VERSION = "qualifying-rebuild-v1"


class PermitQualification(str, Enum):
    QUALIFYING_REBUILD_APPLICATION = "qualifying_rebuild_application"
    REBUILD_RELATED_ANCILLARY = "rebuild_related_ancillary"
    NOT_FIRE_REBUILD = "not_fire_rebuild"
    FLAG_MISSING = "flag_missing"
    UNDOCUMENTED = "undocumented"


@dataclass(frozen=True, slots=True)
class PermitClassification:
    qualification: PermitQualification
    permit_type: Interpretation
    rebuild_flag: Interpretation
    policy_version: str = QUALIFYING_REBUILD_POLICY_VERSION

    @property
    def documented(self) -> bool:
        return self.permit_type.documented and self.rebuild_flag.documented

    def to_json(self) -> dict:
        return {
            "qualification": self.qualification.value,
            "permit_type": self.permit_type.to_json(),
            "rebuild_flag": self.rebuild_flag.to_json(),
            "policy_version": self.policy_version,
        }


def classify_permit(permit_type: object, rebuild_flag: object) -> PermitClassification:
    """Decide whether one permit record can carry rebuild-lane milestones.

    Fail-closed rules:
    - undocumented permit type or flag value -> UNDOCUMENTED (blocks publication);
    - missing flag -> FLAG_MISSING (never qualifies; surfaced, not guessed);
    - ``Bldg-New`` + ``Rebuild`` -> qualifying application;
    - any other documented combination is evidence-only.
    """

    type_interpretation = interpret_permit_type(permit_type)
    flag_interpretation = interpret_rebuild_flag(rebuild_flag)

    if not type_interpretation.documented or not flag_interpretation.documented:
        qualification = PermitQualification.UNDOCUMENTED
    elif flag_interpretation.category == RebuildFlag.MISSING.value:
        qualification = PermitQualification.FLAG_MISSING
    elif (
        type_interpretation.category == PermitClass.NEW_BUILDING.value
        and flag_interpretation.category == RebuildFlag.REBUILD_RELATED.value
    ):
        qualification = PermitQualification.QUALIFYING_REBUILD_APPLICATION
    elif flag_interpretation.category == RebuildFlag.REBUILD_RELATED.value:
        qualification = PermitQualification.REBUILD_RELATED_ANCILLARY
    else:
        qualification = PermitQualification.NOT_FIRE_REBUILD

    return PermitClassification(
        qualification=qualification,
        permit_type=type_interpretation,
        rebuild_flag=flag_interpretation,
    )
