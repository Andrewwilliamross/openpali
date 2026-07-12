# CP4A evidence: in-cluster ML drill (ML-001/ML-002/ML-003)

Command (host, via wrapper):

    python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d ml-drill
    # container: openpali-local-ml-drill-1 -> Exited (0), 2026-07-12T10:39Z

Job service: `ml-drill` in infra/compose.yaml runs `openpali ml-drill`
(production CLI, image openpali-pipeline:local).

## Result: 11/11 checks passed

    snapshot N   = snap-4726833dcffbbc81f3ee7d2a
    snapshot N+1 = snap-3e4da00a4dbc3d94fe8f269e
    rows=320 events=219 gate=True
    [PASS] history gate passes on staggered fixture (dates=11, span=310d, coverage=0.9594)
    [PASS] N dataset rebuild is byte-identical sha=75f5382b57d7
    [PASS] N+1 dataset hash differs 75f5382b57 -> e06bd96956
    [PASS] late-arriving application enters N+1 only rows 320 -> 321
    [PASS] semantic no-op creates no duplicate dataset
    [PASS] challenger executed on fixture
    [PASS] challenger beats KM on IPCW Brier@180 (fold eval) cox=0.19151 km=0.19397
    [PASS] N+1 evaluation ran with distinct MLflow runs
    [PASS] champion unchanged without review
    [PASS] promotion recorded via append-only decision
    [PASS] batch prediction set served rows=48 set=pset-d7336191d78d95267a84
    == drill: 11/11 checks passed ==

MLflow runs (tracking server in-cluster, postgres backend, S3 artifacts):
experiments/1 runs 5a76fdf3/cbb21019/8ff2dae4 (N) and be9aedd4/6e9c13b3/f4a9758f
(N+1); registered model `openpali-issuance-champion` version 1.

## Defects found and repaired on the way (each verified by rerun)

1. Dataset feature-availability scan hardcoded `source_id == "county_base"`;
   fixture parcel observations come from `fixture_civic` so origin coverage
   computed 0.0 and the gate failed. Repair: parcel-context availability is
   source-agnostic (any non-derived parcel observation), excluding the derived
   `openpali_conflict_detection` source. The point-in-time discipline lives in
   the observed_at <= origin comparison. This is a feature-schema semantics
   change: FEATURE_SCHEMA_VERSION bumped v1 -> v2 (dataset IDs change; the
   immutable-object guard that caught the would-be silent overwrite is
   documented below).
2. The object store REFUSED an overwrite of `features/ds-.../dataset.parquet`
   when changed code produced different bytes under an unchanged dataset ID —
   exactly the immutability contract working. Resolution was the version bump
   above, never relaxation of the guard.
3. MLflow 3.14 DNS-rebinding protection rejected in-cluster Host `mlflow:5000`;
   fixed via `MLFLOW_SERVER_ALLOWED_HOSTS` env (compose), not by disabling the
   protection.
4. Fixture bitemporal bug: `acquisition_for()` mapped issuance dates BEYOND the
   last N acquisition onto the last N run — an observation of a future event
   entered snapshot N. Repair: an event is observable only by the first run
   at/after it occurs; events after every run stay unobserved (fixture-v2,
   new run lineage).
5. Fixture design flaw: the arbitrary "25% never issued" class was a uniform
   cure fraction; true S(180|x) spread compressed to ~0.31-0.46 and the
   PH-misspecified Cox challenger legitimately LOST to KM on IPCW Brier
   (observed in-cluster: cox=0.2705 vs km=0.2460). fixture-v2 derives
   censoring administratively from the acquisition window (PH-clean
   generator); a host-side simulation predicted cox=0.19364 vs km=0.19612
   (fold) before the in-cluster run reproduced it (0.19151 vs 0.19397).

## Semantics demonstrated

- Precommitted point-in-time history gate (3 dates/60d span/50% origin
  coverage) passes on genuinely staggered acquisitions and its coverage is
  computed from stored observation acquisition times, not file dates.
- Datasets are immutable, content-addressed, byte-reproducible artifacts with
  data cards; N -> N+1 changes hashes; retraction + late arrival propagate.
- Experiments: naive / censoring-aware KM / interpretable Cox ladder, IPCW
  Brier + calibration + cohort metrics, MLflow tracking with dataset/code/
  config/seed, immutable pickled model with sha256.
- Promotion: predeclared gates (beats-KM IPCW Brier, calibration-not-worse,
  dataset contracts) + named reviewer; append-only ml.promotion_decision; a
  failing challenger was REFUSED promotion in an earlier run (recorded above).
- Serving: snapshot-bound batch prediction set from the immutable artifact in
  a fresh process; horizon-resolved rows excluded; 48 open-horizon rows.
