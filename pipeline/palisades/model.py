"""Normalized domain model — every source is reduced to these shapes before scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# Event kinds, in pipeline order. An event's kind determines the stage it unlocks.
KIND_STAGE = {
    "destroyed": 0,
    "debris_cleared": 1,
    "permit_submitted": 2,
    "permit_issued": 3,
    "inspection": 4,
    "cofo": 5,
}

STAGE_LABELS = {
    0: "No activity",
    1: "Lot cleared",
    2: "Plan check",
    3: "Permitted",
    4: "Under construction",
    5: "Complete",
}

# score bands per stage (see Docs/initialbuild_docs/METHODOLOGY.md)
STAGE_BANDS: dict[int, tuple[float, float]] = {
    0: (0, 7),
    1: (8, 14),
    2: (15, 39),
    3: (40, 49),
    4: (50, 92),
    5: (100, 100),
}

# construction milestone → progress fraction within the stage-4 band
INSPECTION_MILESTONES: list[tuple[str, float]] = [
    ("foundation", 0.15),
    ("framing", 0.40),
    ("mep", 0.58),
    ("insulation_drywall", 0.73),
    ("final", 0.88),
]

# LADBS inspection description (INSP_DESC) → construction milestone.
# Checked most-advanced-first so a "Final" beats a "Footing" on the same lot.
_MILESTONE_RULES: list[tuple[str, list[str]]] = [
    ("final", ["final", "smoke detector", "service/power release", "tco ", "sgsov",
               "fire sprinkler verification", "gas test"]),
    ("insulation_drywall", ["insulation", "drywall", "lathing"]),
    ("mep", ["rough", "plumbing", "electrical", "hvac", "mechanical", "grounding",
             "overhead hydro", "sewer", "underground"]),
    ("framing", ["frame", "diaphrgm", "shear wall", "structural steel", "masonry frame",
                 "light gage", "green building rough"]),
    ("foundation", ["footing", "foundation", "slab", "excavation", "setback", "re-bar",
                    "rebar", "pile", "pier", "caisson", "gunite", "compaction", "grading",
                    "backfill", "sub-drain", "drainage", "bottom/toe", "shotcrete",
                    "reinf. concrete", "reinforced concrete", "anchors", "deputy"]),
]


def classify_milestone(insp_desc: str | None) -> str | None:
    """Map an LADBS INSP_DESC string to a construction milestone, or None."""
    if not insp_desc:
        return None
    d = insp_desc.lower()
    for milestone, needles in _MILESTONE_RULES:
        if any(n in d for n in needles):
            return milestone
    return None


@dataclass
class Event:
    date: date
    kind: str  # KIND_STAGE key
    label: str
    ref: str | None = None
    milestone: str | None = None  # for inspections: foundation/framing/mep/...

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"date": self.date.isoformat(), "kind": self.kind, "label": self.label}
        if self.ref:
            out["ref"] = self.ref
        return out


@dataclass
class Permit:
    no: str
    type: str
    status: str
    submitted: date | None
    issued: date | None
    valuation: float | None
    url: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "no": self.no,
            "type": self.type,
            "status": self.status,
            "submitted": self.submitted.isoformat() if self.submitted else None,
            "issued": self.issued.isoformat() if self.issued else None,
            "valuation": self.valuation,
            "url": self.url,
        }


@dataclass
class Parcel:
    apn: str
    address: str = ""
    jurisdiction: str = "LA"  # LA | COUNTY | MALIBU
    struct: str = "SFR"  # SFR | MFR | COM | OTH
    damage: str = "Destroyed"
    units: int | None = None
    pre_fire: dict[str, Any] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    permits: list[Permit] = field(default_factory=list)
    geometry: dict[str, Any] | None = None  # GeoJSON geometry
    neighborhood: str = ""
    lon: float | None = None
    lat: float | None = None

    # coarse=True for lots whose stage comes from a jurisdiction status field
    # (Malibu markers, county REBUILD_PROGRESS) rather than a dated event timeline.
    # These are scored at mid-band and excluded from cohort velocity statistics.
    coarse: bool = False
    coarse_stage: int | None = None

    # computed by score.py
    stage: int = 0
    score: float = 0.0
    est_completion: str | None = None
    score_explain: str = ""

    def jurisdiction_label(self) -> str:
        return {"LA": "City of LA", "COUNTY": "LA County", "MALIBU": "Malibu"}.get(
            self.jurisdiction, self.jurisdiction
        )

    def sorted_events(self) -> list[Event]:
        return sorted(self.events, key=lambda e: (e.date, KIND_STAGE.get(e.kind, 0)))

    def last_event_date(self) -> date | None:
        ev = self.sorted_events()
        return ev[-1].date if ev else None
