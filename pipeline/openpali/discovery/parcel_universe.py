"""Stage all property types in ZIP 90272 from the County parcel service.

This is an explicit acquisition cohort, not a definition of the Palisades
neighborhood or fire perimeter. Damage records are joined separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import httpx

from openpali.discovery.clearance import Archive, now

LAYER = "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0"
WHERE = "SitusZIP LIKE '90272%'"
FIELDS = ["OBJECTID", "AIN", "APN", "SitusFullAddress", "SitusZIP", "UseType", "UseDescription",
          "YearBuilt1", "EffectiveYear1", "SQFTmain1", "Bedrooms1", "Bathrooms1", "Units1",
          "Roll_Year", "Roll_LandValue", "Roll_ImpValue", "QualityClass1", "ParcelTypeCode",
          "SpatialChangeDate", "ParcelCreateDate", "Assr_Map", "CENTER_LAT", "CENTER_LON"]


def fetch(archive: Archive) -> list[dict]:
    metadata = archive.json(LAYER, {"f": "json"})
    if not set(FIELDS).issubset({f["name"] for f in metadata["fields"]}):
        raise ValueError("parcel schema changed")
    response = archive.json(LAYER + "/query", {"f": "json", "where": WHERE, "returnIdsOnly": "true"})
    ids = sorted(response["objectIds"])
    if not ids or len(ids) > 30000 or len(ids) != len(set(ids)):
        raise ValueError("empty, duplicate or unexpectedly large cohort")
    features = []
    for start in range(0, len(ids), 500):
        batch = ids[start:start + 500]
        payload = archive.json(LAYER + "/query", {
            "f": "geojson", "objectIds": ",".join(map(str, batch)), "outFields": ",".join(FIELDS),
            "returnGeometry": "true", "outSR": 4326,
        }, post=True)
        rows = payload.get("features", [])
        returned = [f["properties"]["OBJECTID"] for f in rows]
        if payload.get("exceededTransferLimit") or len(returned) != len(batch) or set(returned) != set(batch):
            raise ValueError("parcel batch incomplete or substituted")
        if any(f.get("geometry", {}).get("type") not in ("Polygon", "MultiPolygon") for f in rows):
            raise ValueError("missing or unexpected parcel geometry")
        features.extend(rows)
        time.sleep(0.25)
    return features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    run = Path("data/raw/parcel-universe") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {"started_at": now(), "source": LAYER, "where": WHERE,
              "scope": "ZIP 90272, all property types; not a neighborhood boundary", "run_path": str(run)}
    with httpx.Client(timeout=45, follow_redirects=False) as client:
        archive = Archive(run, client)
        try:
            features = fetch(archive)
            body = json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")).encode()
            path = run / "parcels.geojson"
            path.write_bytes(body)
            attrs = [f["properties"] for f in features]
            report.update(status="complete", features=len(features), unique_ains=len({a["AIN"] for a in attrs}),
                          roll_years=dict(Counter(str(a["Roll_Year"]) for a in attrs)),
                          use_types=dict(Counter(str(a["UseType"]) for a in attrs)),
                          path=str(path), sha256=hashlib.sha256(body).hexdigest())
        except Exception as error:
            report.update(status="failed", error=str(error)[:1000])
            raise
        finally:
            report.update(completed_at=now(), requests=archive.requests)
            body = json.dumps(report, indent=2, sort_keys=True) + "\n"
            (run / "report.json").write_text(body)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(body)
    print(json.dumps({k: v for k, v in report.items() if k != "requests"}))


if __name__ == "__main__":
    main()
