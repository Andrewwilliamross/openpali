#!/usr/bin/env python3
"""Palisades Rebuild Tracker — static-artifact pipeline entrypoint.

  uv run run.py              # full live run + emit + validate
  uv run run.py --offline    # use cached raw responses only (ttl=inf)
  uv run run.py --no-validate # skip the oracle reconciliation queries

Emits lane-signal/milestone artifacts. The retired 0-100 score and stage
ladder are never computed or published (TRUTH-001).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openpali.domain.lanes import LaneSignal
from openpali.domain.observations import MilestoneLane

from palisades import checks, emit, provenance, sources, validate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use cache only (ttl=inf)")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()
    ttl = 1e9 if args.offline else 12.0

    run_id = uuid.uuid4().hex[:12]
    started = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{run_id[:6]}"
    provenance.reset()

    print("→ fetching + normalizing sources …")
    parcels, report = sources.build_parcels(ttl_hours=ttl)
    print(f"  {len(parcels)} destroyed parcels")
    if not parcels:
        print("ERROR: no parcels — aborting", file=sys.stderr)
        return 1
    print(f"  qualifying rebuild applications: {report.qualifying_applications}")
    if report.conflicts:
        print(f"  conflicting assertions detected: {len(report.conflicts)}")

    print("→ lane distribution …")
    for lane in MilestoneLane:
        dist = Counter(
            p.lane_state.lane(lane).signal.value
            for p in parcels
            if p.lane_state is not None
        )
        interesting = {
            k: v for k, v in sorted(dist.items())
            if k != LaneSignal.NO_PUBLIC_EVIDENCE.value
        }
        print(f"  {lane.value:14s} {interesting or '(no public evidence anywhere)'}")

    baselines = []
    if not args.no_validate:
        # live: always re-query the oracle fresh; offline: reuse cached oracle
        # responses so reconciliation is never silently skipped.
        print(f"→ validating against official oracle ({'cache' if args.offline else 'live'}) …")
        try:
            baselines = validate.oracle_baselines(ttl_hours=ttl if args.offline else 0.0)
        except Exception as e:  # noqa: BLE001 - validation must never block emit
            print(f"  validation skipped ({e})", file=sys.stderr)

    prop_dicts = [
        {
            "apn": p.apn,
            "jurisdiction": p.jurisdiction,
            **emit._milestones(p.lane_state),
        }
        for p in parcels
    ]
    recon = validate.reconcile(prop_dicts, baselines) if baselines else []
    if recon:
        print("  reconciliation vs official:")
        for r in recon:
            flag = "✓" if r["ok"] else "⚠"
            print(f"    {flag} {r['metric']:36s} official={r['official']:>5} ours={r['ours']!s:>5} drift={r['drift_pct']}%")

    print("→ expectation gates …")
    source_meta = sources.source_health()
    prev_summary = _read_json(emit.OUT_DIR / "summary.json")
    prev_meta = _read_json(emit.OUT_DIR / "meta.json")
    incidents = checks.run_gates(
        parcels, source_meta, recon, prev_summary, prev_meta,
        undocumented_values=report.undocumented,
    )
    for i in incidents:
        print(f"  [{i['level']}] {i['code']}: {i['message']}")
    if not incidents:
        print("  all gates clean")
    if checks.has_errors(incidents):
        print("✗ expectation gates failed — artifacts NOT updated", file=sys.stderr)
        return 2

    print("→ emitting artifacts …")
    result = emit.emit_all(
        parcels, baselines=recon, source_meta=source_meta, incidents=incidents,
        run_id=run_id, snapshot_id=snapshot_id,
    )
    print(f"  wrote {result['features']} features; totals: {result['totals']}")
    print(f"  snapshot {snapshot_id} (run {run_id})")
    print("✓ done")
    return 0


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
