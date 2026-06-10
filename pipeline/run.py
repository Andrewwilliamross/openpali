#!/usr/bin/env python3
"""Palisades Rebuild Tracker — pipeline entrypoint.

  uv run run.py              # full live run + emit + validate
  uv run run.py --offline    # use cached raw responses only (ttl=inf)
  uv run run.py --no-validate # skip the oracle reconciliation queries
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone

from palisades import emit, sources, validate
from palisades.score import score_all


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use cache only (ttl=inf)")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()
    ttl = 1e9 if args.offline else 12.0

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
    if not args.no_validate and not args.offline:
        print("→ validating against LADBS oracle …")
        try:
            baselines = validate.oracle_baselines()
        except Exception as e:  # noqa: BLE001 - validation must never block emit
            print(f"  validation skipped ({e})", file=sys.stderr)

    print("→ emitting artifacts …")
    # emit needs the GeoJSON property dicts for reconciliation
    from palisades.model import STAGE_LABELS
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

    source_meta = [
        {"id": "county_base", "as_of": _today_iso(), "ok": True, "records": len(parcels),
         "note": "LA County Parcels Debris Removal (destroyed)"},
        {"id": "ladbs_permits", "as_of": _today_iso(), "ok": True,
         "records": sum(len(p.permits) for p in parcels), "note": "LADBS Palisades Recovery"},
    ]
    result = emit.emit_all(parcels, baselines=recon, source_meta=source_meta)
    print(f"  wrote {result['features']} features; totals: {result['totals']}")
    print("✓ done")
    return 0


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
