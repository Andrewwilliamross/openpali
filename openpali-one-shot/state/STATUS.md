# Run status

State: `CP4B_COMPLETE_EXCEPT_RENDERER_IMPROVEMENT`

Latest verified (commits through b82ac3a + bench-budget commit):
- Browser evidence PASSED in-cluster (2/2 specs, evidence
  cp4b-browser-evidence-2026-07-12.md): release-qualified USGS tile
  requests, instanced draw calls, AOI picking -> post-fire badge, legend
  flight-date label, 2D journey + release-served hillshade.
- ml-drill 12/12 with ALL methods repairs; representative rerun: typed
  insufficiency at dataset/challenger/serving; fixture-champion domain
  refusal verified live.
- Rights gate LIVE in the public manifest: release rel-970232d7 lists
  lariac-prefire-scene (rights_state=unresolved) and recon-fixture-scene
  (synthetic) under `excluded` with reasons.
- SECURITY.md committed. renderer-bench job exists; budgeted v2 run in
  flight — its numbers pick the SPATIAL-002 improvement (before/after still
  owed).

Verified checkpoints: CP0 (`edde389`), CP1 (`9c24e27`), CP2 (`0310c98`),
CP3 (`691ea8c`), CP4A+CP4B-core (`d85793e`), methods repairs + web wiring
(`8261fb7`, `fca910d`).

CP4A (evidence: cp4a-ml-drill / cp4a-methods-review-disposition):
- Drill 12/12 IN-CLUSTER after two independent methods reviews:
  chronological rolling-origin-v2 folds (leaky interleave fixed), promotion
  gates enforced fail-closed (final_holdout_only for challenger AND KM
  comparator, calibration fail-closed, per-cohort regression gate,
  real dataset-contracts check, reviewer validation) — the drill PROVES a
  fold-evaluated model is refused, then promotes one final-holdout
  evaluation (cox 0.01667 vs km 0.04278 forward fold).
- IPCW left-limit + floor diagnostics, horizon-honest naive baseline,
  Cox Schoenfeld PH test + coefficients logged, champion DOMAIN gate
  (fixture-trained champion structurally refused for civic serving —
  verified live on the representative rerun), extrapolation disclosure,
  serving decoupled from the parcel gate for origin-derived covariates.
- Representative ledger rerun: typed INSUFFICIENT_POINT_IN_TIME_HISTORY at
  dataset+challenger+serving (pset-bd145931) with per-cohort metrics.
- 8 new ML unit tests; 161 pipeline tests green.

CP4B (evidence: cp4b-spatial-core + this session):
- USGS spatial pipeline live end-to-end (see cp4b evidence file):
  usgs-derive-v2 selected by release rel-f678e840 with superseded version
  listed (stale-tile prevention live); manifest geoid_offset_m -36.2;
  picking with per-parcel lon/lat (1,578 parcels).
- MULTIMODAL-001 recon drill 12/12; GPU probe typed unsupported_hardware.
- Web wiring landed: release-pinned postfire discovery, second
  SplatRenderLayer (bakedColor, no pre-fire texturing), post-fire DEM
  hillshade, dual-source picking, legend + detail-card provenance, renderer
  draw stats, /v1 dev proxy.
- BROWSER EVIDENCE (containerized Playwright job e2e-browser through the
  egress proxy; SwiftShader = correctness only): spatial spec PASSED —
  release-qualified tile requests, instanced draw calls, AOI picking ->
  detail card with post-fire badge, legend flight-date label. 2D-journey
  spec result pending at last check.
- Chromium cannot run under the macOS Bash sandbox (Mach port denial) —
  browser evidence MUST use the e2e-browser/renderer-bench compose jobs.
- renderer-bench job added (deterministic 4-scene frame-time/draw/memory/
  request report) — baseline run pending; profiling-selected improvement +
  before/after still open (SPATIAL-002).

Next: finish e2e 2D spec, run renderer-bench baseline, pick + land measured
renderer improvement, LARIAC tracked-corpus rights registration (unresolved,
excluded) — then CP4C journeys (React Router routes, release-pinned client,
axe), CP5 (check-full, CI, SBOM, observability alert, schedule drill,
worker kill/resume, restore drill, SECURITY.md, CofO disclosure wiring),
CP6 terminal protocol.
