# Run status

State: `CP3_ORCHESTRATION_PUBLICATION_COMPLETE`

Verified checkpoints: CP0 (`edde389`), CP1 (`9c24e27`), CP2 (`0310c98`),
CP3 (this commit).

CP3 outcomes (all worker-executed and host-verified; evidence in
`state/evidence/cp3-representative-release-2026-07-12.log` and
`cp3-replay-and-faults-2026-07-12.md`):
- All 7 named sources through ONE production contract via registered Prefect
  deployments on the process worker: county (5,877), LADBS permits (5,339),
  LADBS inspections (1,014), Malibu (269), CAL FIRE DINS (12,137 — 7,340
  APN/spatial-joined, 0 ambiguous, 5 without APN, damage distribution
  recorded), Socrata permits bbox (9,881) + CofO (2,957) cross-checks.
- Representative release rel-27386c5f: snapshot with 27,266 observation
  members incl. 7,340 DINS damage assessments (interval-censored) and 904
  inspection observations; coverage matches corrected CP1 statics (5,877 /
  3,964 cleanup / 1,205 apps / 965 issued / 27 CofO).
- ZERO-NETWORK replay job (internal network, no proxy env): 35 raw pages
  digest-verified; 32,459 observations recomputed byte-deterministically, all
  in ledger; REPLAY OK.
- Analytics engine: versioned catalog (universe, lane/milestone prevalence,
  weekly incidence, censoring-aware KM time-to-issuance median 99d [96,104]
  n=1,126, P(issue≤180d)=0.822, backlog 315/inflow 46/outflow 49/net −3,
  missingness incl. 140 undated applications) + independent reconciliation:
  county server count 0.0% drift PASS; Socrata portal presence of our issued
  qualifying permits 99.88% PASS; CofO cross-portal 13.8% vs predeclared 30%
  tolerance FAIL (honestly recorded; investigate pcis_permit format/lag —
  metric-level disclosure wiring in CP5).
- Publication: gates fail closed; two-pinned-sessions, mirror-failure drift,
  rollback drills pass (9 in-cluster integration tests); ops.job_run rows
  reconcile Prefect flow-run IDs; release-rollback CLI.
- Metrics/bottlenecks/export.csv API routes (13 paths total), TS client
  regenerated.
- Squid peers pinned to static compose IPs (stale-DNS eliminated); db-stats
  ops probe job.

Repairs this checkpoint: inspections/DINS adapter out_fields (missing
OBJECTID/GLOBALID keys), snapshot membership now uses STORED observation IDs
(recomputed-vs-stored divergence class removed), psycopg 65k-param chunking,
replay verdict bitemporality semantics.

CP4A groundwork already written (not yet exercised): point-in-time dataset
builder with precommitted history gate, experiments ladder (naive/KM/Cox +
MLflow + IPCW Brier + calibration/cohorts), registry with predeclared
promotion gates, gated batch serving, temporal fixture + N→N+1 drill.

Immediate next action: exercise CP4A end-to-end in-cluster (fixture ledger →
dataset → experiments → promotion → serving → drill; representative dataset →
INSUFFICIENT_POINT_IN_TIME_HISTORY), forecast API route, methods-review of the
experiment protocol; then CP4B spatial.
