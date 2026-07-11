"""Emit static artifacts per Docs/initialbuild_docs/ARTIFACTS.md into web/public/data/."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import orjson

from .model import STAGE_LABELS, Parcel
from .neighborhoods import NEIGHBORHOODS

OUT_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "data"


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def emit_all(
    parcels: list[Parcel],
    *,
    baselines: list[dict[str, Any]] | None = None,
    source_meta: list[dict[str, Any]] | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    out = out_dir or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # ---- parcels.geojson (lean) ----
    features = []
    for p in parcels:
        if not p.geometry:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "apn": p.apn,
                    "address": p.address,
                    "neighborhood": p.neighborhood,
                    "jurisdiction": p.jurisdiction,
                    "struct": p.struct,
                    "stage": p.stage,
                    "stage_label": STAGE_LABELS[p.stage],
                    "score": p.score,
                    "last_event": p.last_event_date().isoformat() if p.last_event_date() else None,
                },
                "geometry": p.geometry,
            }
        )
    (out / "parcels.geojson").write_bytes(
        orjson.dumps({"type": "FeatureCollection", "features": features})
    )

    # ---- details.json ----
    details: dict[str, Any] = {}
    for p in parcels:
        # Collapse duplicate timeline events (a lot with main-house + ADU permits emits
        # e.g. two identical "Building permit issued" events) — keep one per kind+date.
        seen_events: set[tuple[str, str]] = set()
        unique_events = []
        for e in p.sorted_events():
            key = (e.kind, e.date.isoformat())
            if key in seen_events:
                continue
            seen_events.add(key)
            unique_events.append(e)
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
            "events": [e.to_json() for e in unique_events],
            "permits": [pm.to_json() for pm in p.permits],
            "est_completion": p.est_completion,
            "score": p.score,
            "score_explain": p.score_explain,
            "lat": round(p.lat, 6) if p.lat else None,
            "lon": round(p.lon, 6) if p.lon else None,
        }
    (out / "details.json").write_bytes(orjson.dumps(details))

    # ---- summary.json ----
    stages = Counter(p.stage for p in parcels)
    totals = {
        "destroyed": len(parcels),
        "cleared": sum(v for s, v in stages.items() if s >= 1),
        "plan_check": stages.get(2, 0),
        "permitted": stages.get(3, 0),
        "under_construction": stages.get(4, 0),
        "complete": stages.get(5, 0),
    }

    weekly_sub: Counter[date] = Counter()
    weekly_iss: Counter[date] = Counter()
    for p in parcels:
        for e in p.events:
            if e.kind == "permit_submitted":
                weekly_sub[_week_start(e.date)] += 1
            elif e.kind == "permit_issued":
                weekly_iss[_week_start(e.date)] += 1
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
        if p.stage == 3:
            c["permitted"] += 1
        elif p.stage == 4:
            c["under_construction"] += 1
        elif p.stage == 5:
            c["complete"] += 1
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
                "permitted": s["permitted"],
                "under_construction": s["under_construction"],
                "complete": s["complete"],
            }
        )

    summary = {
        "as_of": now.isoformat(),
        "totals": totals,
        "weekly": weekly,
        "baselines": baselines or [],
        "neighborhoods": neighborhoods,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1))

    # ---- meta.json ----
    meta = {"generated": now.isoformat(), "sources": source_meta or []}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))

    return {"features": len(features), "totals": totals, "weeks": len(weekly)}
