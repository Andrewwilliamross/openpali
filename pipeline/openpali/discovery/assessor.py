"""Bounded, read-only acquisition of the LA Assessor portal's public JSON.

Run from repo root with PYTHONPATH=pipeline. This stages evidence locally; it
does not write the application database or infer market prices from tax values.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

import httpx

from openpali.discovery.clearance import Archive, now

BASE = "https://portal.assessor.lacounty.gov/api/"
HISTORIES = {
    "parcel_ownershiphistory": "Parcel_OwnershipHistory",
    "parcel_assessmenthistory": "Parcel_AssessmentHistory",
    "parcel_parcelchange": "Parcel_ChangeHistory",
}
ENDPOINTS = ("parceldetail", *HISTORIES, "pdbdate")


def valid_source_date(value: object) -> bool:
    try:
        datetime.strptime(str(value).strip(), "%m/%d/%Y")
    except ValueError:
        return False
    return True


def normalize_ain(value: str) -> str:
    if not re.fullmatch(r"(?:[0-9]{10}|[0-9]{4}-[0-9]{3}-[0-9]{3})", value):
        raise ValueError("AIN must be 10 digits or XXXX-XXX-XXX")
    return value.replace("-", "")


def validate(endpoint: str, ain: str, payload: object) -> dict:
    """Fail closed on HTML, errors, wrong parcels, or changed envelopes."""
    if not isinstance(payload, dict) or "error" in payload:
        raise ValueError(f"invalid {endpoint} response")
    if endpoint == "parceldetail":
        parcel = payload.get("Parcel")
        if not isinstance(parcel, dict) or str(parcel.get("AIN")) != ain:
            raise ValueError("parcel detail does not match requested AIN")
        if not parcel.get("PDBEffectiveDate") or not parcel.get("CurrentRoll_BaseYear"):
            raise ValueError("parcel detail lacks source effective date/current roll")
    elif endpoint in HISTORIES:
        rows = payload.get(HISTORIES[endpoint])
        if str(payload.get("AIN")) != ain or not isinstance(rows, list):
            raise ValueError("history envelope does not match requested AIN")
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("history row is not an object")
    elif endpoint == "pdbdate":
        if not payload.get("PDBEffectiveDate"):
            raise ValueError("source effective date missing")
    else:
        raise ValueError("unknown endpoint")
    return payload


def profile(payloads: dict) -> dict:
    parcel = payloads.get("parceldetail", {}).get("Parcel", {})
    assessment = payloads.get("parcel_assessmenthistory", {}).get("Parcel_AssessmentHistory", [])
    ownership = payloads.get("parcel_ownershiphistory", {}).get("Parcel_OwnershipHistory", [])
    changes = payloads.get("parcel_parcelchange", {}).get("Parcel_ChangeHistory", [])
    # Year is a role, not a max(): preparation can already be next year's roll.
    result = {
        "source_effective_date": parcel.get("PDBEffectiveDate"),
        "database_effective_date": payloads.get("pdbdate", {}).get("PDBEffectiveDate"),
        "current_roll_year": parcel.get("CurrentRoll_BaseYear"),
        "preparation_roll_year": parcel.get("RollPreparation_BaseYear"),
        "detail_fields": sorted(parcel),
        "assessment_history_rows": len(assessment),
        "assessment_rows_by_year": dict(Counter(str(r.get("TaxYear")) for r in assessment)),
        "ownership_history_rows": len(ownership),
        "ownership_recording_dates": [r.get("RecordingDate") for r in ownership],
        "parcel_change_rows": len(changes),
        "construction_date_rows": sum(valid_source_date(r.get("NewConstructionDate")) for r in assessment),
        "construction_date_sentinels": dict(Counter(str(r.get("NewConstructionDate")) for r in assessment
                                                    if not valid_source_date(r.get("NewConstructionDate")))),
        "invalid_ownership_date_values": [r.get("RecordingDate") for r in ownership
                                          if not valid_source_date(r.get("RecordingDate"))],
    }
    # Assessment bills/corrections and trust/partial transfers remain separate.
    # DTTSalePrice is a transfer-tax-derived source field, not a verified closing price.
    return result


def collect(archive: Archive, ain: str, delay: float) -> dict:
    payloads, failures = {}, []
    for endpoint in ENDPOINTS:
        try:
            raw, _ = archive.get(BASE + endpoint, {"ain": ain})
            payloads[endpoint] = validate(endpoint, ain, json.loads(raw))
        except (httpx.HTTPError, ValueError) as error:
            failures.append({"endpoint": endpoint, "error": str(error)[:500]})
            # Stop host traffic on explicit rate limiting / access denial.
            if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403, 429):
                break
        time.sleep(delay)
    return {"ain": ain, "payloads": payloads, "failures": failures,
            "status": "complete" if len(payloads) == len(ENDPOINTS) else "partial",
            "profile": profile(payloads)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ain", action="append", required=True)
    parser.add_argument("--root", type=Path, default=Path("data/raw/assessor"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()
    if not 0.5 <= args.delay <= 10:
        parser.error("--delay must be between 0.5 and 10 seconds")
    try:
        ains = list(dict.fromkeys(normalize_ain(a) for a in args.ain))
    except ValueError as error:
        parser.error(str(error))
    if len(ains) > 25:
        parser.error("research collector is bounded to 25 parcels per invocation")
    run = args.root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {"started_at": now(), "source": BASE, "run_path": str(run),
              "scope": "public portal sample; no publication or production ingestion", "parcels": []}
    with httpx.Client(timeout=45, follow_redirects=False,
                      headers={"User-Agent": "OpenPali research property history"}) as client:
        archive = Archive(run, client)
        for ain in ains:
            record = collect(archive, ain, args.delay)
            body = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
            path = run / f"{ain}.json"
            path.write_bytes(body)
            report["parcels"].append({k: v for k, v in record.items() if k != "payloads"} |
                                     {"path": str(path), "sha256": hashlib.sha256(body).hexdigest()})
            if any(r["status"] in (401, 403, 429) for r in archive.requests):
                report["stop_reason"] = "host denied access or requested rate limiting"
                break
        report.update({"completed_at": now(), "requests": archive.requests,
                       "requested_ains": ains})
    report["status"] = ("complete" if len(report["parcels"]) == len(ains)
                        and all(p["status"] == "complete" for p in report["parcels"]) else "partial")
    body = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (run / "report.json").write_text(body)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(body)
    print(json.dumps({"status": report["status"], "parcels": len(report["parcels"]), "run_path": str(run)}))
    if report["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
