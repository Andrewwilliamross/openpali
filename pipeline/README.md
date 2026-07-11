# Palisades Rebuild Tracker — data pipeline

Python ETL that turns fragmented LA city/county fire-recovery data into the static
artifacts the web app serves. Two subsystems share one toolbox:

| Subsystem | Produces | Entrypoint |
|---|---|---|
| **`palisades/`** — 2D rebuild tracker (Phase 1) | `web/public/data/*.json` — per-lot rebuild stage, score, timeline, metrics | `run.py` |
| **`core/spatial/`** — 4D/3D spatial twin (Phase 2–3) | `data/spatial/` GeoParquet store + `web/public/tiles/palisades/` splat pyramid | `run_spatial.py` |

Everything keys on the **10-digit unhyphenated APN**. No backend, no database — the
pipeline emits versioned static files; their git history doubles as a time-series of the
recovery.

## Quick start

```bash
# 2D tracker: fetch live gov APIs → score → emit → reconcile vs official numbers
uv run run.py                 # live
uv run run.py --offline       # rebuild artifacts from cache (no network)
uv run run.py --no-validate   # skip the LADBS oracle reconciliation

# 4D spatial core: LARIAC 3D priors → GeoParquet store (full 5,877-parcel universe)
uv run run_spatial.py             # nightly pass (drains the prior backlog)
uv run run_spatial.py --limit 25  # bound new extractions this run
uv run run_spatial.py --apn 4413008013   # specific parcels

# web-streamable splat tiles from the store (+ picking index, score-tinted)
uv run python -m core.spatial.web_export

# tests
uv run pytest                 # 24 tests (scoring + geodesy + registration + LOD)
```

From the repo root the `Makefile` wraps these: `make data` / `make spatial` / `make test`.

## `palisades/` — the 2D ingestion pipeline

```
sources.py        fetch + normalize every source into Parcel objects (the orchestration)
model.py          domain model: Parcel, Event, Permit; stage bands; milestone classifier
score.py          rebuild score 0–100: stage band + cohort velocity + predicted completion
emit.py           write parcels.geojson / details.json / summary.json / meta.json
validate.py       reconcile computed counts against the LADBS oracle (server-side group-bys)
neighborhoods.py  Pacific Palisades sub-neighborhoods (jump-to + roll-up stats)

http.py           cached, retrying httpx layer (polite to public agency APIs)
arcgis.py         ArcGIS REST FeatureServer paging + counts
socrata.py        Socrata SODA paging + counts
apn.py            APN normalization (the universal join key)
dates.py          epoch-ms / Oracle-string / ISO date parsing
```

**Flow:** the LA County debris-removal layer defines the universe (5,877 destroyed
parcels, with polygon geometry, jurisdiction, debris status, and pre-fire attributes);
the LADBS Palisades Recovery feed overlays the rich permit/inspection/CofO timeline that
drives the score; Malibu + unincorporated lots get a coarser stage from their own status
fields. Endpoints and the join strategy are documented in
[`../Docs/initialbuild_docs/DATA_SOURCES.md`](../Docs/initialbuild_docs/DATA_SOURCES.md);
the score method in
[`../Docs/initialbuild_docs/METHODOLOGY.md`](../Docs/initialbuild_docs/METHODOLOGY.md);
the emitted artifact contract in
[`../Docs/initialbuild_docs/ARTIFACTS.md`](../Docs/initialbuild_docs/ARTIFACTS.md).

**Self-validating.** Every live run re-queries the LADBS feed (the same data behind the
city's official dashboard) and reconciles our parcel counts against it under identical
filters — destroyed and CofO match exactly, permits-issued within ~2%. Drift >5% surfaces
as a data-quality notice rather than a silently-wrong number.

**Honest links.** Official-record permit links are *presence-gated*: each permit is
batch-checked against the City open-data portal and a deep link is attached only when the
record actually resolves; the rest render as plain text (no dead links).

## `core/spatial/` — the 4D/3D spatial twin

```
geodesy.py        exact WGS84 ⇄ ECEF ⇄ ENU transforms; EPSG:2229 (CA State Plane V) → WGS84
schema.py         unified Gaussian-splat state vector + hive-partitioned GeoParquet store (H3 keyed)
scene_client.py   LARIAC 3D building extraction (I3S SceneServer, uncompressed buffer — no Draco)
surfels.py        oriented, coloured disk-Gaussian surfels from mesh vertices + normals
registration.py   rigid alignment: SOR → Mahalanobis → RANSAC coarse → ICP fine (full math)
splat_tiler.py    3DGS octree LOD → 3D Tiles 1.1 + 32-byte .splat tiles
web_export.py     store → web/public/tiles/ (tileset + picking.json + manifest, score-tinted)
runner.py         idempotent nightly job over the full parcel universe (fail-safe, anomaly-flagged)
```

Every spatial primitive — a LARIAC mesh vertex, a registered crowdsourced point, a
trained Gaussian splat — is one row of the state vector `[ECEF xyz, T_epoch, scale, quat,
alpha, SH coeffs, APN]`. The nightly job evaluates the **complete parcel universe** (lots
with no spatial data get explicit `static_baseline` rows — never dropped), is idempotent,
and isolates per-source/per-parcel failures (preserving the last valid asset). Full design
in
[`../Docs/initialbuild_docs/SPATIAL_CORE.md`](../Docs/initialbuild_docs/SPATIAL_CORE.md).

## Conventions

- **Join key:** 10-digit APN, dashes stripped (`apn.normalize_apn`). DINS counts
  *structures*; we count *parcels* — never validate one against the other.
- **Dates:** ArcGIS layers return epoch-ms, USACE ROE timestamps are Oracle strings,
  Socrata is ISO — all normalized in `dates.py`.
- **Rebuild stage** is driven only by `PERMIT_TYPE='Bldg-New'`; pools/demo/grading appear
  as permit records but don't advance the stage.
- **Caching:** raw upstream responses cache under `data/raw/` (gitignored); `--offline`
  runs entirely from cache. The LARIAC scene layer is a static snapshot, cached forever.

## Layout

```
palisades/        2D ingestion package
core/spatial/     4D/3D spatial core package
tests/            pytest suite (test_score, test_spatial, test_spatial_integration)
run.py            2D pipeline entrypoint
run_spatial.py    spatial-core entrypoint
pyproject.toml    uv project (httpx, pandas, shapely, numpy, scipy, pyproj, pyarrow, h3, …)
```
