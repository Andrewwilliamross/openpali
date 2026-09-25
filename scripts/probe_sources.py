#!/usr/bin/env python3
"""Read-only metadata/domain/count probes of configured civic source adapters.

No ledger writes, record ingestion, vendor tasking, or public publication.
Run with pipeline/.venv/bin/python; responses retain hashes and parameters.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from openpali.adapters.registry import ADAPTERS  # noqa: E402


DOMAINS = {
    "county_base": ["ROE_STATUS", "DEBRIS_CLEARED", "REBUILD_PROGRESS", "LCITY"],
    "ladbs_permits": ["PALISADES_WF_REBUILD", "PERMIT_TYPE", "PERMIT_STATUS"],
    "ladbs_inspections": ["INSP_STATUS"],
    "calfire_dins": ["DAMAGE"],
}


def probe(source_id: str) -> dict:
    adapter = ADAPTERS[source_id]()
    result = {"source_id": source_id, "endpoint": adapter.layer_url, "requests": []}
    with httpx.Client(timeout=30, follow_redirects=True, headers={
        "User-Agent": "OpenPali source audit (read-only metadata and aggregate counts)",
    }) as client:
        def get(url, params=None):
            response = client.get(url, params=params)
            result["requests"].append({
                "url": url, "parameters": params, "status": response.status_code,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "bytes": len(response.content), "sha256": hashlib.sha256(response.content).hexdigest(),
            })
            response.raise_for_status()
            body = response.json()
            if isinstance(body, dict) and "error" in body:
                raise ValueError(body["error"])
            return body

        try:
            if source_id in DOMAINS:
                metadata = get(adapter.layer_url, {"f": "json"})
                result["metadata"] = {key: metadata.get(key) for key in (
                    "name", "description", "copyrightText", "editingInfo", "extent",
                    "fields", "maxRecordCount", "advancedQueryCapabilities", "objectIdField",
                )}
                requested = set(adapter.out_fields.split(","))
                available = {f["name"] for f in metadata.get("fields", [])}
                result["configured_fields_missing"] = sorted(requested - available)
                params = {"f": "json", "where": adapter.where, "returnCountOnly": "true"}
                result["count"] = get(adapter.layer_url + "/query", params)
                domains = {}
                for field in DOMAINS[source_id]:
                    if field not in available:
                        domains[field] = {"error": "field absent"}
                        continue
                    params = {
                        "f": "json", "where": adapter.where, "returnGeometry": "false",
                        "groupByFieldsForStatistics": field,
                        "outStatistics": json.dumps([{"statisticType": "count",
                            "onStatisticField": metadata.get("objectIdField", "OBJECTID"),
                            "outStatisticFieldName": "row_count"}]),
                    }
                    domains[field] = get(adapter.layer_url + "/query", params)
                result["domains"] = domains
            elif source_id.startswith("socrata_"):
                metadata = get(f"https://{adapter.domain}/api/views/{adapter.dataset_id}.json")
                result["metadata"] = {key: metadata.get(key) for key in (
                    "id", "name", "description", "rowsUpdatedAt", "viewLastModified", "licenseId",
                )}
                result["fields"] = [{"name": c.get("fieldName"), "type": c.get("dataTypeName")}
                                    for c in metadata.get("columns", [])]
                result["configured_fields_missing"] = sorted(set(adapter.select.split(",")) -
                    {c.get("fieldName") for c in metadata.get("columns", [])})
                result["count"] = get(adapter.layer_url, {"$select": "count(*)", "$where": adapter.where})
            else:
                # Inspect JSON shape and count only; never persist individual marker records.
                body = get(adapter.layer_url)
                result["response_type"] = type(body).__name__
                if isinstance(body, list):
                    result["count"] = len(body)
                    result["fields"] = sorted({k for row in body if isinstance(row, dict) for k in row})
                elif isinstance(body, dict):
                    result["top_level_fields"] = sorted(body)
            result["status"] = "succeeded"
        except (httpx.HTTPError, ValueError) as error:
            result["status"] = "failed"
            result["error"] = str(error)[:1500]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=3) as pool:
        sources = list(pool.map(probe, ADAPTERS))
    report = {"probed_at": datetime.now(timezone.utc).isoformat(), "sources": sources}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for source in sources:
        print(source["source_id"], source["status"], source.get("count", source.get("error")),
              "missing fields:", source.get("configured_fields_missing", []))


if __name__ == "__main__":
    main()
