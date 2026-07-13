# CP3 zero-network replay + fault injection — 2026-07-12

## Zero-network replay (job `replay`, internal network, NO proxy env — the
## process is physically incapable of egress)

```
replaying release rel-27386c5fa5ab8620f95e22ab (7 input runs), snapshot snap-839abf837b0bd0ad8f5878a8
  replayed county_base: 5877 records (7 verified raw pages)
  replayed ladbs_permits: 5339 records (7 verified raw pages)
  replayed ladbs_inspections: 1014 records (3 verified raw pages)
  replayed malibu_dash: 269 records (1 verified raw pages)
  replayed calfire_dins: 12137 records (14 verified raw pages)
  replayed socrata_permits: 9881 records (2 verified raw pages)
  replayed socrata_cofo: 2957 records (1 verified raw pages)
recomputed observations: 32459; in ledger: 32459
membership (non-derived): 27266; reproduced from this release's bytes: 27265;
from earlier acquisitions of the same sources: 1
REPLAY OK: exact raw hashes reproduced the release's semantic observations
```

Every raw page read is size+digest verified (`ObjectStore.get_verified`).
The single member observation not derived from this release's pages is an
assertion first observed in an earlier acquisition of the same source —
correct bitemporality (assertions observed ≤ cutoff remain visible), each
independently replayable from its own pages.

## Fault injection (job `test-integration`, 9 passed)

- object store: content dedup, different-byte overwrite rejection, digest-
  verified reads, corrupted-expectation rejection;
- ledger idempotent reload (0 new on replay), point-in-time visibility
  (late-arriving earlier-occurrence excluded before its observed_at),
  snapshot rebuild no-op;
- publication: gate failure keeps current untouched (fail closed) while LKG
  stays readable; two pinned browser/API sessions never mix releases across a
  promotion; cross-release cursor reuse rejected (400);
- mirror failure: promotion succeeds with mirror_ok=False, DB stays sole
  authority, pointer drift detectable;
- rollback: LKG promoted back, rolled-back release becomes unaddressable
  (404), restored release serves coherently.

NOTE (CP5): the fault suite mutates the live current pointer; the
representative release was re-promoted afterwards through the
release-candidate deployment (worker-executed, state=Completed). CI isolation
for these tests lands with the full-gate work.

## Prefect worker executions (registered deployments, process pool)

- full-refresh-release/default → Completed: 7/7 sources through acquisition →
  ledger → snapshot (27,266 members) → analytics → gated atomic publication
  (release rel-27386c5f..., ~90 s end to end).
- release-candidate/default → Completed (re-promotion).
- Typed retry policy: only `transient` acquisition failures retry;
  schema/mutation/semantic failures fail immediately (flows.py).
