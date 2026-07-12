"""Emit static artifacts per Docs/initialbuild_docs/ARTIFACTS.md into web/public/data/.

Artifacts carry lane signals, milestone facts, and typed observations. The
retired 0-100 score, heuristic ETA, and 0-5 stage ladder are never emitted
(TRUTH-001): map styling and counts derive only from evidenced milestones.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import orjson

from openpali.domain.lanes import (
    LaneSignal,
    PROJECTION_POLICY_VERSION,
    ParcelLaneState,
)
from openpali.domain.observations import MilestoneLane
from openpali.domain.policy import QUALIFYING_REBUILD_POLICY_VERSION
from openpali.domain.taxonomy import TAXONOMY_VERSION
from openpali.domain.temporal import ExactDate

from .model import Parcel
from .neighborhoods import NEIGHBORHOODS

OUT_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "data"

#: Compact per-lane property keys for parcels.geojson.
_LANE_KEYS = {
    MilestoneLane.CLEANUP: "lane_cleanup",
    MilestoneLane.DESIGN_REVIEW: "lane_design",
    MilestoneLane.PERMITTING: "lane_permit",
    MilestoneLane.CONSTRUCTION: "lane_constr",
    MilestoneLane.OCCUPANCY: "lane_occup",
}


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _lane_signals(state: ParcelLaneState | None) -> dict[str, str]:
    if state is None:
        return {key: LaneSignal.NO_PUBLIC_EVIDENCE.value for key in _LANE_KEYS.values()}
    return {
        _LANE_KEYS[projection.lane]: projection.signal.value
        for projection in state.lanes
    }


def _milestones(state: ParcelLaneState | None) -> dict[str, bool]:
    """Evidence-backed milestone facts (booleans, not a ranking)."""

    if state is None:
        return {
            "cleanup_complete": False,
            "plan_check_approved": False,
            "application_submitted": False,
            "permit_issued": False,
            "construction_evidence": False,
            "cofo_issued": False,
        }
    reached: dict[MilestoneLane, tuple[str, ...]] = {
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


def emit_all(
    parcels: list[Parcel],
    *,
    baselines: list[dict[str, Any]] | None = None,
    source_meta: list[dict[str, Any]] | None = None,
    incidents: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    snapshot_id: str | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    out = out_dir or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    # One snapshot_id stamps every artifact of a run so the frontend can detect
    # mixed-vintage reads; run_id ties artifacts back to logs/provenance.
    run_id = run_id or uuid.uuid4().hex[:12]
    snapshot_id = snapshot_id or f"{now.strftime('%Y%m%dT%H%M%SZ')}-{run_id[:6]}"

    # ---- parcels.geojson (lean) ----
    features = []
    for p in parcels:
        if not p.geometry:
            continue
        properties: dict[str, Any] = {
            "apn": p.apn,
            "address": p.address,
            "neighborhood": p.neighborhood,
            "jurisdiction": p.jurisdiction,
            "struct": p.struct,
            "last_evidence": (
                p.last_evidence_date().isoformat() if p.last_evidence_date() else None
            ),
        }
        properties.update(_lane_signals(p.lane_state))
        properties.update(_milestones(p.lane_state))
        features.append(
            {"type": "Feature", "properties": properties, "geometry": p.geometry}
        )
    parcels_bytes = orjson.dumps(
        # snapshot_id is a GeoJSON foreign member (RFC 7946 §6.1) — safe for consumers
        {"type": "FeatureCollection", "snapshot_id": snapshot_id, "features": features}
    )
    (out / "parcels.geojson").write_bytes(parcels_bytes)

    # ---- details.json ----
    details: dict[str, Any] = {}
    for p in parcels:
        details[p.apn] = {
            "address": p.address.title(),
            "pre_fire": {
                "use": p.pre_fire.get("use"),
                "year_built": p.pre_fire.get("year_built"),
                "sqft": p.pre_fire.get("sqft"),
                "beds": p.pre_fire.get("beds"),
                "baths": p.pre_fire.get("baths"),
                "units": p.pre_fire.get("units"),
            },
            "observations": [o.to_json() for o in p.sorted_observations()],
            "lanes": p.lane_state.to_json() if p.lane_state else None,
            "permits": [pm.to_json() for pm in p.permits],
            "lat": round(p.lat, 6) if p.lat else None,
            "lon": round(p.lon, 6) if p.lon else None,
        }
    # underscore key cannot collide with 10-digit APN keys; web does keyed lookups only
    details["_snapshot_id"] = snapshot_id
    details_bytes = orjson.dumps(details)
    (out / "details.json").write_bytes(details_bytes)

    # ---- summary.json ----
    milestone_counts: Counter[str] = Counter()
    scheduled_only = opt_out = 0
    for p in parcels:
        milestones = _milestones(p.lane_state)
        for key, value in milestones.items():
            if value:
                milestone_counts[key] += 1
        if p.lane_state is not None:
            construction = p.lane_state.lane(MilestoneLane.CONSTRUCTION)
            if construction.signal is LaneSignal.ACTIVITY_SCHEDULED:
                scheduled_only += 1
            if any(
                o.event_type == "cleanup_opt_out_selected" for o in p.observations
            ):
                opt_out += 1
    totals = {
        "destroyed": len(parcels),
        "cleanup_complete": milestone_counts["cleanup_complete"],
        "cleanup_opt_out": opt_out,
        "application_submitted": milestone_counts["application_submitted"],
        "plan_check_approved": milestone_counts["plan_check_approved"],
        "permit_issued": milestone_counts["permit_issued"],
        "construction_evidence": milestone_counts["construction_evidence"],
        "construction_inspection_scheduled_only": scheduled_only,
        "cofo_issued": milestone_counts["cofo_issued"],
    }

    # Weekly series count only source-dated (exact) milestone occurrences —
    # undated assertions are reported in totals but cannot be time-bucketed.
    weekly_sub: Counter[date] = Counter()
    weekly_iss: Counter[date] = Counter()
    for p in parcels:
        for o in p.observations:
            if not isinstance(o.occurred, ExactDate):
                continue
            if o.event_type == "rebuild_application_submitted":
                weekly_sub[_week_start(o.occurred.value)] += 1
            elif o.event_type == "rebuild_permit_issued":
                weekly_iss[_week_start(o.occurred.value)] += 1
    weeks = sorted(set(weekly_sub) | set(weekly_iss))
    weekly = [
        {"w": w.isoformat(), "submitted": weekly_sub.get(w, 0), "issued": weekly_iss.get(w, 0)}
        for w in weeks
        if w >= date(2025, 1, 6)
    ]

    hood_stats: dict[str, Counter] = defaultdict(Counter)
    for p in parcels:
        c = hood_stats[p.neighborhood]
        c["destroyed"] += 1
        milestones = _milestones(p.lane_state)
        if milestones["cofo_issued"]:
            c["cofo_issued"] += 1
        if milestones["permit_issued"]:
            c["permit_issued"] += 1
        if milestones["application_submitted"]:
            c["application_submitted"] += 1
        if milestones["cleanup_complete"]:
            c["cleanup_complete"] += 1
    neighborhoods = []
    for n in NEIGHBORHOODS:
        s = hood_stats.get(n["name"])
        if not s:
            continue
        neighborhoods.append(
            {
                "name": n["name"],
                "center": list(n["center"]),
                "zoom": n["zoom"],
                "destroyed": s["destroyed"],
                "cleanup_complete": s["cleanup_complete"],
                "application_submitted": s["application_submitted"],
                "permit_issued": s["permit_issued"],
                "cofo_issued": s["cofo_issued"],
            }
        )

    summary = {
        "as_of": now.isoformat(),
        "snapshot_id": snapshot_id,
        "totals": totals,
        "weekly": weekly,
        "baselines": baselines or [],
        "neighborhoods": neighborhoods,
        "policy_versions": {
            "taxonomy": TAXONOMY_VERSION,
            "projection": PROJECTION_POLICY_VERSION,
            "qualifying_rebuild": QUALIFYING_REBUILD_POLICY_VERSION,
        },
    }
    summary_text = json.dumps(summary, indent=1)
    (out / "summary.json").write_text(summary_text)

    # ---- meta.json ----
    meta = {
        "generated": now.isoformat(),
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "sources": source_meta or [],
        "incidents": incidents or [],
        "policy_versions": summary["policy_versions"],
        "artifacts": {
            "parcels.geojson": hashlib.sha256(parcels_bytes).hexdigest(),
            "details.json": hashlib.sha256(details_bytes).hexdigest(),
            "summary.json": hashlib.sha256(summary_text.encode()).hexdigest(),
        },
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1))

    return {"features": len(features), "totals": totals, "weeks": len(weekly),
            "snapshot_id": snapshot_id}
