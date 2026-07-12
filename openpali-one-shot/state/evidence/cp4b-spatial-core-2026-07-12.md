# CP4B core evidence: USGS spatial pipeline + reconstruction fixture

All commands host-executed via `python3 openpali-one-shot/scripts/docker_safe.py
-f infra/compose.yaml ...`; containers on image `openpali-pipeline:local`.

## Frozen AOI (committed BEFORE execution)

`pipeline/openpali/spatial/palisades_aoi.geojson`: four independently
requested USGS LOD tiles (Prelim_11SLT00358*/00359*), UTM block
358500,3767250 -> 360000,3768750 (EPSG:6340), WGS84 -118.532835,34.036386 ->
-118.516832,34.050111; 1,728 destroyed parcels verified inside pre-freeze
(1,773 by ST_Intersects at derive time — both >= the required 25).

## Live acquisition through the production contract (`up -d spatial-refresh`)

- Adapter `UsgsDemAdapter` (openpali/spatial/usgs.py) through the SAME
  run_acquisition contract as all civic sources: 9 pages (vendor XML + 4
  GeoTIFF 9,443,436 B each + 4 .tfw), content-addressed into openpali-raw,
  AcquisitionRun run-b47398872d234bcabfbbc00b (re-run converged idempotently
  as run-70cc633b521af9d495972ac7 with identical page digests — dedup
  observed in object store).
- .tfw georeference validated against the frozen AOI bounds at acquisition;
  TIFF magic checked; flight window (2025-01-21) parsed from vendor FGDC XML
  — acquisition time is the flight, ingest time is the run, processing time
  is separate (`processed_at`).
- Egress through the labeled squid proxy only (prd-tnm.s3.amazonaws.com on
  the documented allowlist; cdn.proj.org added for the NOAA GEOID18 grid).

## Derivation (openpali spatial-derive, in-cluster)

    version sv-20dcacc0c8ac9d4142af
    surfels: 1,000,000 (1.5 m spacing, hillshade grey, flight-date t_epoch)
    datum: EPSG:6340 + NAVD88(GEOID18) -> WGS84 ellipsoidal via us_noaa_g2018u0
      grid (pyproj, allow_ballpark=False, LA undulation band guard) -> ECEF
    seam quality: median seam step 0.0249 m vs interior 0.0246 m (coherent)
    parcel attribution: county parcel polygons rasterized onto the DEM grid;
      reconciliation {intersecting: 1773, destroyed: 1773, with_dem: 1579,
      coverage 89.06%} recorded on the asset
    surfel tileset: 320 files / 33.7 MB -> s3://openpali-spatial/assets/...
      (3D Tiles splat pyramid via core.spatial.splat_tiler + picking.json)
    terrain: 231 terrarium PNG tiles z13-18 / 12.1 MB, NAVD88 heights
      documented; center-pixel decode 92.6 m NAVD88 (plausible Palisades)

## Registry + release + API (verified live)

- spatial.spatial_asset rows carry CRS/vertical datum/acquisition window/
  observation kind (post_fire_observation)/rights (public_domain)/transform
  lineage/seam residual/coverage/quality; AssetRelation derived_from x4 raw.
- Release selection (latest-ready-rights-safe-v1): exactly one nonempty
  version per (subject, kind, vintage_slot); EmptySlotError on empty enabled
  slots; synthetic fixture assets TECHNICALLY excluded from non-fixture
  releases (verified in the recon drill AND visible as `excluded` in the
  live manifest).
- Representative release republished through the registered
  release-candidate/default deployment on the process worker: flow_run
  4e1a8e6a Completed -> release rel-598f81ab225e15ccf661f1e0 (same snapshot
  snap-839abf83; undocumented values now re-derived from run health inside
  the flow).
- API (all exercised over the accel proxy, immutable ETags):
  - GET /v1/releases/rel-598f81ab/spatial/assets -> both USGS assets with
    full truth model + excluded recon-fixture-scene with reason
  - manifest.json/tileset.json/picking.json/L0 splat payload served
  - terrain 15/5595/13085.png -> 72 kB PNG, decoded elevation 92.6 m
  - foreign/stale version -> 404 ("stale or foreign asset versions are not
    served")

## MULTIMODAL-001 drill (`up -d recon-drill`): 12/12

    [PASS] gate translation_error_m <= 0.15 value=0.002
    [PASS] gate rotation_error_deg <= 0.5 value=0.002
    [PASS] gate aligned_rmse_nochange_m <= 0.2 value=0.1622
    [PASS] fused asset tiled and registered recon-fixture-scene@sv-6679fee9eae
    [PASS] synthetic asset technically barred from public releases
    [PASS] change + control candidates proposed confidences=[0.416, 0.416]
    [PASS] candidate carries full truth model
    [PASS] no civic observation exists before review n=0
    [PASS] acceptance appends exactly one observation
    [PASS] rejection appends nothing
    [PASS] rejected candidate cannot be accepted later
    [PASS] retraction is an append-only revision (observation preserved)

Fixture: two partially overlapping views (26,972 / 25,292 pts incl. 4%
clutter), 40-degree occlusion wedges per view, mixed change/no-change
regions, withheld transform |t|=1.476 m / 3.0 degrees. The PRODUCTION
pipeline (core.spatial.registration: SOR -> Mahalanobis -> RANSAC ->
chi^2-gated ICP) estimated it to 0.002 m / 0.002 degrees; aligned no-change
RMSE 0.162 m on production-admitted points.

Registration robustness repair (production code, reproduced-before-fixed):
descriptor RANSAC on ground-dominant scenes rewarded "slide along the
terrain" and "180-degree flip" hypotheses (observed: 12.9 m/180.0 deg, then
14.5 m/5.9 deg). ransac_coarse_align now samples and scores consensus on
geometrically SALIENT points (local vertical extent >= 1 m) with full-cloud
fallback when vertical structure is sparse. Existing parcel-scale
registration tests still pass (153 passed / 10 skipped).

## GPU worker boundary (`--profile gpu up -d recon-gpu`)

    {"status": "unsupported_hardware",
     "requirement": "NVIDIA GPU with driver (nvidia-smi + /dev/nvidia*)", ...}

Typed refusal, exit 0 — never a crash, never a silent CPU fallback.

## Forecast route on the live release (ML-003 user-facing)

    GET /v1/releases/rel-598f81ab/properties/prop-ecdf6b83.../forecast ->
    {"status": "insufficient_evidence",
     "reason": "INSUFFICIENT_POINT_IN_TIME_HISTORY",
     "prediction_set_id": "pset-3c0f02c2354da718918c", ...}

## Prefect

6 deployments registered on openpali-process (adds spatial-refresh/default).

## Remaining for CP4B/SPATIAL-002 (tracked, not claimed)

Renderer wiring of the USGS tileset + terrain through the web client
(draw/picking/legend/property evidence), measured renderer improvement with
deterministic before/after scenes, two-epoch + coverage-reconciliation
integration tests, LARIAC tracked-tile rights-gate object policy.
