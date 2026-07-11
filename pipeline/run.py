#!/usr/bin/env python3
"""Palisades Rebuild Tracker — pipeline entrypoint.

  uv run run.py              # full live run + emit + validate
  uv run run.py --offline    # use cached raw responses only (ttl=inf)
  uv run run.py --no-validate # skip the oracle reconciliation queries
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from palisades import checks, emit, provenance, sources, validate
from palisades.score import score_all


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
    parcels = sources.build_parcels(ttl_hours=ttl)
    print(f"  {len(parcels)} destroyed parcels")
    if not parcels:
        print("ERROR: no parcels — aborting", file=sys.stderr)
        return 1

    print("→ scoring …")
    cohort = score_all(parcels, today=date.today())
    for s in (2, 3, 4):
        st = cohort[s]
        print(f"  stage {s}: median {st['median']:.0f}d (n={st['n']})")

    # stage histogram
    from collections import Counter
    hist = Counter(p.stage for p in parcels)
    print("  stage histogram:", dict(sorted(hist.items())))
    print("  jurisdictions:", dict(Counter(p.jurisdiction for p in parcels)))
    print("  coarse parcels:", sum(1 for p in parcels if p.coarse))

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
        {"apn": p.apn, "jurisdiction": p.jurisdiction, "stage": p.stage}
        for p in parcels
    ]
    recon = validate.reconcile(prop_dicts, baselines) if baselines else []
    if recon:
        print("  reconciliation vs official:")
        for r in recon:
            flag = "✓" if r["ok"] else "⚠"
            print(f"    {flag} {r['metric']:32s} official={r['official']:>5} ours={r['ours']!s:>5} drift={r['drift_pct']}%")

    print("→ expectation gates …")
    source_meta = sources.source_health()
    prev_summary = _read_json(emit.OUT_DIR / "summary.json")
    prev_meta = _read_json(emit.OUT_DIR / "meta.json")
    incidents = checks.run_gates(parcels, source_meta, recon, prev_summary, prev_meta)
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
