# Verified starting baseline

Captured 2026-07-11 in `/Users/andrewross/paliml` at commit `c59bc64` on
`main`. Fable must reproduce time-sensitive facts in the exact prepared local
checkout and record corrections in mutable state rather than editing this file.

At preparation time, that local commit was an ancestor of `origin/main` and 18
remote commits behind it (`origin/main` at `4e2301f`). The remote line already
contained overlapping provenance/contracts and 2D/3D work. The experiment must
not start from either side implicitly: Andrew must fetch, preserve the dirty
local work on a safe branch, and reconcile the intended snapshot first.

## Repository and working tree

The repository is a compact static application, not yet a platform:

- Python 3.12/`uv` pipeline under `pipeline/`.
- React 19, TypeScript 6, Vite 8, and MapLibre 5 client under `web/`.
- Four civic JSON artifacts under `web/public/data/`.
- GeoParquet spatial state and a custom WebGL2 splat renderer.
- No database, backend API, GitHub Actions, deployment workflow, container,
  scheduler, top-level `LICENSE`, `SECURITY.md`, or privacy policy.

The working tree was dirty before this harness was added. It contained modified
README/pipeline/type files, a `docs/` to `Docs/initialbuild_docs/` reorganization,
untracked production-readiness documents, and `data/runs/`. These are user-owned
changes. The launch preflight requires Andrew to commit the intended snapshot so
Fable sees it in the same checkout; Fable must never reset, clean, stash, or
overwrite it implicitly.

## Shared local tool environment

The preparation environment contained the actual repository, local public-data
caches/artifacts, and the same tool surface Fable will receive:

- Claude Code 2.1.207;
- `uv` 0.8.24 and Python 3.14 on the host, with the project locked to Python
  3.12 or newer;
- Node 24.9.0 and npm 11.6.0;
- Docker 28.5.1 and Docker Compose 2.40.3;
- Git and authenticated GitHub CLI; and
- the React browser project plus the checked-in civic and spatial artifacts.

Preparation did not prove Docker daemon state, account-level Fable entitlement,
GPU availability, free disk, browser binaries, or every native library. The
preflight and Fable must probe these at launch. The current checkout and tool
access are the starting environment; a linked Git worktree would only isolate
source edits and would omit untracked local state, so this harness does not
create one.

## Local verification

Observed commands and results:

| Command | Result |
|---|---|
| `cd pipeline && uv run pytest -q` | 35 passed in 2.11s |
| `cd web && npm test -- --run` | 17 passed |
| `cd web && npm run build` | passed; JS 1,262.55 kB minified / 348.88 kB gzip; chunk warning |
| `cd web && npm run lint` | failed with 5 errors |

Lint failures were at `MapView.tsx:72,74`,
`ParcelDetailCard.tsx:43`, `SplatRenderLayer.ts:325`, and
`spatial_intersector.ts:103`.

Existing tests concentrate on score math and spatial primitives. There are no
meaningful ingestion/source-contract, offline, emission, reconciliation,
artifact-schema, App/MapView, browser E2E, accessibility, or deployment tests.

## P0 public-truth defects

### Scheduled inspections become physical construction

`pipeline/palisades/sources.py:233-256` maps any recognized inspection
description to a stage-4 event without filtering `INSP_STATUS`.

The checked-in `details.json` contains:

- 817 inspection events across 500 parcels;
- all 817 labeled `(insp scheduled)`;
- 10 dates later than the artifact's 2026-06-11 generation date;
- 489 parcels publicly counted as `under_construction`.

The live inspection table returned only `INSP_STATUS='Insp Scheduled'` (1,014
rows) when grouped on 2026-07-11. Scheduled, failed, canceled, not-ready, or
future activity is not evidence that a milestone was reached.

### Ancillary permits can advance the rebuild

`attach_ladbs_permits` inserts every permit into `permit_to_apn` before its
`Bldg-New` test (`sources.py:186-204`); `attach_inspections` then attaches every
matched permit's inspection as a construction event.

In the publication:

- 26 of 489 stage-4 parcels have no `Bldg-New` permit;
- 32 have no issued `Bldg-New` permit;
- APN `4412014020` is one example with only grading permits and a scheduled
  “Rough” inspection.

### Missing cleanup facts are fabricated

`sources.py:159-164` treats any `opt-out` as cleared and replaces a missing
completion date with `FIRE_START`.

- 1,595 “Lot cleared (private opt-out)” events all use 2025-01-07.
- In total, 1,620 debris-cleared events use the fire date fallback.

Opting out selects a cleanup path; it does not itself prove completion. Missing
effective dates must remain unknown or interval-censored, not become fire-day
events. `attach_inspections` similarly falls back to `date.today()` for missing
inspection dates.

### “Fire rebuild” is not defined in code

