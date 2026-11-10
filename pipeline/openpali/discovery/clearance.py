"""Inventory all clearance links and acquire a bounded, stratified PDF sample.

No database writes or publication. Raw bytes are content-addressed locally.
Example (repo root):
  pipeline/.venv/bin/python pipeline/openpali/discovery/clearance.py --sample 12
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse

import httpx


LAYER = ("https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
         "Parcels_Debris_Removal_Public/FeatureServer/0")
WHERE = "FIRE_NAME='Palisades' AND DAMAGE='Destroyed (>50%)'"
FIELDS = ["OBJECTID", "APN", "SITUSFULLADDRESS", "LCITY", "ROE_STATUS", "DAMAGE",
          "FSO_URL", "FSO_PKG_APPROVED_USACE", "DEBRIS_CLEARED",
          "DEBRIS_REMOVAL_EPICLA", "BUILD_PLAN_APPROVED", "REBUILD_PROGRESS"]
MAX_BYTES = 24 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Archive:
    def __init__(self, root: Path, client: httpx.Client):
        self.root, self.client = root, client
        self.requests: list[dict] = []
        (root / "objects").mkdir(parents=True, exist_ok=True)

    def get(self, url: str, params: dict | None = None, *, post: bool = False) -> tuple[bytes, dict]:
        # No automatic retries: a rate-limit or block is retained as evidence.
        method = "POST" if post else "GET"
        options = {"data": params} if post else {"params": params}
        with self.client.stream(method, url, **options) as response:
            payload = bytearray()
            for chunk in response.iter_bytes():
                payload.extend(chunk)
                if len(payload) > MAX_BYTES:
                    raise ValueError(f"response exceeds {MAX_BYTES} bytes: {url}")
            body = bytes(payload)
            digest = hashlib.sha256(body).hexdigest()
            path = self.root / "objects" / digest
            if not path.exists():
                path.write_bytes(body)
            record = {
                "url": str(response.url), "requested_url": url, "parameters": params,
                "method": method,
                "retrieved_at": now(), "status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "bytes": len(body), "sha256": digest, "object_path": str(path),
            }
            self.requests.append(record)
            response.raise_for_status()
            return body, record

    def json(self, url: str, params: dict, *, post: bool = False) -> dict:
        raw, _ = self.get(url, params, post=post)
        data = json.loads(raw)
        if not isinstance(data, dict) or "error" in data:
            raise ValueError(f"invalid ArcGIS response: {str(data)[:300]}")
        return data


def fetch_inventory(archive: Archive) -> list[dict]:
    """Freeze IDs first, and require every requested ID exactly once per batch."""
    query = LAYER + "/query"
    response = archive.json(query, {"f": "json", "where": WHERE,
                                    "returnIdsOnly": "true"})
    oid = response["objectIdFieldName"]
    ids = sorted(response["objectIds"])
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("empty or duplicate object ID inventory")
    records = []
    fields = list(dict.fromkeys([oid, *FIELDS]))
    for start in range(0, len(ids), 500):
        batch = ids[start:start + 500]
        body = archive.json(query, {
            "f": "json", "objectIds": ",".join(map(str, batch)),
            "outFields": ",".join(fields), "returnGeometry": "false",
        }, post=True)  # ArcGIS read-only query; avoid long object-ID URLs.
        if body.get("exceededTransferLimit"):
            raise ValueError("source truncated a requested batch")
        rows = [f["attributes"] for f in body["features"]]
        returned = [r[oid] for r in rows]
        if len(returned) != len(batch) or set(returned) != set(batch):
            raise ValueError("source omitted, duplicated, or substituted requested IDs")
        records.extend(rows)
    return records


def approved_pdf_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlparse(value)
        return (url.scheme == "https" and url.hostname == "pwgis.blob.core.windows.net"
                and url.path.startswith("/epd/Debris_Removal/")
                and url.path.lower().endswith(".pdf") and not url.username
                and not url.password and url.port in (None, 443))
    except ValueError:
        return False


def choose_samples(records: list[dict], limit: int) -> list[dict]:
    """Round-robin by ROE status; unique documents; deterministic hash order."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        if approved_pdf_url(row.get("FSO_URL")):
            groups[str(row.get("ROE_STATUS"))].append(row)
    for group in groups.values():
        group.sort(key=lambda r: hashlib.sha256(r["FSO_URL"].encode()).hexdigest())
    selected, seen = [], set()
    while groups and len(selected) < limit:
        for key in sorted(list(groups)):
            group = groups[key]
            while group and group[0]["FSO_URL"] in seen:
                group.pop(0)
            if not group:
                del groups[key]
                continue
            row = group.pop(0)
            seen.add(row["FSO_URL"])
            selected.append(row)
            if len(selected) >= limit:
                break
    return selected


