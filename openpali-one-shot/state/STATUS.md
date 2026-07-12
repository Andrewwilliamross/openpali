# Run status

State: `CP4A_COMPLETE__CP4B_CORE_COMPLETE`

Verified checkpoints: CP0 (`edde389`), CP1 (`9c24e27`), CP2 (`0310c98`),
CP3 (`691ea8c`), CP4A+CP4B-core (`d85793e`).

CP4A outcomes (evidence `state/evidence/cp4a-ml-drill-2026-07-12.md`):
- In-cluster ml-drill 11/11: precommitted history gate passes on the
  staggered fixture (11 dates/310d/95.9% coverage), byte-identical dataset
  rebuild, N->N+1 hash change + late arrival + retraction, Cox challenger
  beats KM on IPCW Brier@180 (0.19151 vs 0.19397), append-only promotion
  with named reviewer + predeclared gates, 48-row batch serving from the
  immutable artifact in a fresh process. MLflow + model registry live.
- Representative ledger: ds-59936cf5 (1,127 rows / 811 events) FAILS the
  gate honestly (1 acquisition date) -> challenger emits typed
  INSUFFICIENT_POINT_IN_TIME_HISTORY; baselines still run (KM Brier .184);
  typed insufficiency prediction set pset-3c0f02c2; forecast API returns the
  typed insufficiency for qualifying properties on the live release.
- Repairs: features-v2 (source-agnostic parcel availability), fixture-v2
  (administrative censoring; no cure class; observation-window bitemporal
  bug), object-store overwrite guard proven, MLflow DNS-rebinding hosts.

CP4B-core outcomes (evidence `state/evidence/cp4b-spatial-core-2026-07-12.md`):
- Frozen 4-tile USGS AOI committed pre-execution; live acquisition through
  the production adapter contract (9 immutable raw pages incl. vendor XML);
  GEOID18 grid datum normalization (guarded) -> 1M-surfel 3D-Tiles pyramid +
  231-tile terrarium terrain; content-addressed upload; registry rows carry
  CRS/datum/flight-vs-processing time/rights/lineage/seam 2.5cm/coverage
  reconciliation 1579/1773; release selection (one nonempty version per
  slot; synthetic barred from public kinds) in manifest + gates; spatial API
  routes verified live incl. stale-version 404; representative release
  rel-598f81ab (then superseded by v2-selection republish).
- MULTIMODAL-001 recon-drill 12/12 in-cluster: withheld 1.476m/3deg
  estimated to 0.002m/0.002deg, no-change RMSE 0.162m; production
  registration repaired (salient-point RANSAC; 180-flip + terrain-slide
  reproduced first); candidates with residual-derived confidence; reviewed
  accept/reject/retract; typed unsupported_hardware GPU profile.
- Prefect: 6 deployments incl. spatial-refresh/default.

In progress (CP4B remainder): web renderer wiring of the release-served USGS
surfel + terrain sources (second SplatRenderLayer instance with bakedColor,
release-pinned postfire lib, dual-source picking, legend + detail-card
post-fire evidence — code landed, browser verification pending);
usgs-derive-v2 (picking lon/lat + geoid_offset_m) republish pending; then
SPATIAL-002 renderer instrumentation + measured improvement, methods-review
disposition (ML review agent running), CP4C journeys, CP5 ops.
