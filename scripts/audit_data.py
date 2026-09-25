#!/usr/bin/env python3
"""Profile a published static bundle without changing it or contacting services.

Run with pipeline/.venv/bin/python for optional Shapely geometry validation.
Counts describe records in this bundle, never the actual state of all homes.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path


MILESTONES = (
    "cleanup_complete", "application_submitted", "plan_check_approved",
    "permit_issued", "construction_evidence", "cofo_issued",
)


def profile(bundle: Path, as_of: date) -> dict:
    bodies = {name: (bundle / name).read_bytes() for name in (
        "meta.json", "parcels.geojson", "details.json", "summary.json", "coverage.json",
    )}
    documents = {name: json.loads(body) for name, body in bodies.items()}
    meta, geo, details, summary, coverage = (
        documents[name] for name in bodies
    )
    parcels = geo["features"]
    records = {key: value for key, value in details.items() if not key.startswith("_")}
    apns = [f["properties"]["apn"] for f in parcels]
    snapshot_ids = {
        "meta": meta.get("snapshot_id"), "parcels": geo.get("snapshot_id"),
        "details": details.get("_snapshot_id"), "summary": summary.get("snapshot_id"),
    }
    hashes = {
        name: {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
               "matches_manifest": hashlib.sha256(body).hexdigest() == meta["artifacts"][name]
               if name in meta.get("artifacts", {}) else None}
        for name, body in bodies.items()
    }
    aggregate = Counter()
    jurisdictions, neighborhoods = defaultdict(Counter), defaultdict(Counter)
    lane_signals = defaultdict(Counter)
    observation_types, observation_statuses, occurrence_kinds = Counter(), Counter(), Counter()
    sources = defaultdict(Counter)
    observation_ids = Counter()
    missing_pre_fire = Counter()
    temporal_issues = Counter()
    observed_dates = Counter()
    for apn, detail in records.items():
        for name, value in detail.get("pre_fire", {}).items():
            if value is None:
                missing_pre_fire[name] += 1
        aggregate["permit_records"] += len(detail.get("permits", []))
        aggregate["parcels_with_permit_records"] += bool(detail.get("permits"))
        observations = detail.get("observations", [])
        for obs in observations:
            observation_ids[obs["observation_id"]] += 1
            event = obs["event_type"]
            observation_types[event] += 1
            observation_statuses[obs["status"]] += 1
            when = obs["occurred"]
            occurrence_kinds[when["kind"]] += 1
            source = sources[obs["source_record"]["source_id"]]
            source["observation_instances"] += 1
            source["missing_payload_hash"] += not bool(obs["source_record"].get("payload_sha256"))
            source["date_" + when["kind"]] += 1
            source["event_" + event] += 1
            observed = datetime.fromisoformat(obs["observed_at"]).date()
            observed_dates[observed.isoformat()] += 1
            exact = when.get("date")
            if exact and date.fromisoformat(exact) > observed and obs["status"] != "scheduled":
                temporal_issues["nonscheduled_exact_after_observation"] += 1
            if when["kind"] == "interval":
                low, high = when.get("earliest"), when.get("latest")
                temporal_issues["interval_without_upper_bound"] += high is None
                if low and high and low > high:
                    temporal_issues["reversed_interval"] += 1
        aggregate["parcels_without_observations"] += not bool(observations)
        aggregate["parcels_with_cleanup_opt_out"] += any(
            o["event_type"] == "cleanup_opt_out_selected" for o in observations
        )
        aggregate["construction_scheduled_only"] += any(
            lane["lane"] == "construction" and lane["signal"] == "activity_scheduled"
            for lane in (detail.get("lanes") or {}).get("lanes", [])
        )

    for feature in parcels:
        props = feature["properties"]
        groups = [aggregate, jurisdictions[props.get("jurisdiction", "unknown")],
                  neighborhoods[props.get("neighborhood", "unknown")]]
        for group in groups:
            group["parcels"] += 1
            for key in MILESTONES:
                group[key] += props.get(key) is True
            group["no_evidenced_milestone"] += not any(props.get(k) is True for k in MILESTONES)
            group["no_evidenced_permit_or_later"] += not any(
                props.get(k) is True for k in ("permit_issued", "construction_evidence", "cofo_issued")
            )
        for key, value in props.items():
            if key.startswith("lane_"):
                lane_signals[key][value] += 1

    geometry = {"validation": "not_run: install Shapely or use pipeline/.venv/bin/python"}
    try:
        from shapely.geometry import shape
    except ImportError:
        pass
    else:
        checks = Counter()
        for feature in parcels:
            raw = feature.get("geometry")
            if raw is None:
                checks["missing"] += 1
                continue
            try:
                value = shape(raw)
                checks["invalid"] += not value.is_valid
                checks["empty"] += value.is_empty
                checks["nonpolygon"] += value.geom_type not in ("Polygon", "MultiPolygon")
            except (TypeError, ValueError):
                checks["unparseable"] += 1
        geometry = {"validation": "Shapely", **checks}

    observed_source_ids = set(sources)
    metadata_source_ids = {s["id"] for s in meta["sources"]}
    source_health = []
    for source in meta["sources"]:
        fetched = source.get("fetched_at") or source.get("as_of")
        source_health.append({
            **source,
            "retrieval_age_days": (as_of - datetime.fromisoformat(fetched).date()).days
            if fetched else None,
            "age_basis": "retrieval, not acquisition or event occurrence",
        })
    totals = {"destroyed": len(parcels), **{k: aggregate[k] for k in MILESTONES},
              "cleanup_opt_out": aggregate["parcels_with_cleanup_opt_out"],
              "construction_inspection_scheduled_only": aggregate["construction_scheduled_only"]}
    return {
        "audit_version": "1", "as_of": as_of.isoformat(),
        "scope": "local static bundle only; deployment and live source state are separate",
        "snapshot_ids": snapshot_ids,
        "bundle_age_days": (as_of - datetime.fromisoformat(summary["as_of"]).date()).days,
        "hashes": hashes,
        "integrity": {
            "snapshot_ids_match": len(set(snapshot_ids.values())) == 1 and all(snapshot_ids.values()),
            "duplicate_map_apns": sum(n - 1 for n in Counter(apns).values() if n > 1),
            "map_apns_without_details": len(set(apns) - records.keys()),
            "detail_apns_without_map": len(records.keys() - set(apns)),
            "map_apns_without_coverage": len(set(apns) - coverage.keys()),
            "summary_mismatches": {k: {"computed": v, "published": summary["totals"].get(k)}
                                   for k, v in totals.items() if summary["totals"].get(k) != v},
            "duplicate_observation_instances": sum(n - 1 for n in observation_ids.values() if n > 1),
            "note": "observation instance duplicates can reflect a multi-parcel relationship",
            "temporal_issues": temporal_issues,
        },
        "counts": aggregate, "jurisdictions": jurisdictions, "neighborhoods": neighborhoods,
        "neighborhood_method": "nearest configured center; not validated neighborhood polygons",
        "lane_signals": lane_signals,
        "observations": {
            "instances": sum(observation_types.values()), "unique_ids": len(observation_ids),
            "event_types": observation_types, "statuses": observation_statuses,
            "occurrence_kinds": occurrence_kinds, "observed_dates": observed_dates,
            "by_source": sources,
            "sources_absent_from_metadata": sorted(observed_source_ids - metadata_source_ids),
        },
        "missing_pre_fire_fields": missing_pre_fire,
        "geometry": geometry, "source_health": source_health,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parents[1] / "web/public/data")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(profile(args.bundle, args.as_of), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(args.output)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
