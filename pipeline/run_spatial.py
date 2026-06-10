#!/usr/bin/env python3
"""openpali Phase 2 — nightly spatial-core entrypoint.

  uv run run_spatial.py                       # full nightly pass (drains backlog)
  uv run run_spatial.py --limit 25            # bound new extractions this run
  uv run run_spatial.py --apn 4413008013 ...  # specific parcels only
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.spatial.runner import DEFAULT_STORE, run_nightly


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="max NEW prior extractions this run (backlog drains nightly)")
    ap.add_argument("--apn", action="append", default=None,
                    help="restrict to specific APN(s); repeatable")
    ap.add_argument("--store", type=Path, default=DEFAULT_STORE)
    args = ap.parse_args()

    report = run_nightly(store_root=args.store, limit=args.limit, apns=args.apn)
    j = report.to_json()
    print(f"universe          {j['universe']}")
    print(f"priors existing   {j['priors_existing']}")
    print(f"priors extracted  {j['priors_extracted']} (+{j['priors_footprint_fallback']} footprint fallback)")
    print(f"static baseline   {j['static_baseline']}")
    print(f"stale cached      {j['stale_cached']}")
    print(f"anomalies         {len(j['anomalies'])}")
    for a in j["anomalies"][:8]:
        print(f"  ⚠ {a['source']}: {a['error'][:120]}")
    print(f"({j['duration_s']}s) → {args.store}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
