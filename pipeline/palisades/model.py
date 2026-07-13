"""Normalized display model for the static-artifact path.

Semantic truth lives in ``openpali.domain`` (observations, taxonomy, lanes,
policies). ``Parcel`` here carries identity/geometry/display attributes plus
the typed observations and their parallel-lane projection.

DEPRECATED MEMBERS: ``Event``, ``KIND_STAGE``, ``STAGE_LABELS``,
``STAGE_BANDS``, ``INSPECTION_MILESTONES``, ``classify_milestone``, and the
``Parcel.stage``/``score``/``est_completion``/``score_explain`` fields belong
to the retired 0-5 stage ladder / 0-100 score heuristic. They are retained
only so the deprecated ``score.py`` module and its characterization tests keep
importing; nothing in the publication path reads or emits them, and they must
not be reintroduced into any public artifact, API, sort order, color, or map
style (TRUTH-001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from openpali.domain.lanes import ParcelLaneState
from openpali.domain.observations import RecoveryObservation
from openpali.domain.temporal import ExactDate

# --- DEPRECATED: retired stage ladder (see module docstring) ---------------
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

STAGE_BANDS: dict[int, tuple[float, float]] = {
    0: (0, 7),
    1: (8, 14),
    2: (15, 39),
    3: (40, 49),
    4: (50, 92),
    5: (100, 100),
}

INSPECTION_MILESTONES: list[tuple[str, float]] = [
    ("foundation", 0.15),
    ("framing", 0.40),
    ("mep", 0.58),
    ("insulation_drywall", 0.73),
    ("final", 0.88),
]

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
    """DEPRECATED: description-keyword milestone guessing (never an outcome)."""
    if not insp_desc:
        return None
    d = insp_desc.lower()
    for milestone, needles in _MILESTONE_RULES:
        if any(n in d for n in needles):
            return milestone
    return None


@dataclass
class Event:
    """DEPRECATED display event of the retired stage ladder."""

    date: date
    kind: str  # KIND_STAGE key
    label: str
    ref: str | None = None
    milestone: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"date": self.date.isoformat(), "kind": self.kind, "label": self.label}
        if self.ref:
            out["ref"] = self.ref
        return out


# --- Current display model ---------------------------------------------------


@dataclass
class Permit:
    no: str
    type: str
    status: str
    submitted: date | None
    issued: date | None
    valuation: float | None
    url: str | None
    #: openpali.domain.policy.PermitQualification value; drives card labeling
    #: (qualifying rebuild vs rebuild-related ancillary vs non-rebuild).
    qualification: str = "undocumented"

    def to_json(self) -> dict[str, Any]:
        return {
            "no": self.no,
            "type": self.type,
            "status": self.status,
            "submitted": self.submitted.isoformat() if self.submitted else None,
            "issued": self.issued.isoformat() if self.issued else None,
            "valuation": self.valuation,
            "url": self.url,
            "qualification": self.qualification,
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
    permits: list[Permit] = field(default_factory=list)
    geometry: dict[str, Any] | None = None  # GeoJSON geometry
    neighborhood: str = ""
    lon: float | None = None
    lat: float | None = None

    #: Typed recovery observations (openpali.domain) — the evidence timeline.
    observations: list[RecoveryObservation] = field(default_factory=list)
    #: Parallel-lane projection over ``observations``.
    lane_state: ParcelLaneState | None = None

    # --- DEPRECATED stage-ladder fields (see module docstring) ---
    events: list[Event] = field(default_factory=list)
    coarse: bool = False
    coarse_stage: int | None = None
    stage: int = 0
    score: float = 0.0
    est_completion: str | None = None
    score_explain: str = ""

    def jurisdiction_label(self) -> str:
        return {"LA": "City of LA", "COUNTY": "LA County", "MALIBU": "Malibu"}.get(
            self.jurisdiction, self.jurisdiction
        )

    def sorted_events(self) -> list[Event]:
        """DEPRECATED: stage-ladder event ordering (score.py tests only)."""
        return sorted(self.events, key=lambda e: (e.date, KIND_STAGE.get(e.kind, 0)))

    def last_event_date(self) -> date | None:
        """DEPRECATED: use :meth:`last_evidence_date`."""
        ev = self.sorted_events()
        return ev[-1].date if ev else None

    def sorted_observations(self) -> list[RecoveryObservation]:
        """Observations ordered for display: earliest known occurrence first,
        undated evidence last (by observation time)."""

        def key(o: RecoveryObservation):
            earliest = o.occurred.earliest()
            return (
                0 if earliest is not None else 1,
                earliest or o.observed_at.date(),
                o.event_type,
            )

        return sorted(self.observations, key=key)

    def last_evidence_date(self) -> date | None:
        """Latest source-asserted exact occurrence date, if any."""

        dates = [
            o.occurred.value
            for o in self.observations
            if isinstance(o.occurred, ExactDate)
        ]
        return max(dates) if dates else None