def pdf_profile(body: bytes, path: Path) -> dict:
    if not body.startswith(b"%PDF-"):
        raise ValueError("response is not a PDF despite its URL")
    result: dict = {"format_verified": True}
    if shutil.which("pdfinfo"):
        info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True,
                              timeout=30, check=True).stdout
        match = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
        result["pages"] = int(match[1]) if match else None
    if shutil.which("pdftotext"):
        extracted = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                   capture_output=True, text=True, timeout=30,
                                   check=True).stdout
        result.update({
            "extracted_text_characters": len(extracted),
            "photo_description_mentions": extracted.lower().count("photo description"),
            "has_clearance_form_text": "final property clearance" in extracted.lower(),
            "withdrawal_text_present": "withdrawal" in extracted.lower(),
            "visual_review_required": True,
            "needs_ocr_review": len(extracted.strip()) < 100,
            "date_strings": sorted(set(re.findall(
                r"\b(?:\d{1,2}[-/][A-Za-z]{3}[-/]\d{4}|\d{1,2}/\d{1,2}/\d{4})\b",
                extracted))),
        })
        # This is extraction evidence, not a normalized completion date. Stamps
        # and checkboxes can be embedded images missing from the text layer.
        path.with_suffix(".txt").write_text(extracted)
    return result


def summarize(records: list[dict]) -> dict:
    urls = [r["FSO_URL"] for r in records if r.get("FSO_URL")]
    status: dict[str, Counter] = defaultdict(Counter)
    for row in records:
        group = status[str(row.get("ROE_STATUS"))]
        group["parcels"] += 1
        group["with_pdf_url"] += approved_pdf_url(row.get("FSO_URL"))
    return {
        "parcels": len(records), "unique_apns": len({r["APN"] for r in records}),
        "populated_url_rows": len(urls), "unique_populated_urls": len(set(urls)),
        "approved_url_rows": sum(approved_pdf_url(u) for u in urls),
        "by_roe_status": dict(status),
        "debris_removal_epicla_domain": dict(Counter(str(r.get("DEBRIS_REMOVAL_EPICLA")) for r in records)),
        "epicla_by_roe_status": {status: dict(Counter(str(r.get("DEBRIS_REMOVAL_EPICLA")) for r in records
                                                     if str(r.get("ROE_STATUS")) == status))
                                 for status in sorted(status)},
        "build_plan_approved_domain": dict(Counter(str(r.get("BUILD_PLAN_APPROVED")) for r in records)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/clearance"))
    parser.add_argument("--sample", type=int, default=0, help="bounded PDF sample, maximum 50")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 0 <= args.sample <= 50:
        parser.error("--sample must be between 0 and 50")
    run = args.root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True)
    report = {"started_at": now(), "source": LAYER, "where": WHERE,
              "scope": "research inventory and stratified convenience sample, not publication",
              "run_path": str(run), "documents": []}
    with httpx.Client(timeout=45, follow_redirects=False,
                      headers={"User-Agent": "OpenPali research clearance inventory"}) as client:
        archive = Archive(run, client)
        try:
            records = fetch_inventory(archive)
            index = run / "index.jsonl"
            index.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))
            report.update(summarize(records))
            report["index_path"] = str(index)
            report["index_sha256"] = hashlib.sha256(index.read_bytes()).hexdigest()
            for row in choose_samples(records, args.sample):
                document = {"apn": row["APN"], "roe_status": row.get("ROE_STATUS"),
                            "url": row["FSO_URL"]}
                try:
                    raw, request = archive.get(row["FSO_URL"])
                    document.update(request)
                    document["profile"] = pdf_profile(raw, Path(request["object_path"]))
                    document["status"] = "downloaded"
                except (httpx.HTTPError, ValueError, subprocess.SubprocessError) as error:
                    document["status"] = "failed"
                    document["error"] = str(error)[:500]
                report["documents"].append(document)
            report["status"] = "complete"
        except Exception as error:
            report["status"] = "failed"
            report["error"] = str(error)[:1000]
            raise
        finally:
            report["completed_at"] = now()
            report["requests"] = archive.requests
            body = json.dumps(report, indent=2, sort_keys=True) + "\n"
            (run / "report.json").write_text(body)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(body)
    print(json.dumps({k: v for k, v in report.items() if k not in ("requests", "documents")}, indent=2))


if __name__ == "__main__":
    main()