The LADBS query fetches `PALISADES_WF_REBUILD` but ignores it; every
`PERMIT_TYPE.startswith('Bldg-New')` can advance a destroyed parcel.

In the cached 4,861-row LADBS snapshot:

- 1,047 `Bldg-New` rows are marked Rebuild;
- 735 are marked No;
- 544 destroyed-universe APNs have only `Bldg-New/No` records but are shown at
  stage 2 or higher.

The field's official semantics and the correct qualifying cohort need source-
owner or official-dashboard verification. Do not guess.

### Current reconciliation is circular and does not protect publication

`pipeline/palisades/validate.py` re-queries the same County and LADBS sources
with similar predicates. It has no `under_construction` oracle, no row-level
golden cases, and publishing continues on failure.

The 2026-06-29 reconciliation artifact records:

- destroyed: 5,877 vs 5,877;
- Bldg-New application parcels: 1,558 vs 1,604;
- issued parcels: 1,008 vs 1,033;
- CofO: 16 vs 21, a failing 23.8% drift.

## Reproducibility and lineage defects

- `--offline` only changes cache TTL. Cache misses still perform network I/O
  (`run.py:21-27`, `http.py:58-66`).
- `source_meta` hard-codes `ok: true`, labels run time as source `as_of`, and
  omits inspections, Malibu, and Socrata (`run.py:68-73`).
- Checked-in civic artifacts were generated 2026-06-11 and are stale relative
  to this baseline.
- ArcGIS paging has no stable object-ID snapshot/order.
- Raw cache files lack an immutable run manifest, content hash ledger, schema
  fingerprint, and row lineage.
- JSON files are written sequentially, so a crash can publish mixed vintages.
- There is no shared snapshot ID across civic JSON, tiles, picking index, and
  spatial assets.

Direct layer metadata on 2026-07-11 showed the County debris layer had a
2026-07-10 data edit and the LADBS permit layer a 2026-07-11 data edit. Search
indexes and aggregate service pages can be stale; snapshot exact layer metadata
(`FeatureServer/0?f=pjson`) during every run.

## Score and modeling baseline

`score.py` is a communication heuristic, not a learning or validated forecast
system:

- fixed arbitrary stage bands and unsourced priors;
- medians computed only from parcels that advanced, ignoring right-censoring;
- no point-in-time training set, temporal split, calibration, interval coverage,
  model version, data cutoff, registry, drift monitor, or champion/challenger;
- one Early/Mid/Late year label without a calibrated interval or sample size;
- stage-1 parcels receive nearly identical ETAs regardless of wait time;
- invalid inspection and cleanup labels contaminate stages and durations.

`summary.json` has an empty `baselines` list. Forecasting and causal policy
evaluation are separate research questions; prediction performance cannot prove
intervention impact.

## Spatial and product baseline

The checked-in spatial manifest reports 10,016,113 splats, 4,976 parcels,
2,375 nodes, and 326,829,952 bytes. The civic denominator is 5,877 parcels, so
901 lack rendered scan coverage.

The current 3D layer is primarily a pre-fire LARIAC-derived mesh/surfel context
tinted by the civic score—not current construction geometry and not a learned,
continually updated 3D Gaussian reconstruction. Additional gaps:

- extraction time is stored as acquisition time;
- `.splat` output drops `t_epoch`;
- registration is unused outside tests;
- footprint fallback emits `mesh_vertices`, while web export reads `splats`;
- store reads can select every epoch instead of one snapshot;
- 3D loads by default and the static tile payload is about 318 MiB;
- the initial JS bundle is about 349 KiB gzip;
- client data loads roughly 4.7 MB GeoJSON plus 4.3 MB details JSON eagerly;
- source-health/reconciliation failures are not visible to users.

The code hotlinks EagleView/Pictometry LARIAC imagery and distributes derived
LARIAC 3D assets. LA County item metadata describes this as licensed content for
LARIAC members, and the consortium NDA restricts use/disclosure. Reachability is
not a redistribution or training license. Default-disable unresolved assets.

Esri Wayback release identifiers/dates are publication releases, not necessarily
image acquisition dates. Per-location/tile metadata must support capture-date
claims.

## Baseline interpretation

The strongest path to community impact is not a larger score formula, and it is
not truth repair alone. The baseline demands a connected build:

1. trustworthy source semantics and immutable bitemporal observations;
2. persistent geospatial storage, object artifacts, orchestration, typed APIs,
   fail-closed snapshots, last-known-good, and rollback;
3. auditable property timelines and community bottleneck measures;
4. an executed point-in-time continual-learning system with baseline,
   challenger, tracking, gated reevaluation, and honest serving;
5. an operational rights-safe spatial/reconstruction path plus measured 2D/3D
   renderer improvements; and
6. a fast, accessible API-backed product with CI, observability, security, and
   recovery operations.
