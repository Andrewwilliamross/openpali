# Palisades Rebuild Tracker

By RE\SPRING (respring.ai) · open-source

A single web map of Pacific Palisades where **every lot destroyed in the January 2025
Palisades Fire is color-coded by how far along its rebuild is** — from deep red ("no
permit on file") through orange/yellow ("in plan check", "permitted") to green ("under
construction", "complete"). It pulls live from city and county data systems and turns
fragmented permit records into one glanceable picture of the recovery, lot by lot.

> Run `make web` and open the app to see all 5,877 destroyed lots rendered live.

## Why

The data exists — LADBS permits, LA County dashboards, CAL FIRE damage assessments,
USACE debris records — but it's scattered across a dozen systems and presented as
aggregate counts. No tool answers the simple question a returning resident actually has:
*how far along is my block?* This does.

## How it works

```
pipeline/ (Python)              web/ (React + MapLibre)
  fetch live gov APIs   ──►  parcels.geojson   ──►  full-screen map, score gradient
  normalize on APN           details.json           click → Zillow-style lot card
  score each lot 0–100        summary.json           address search + neighborhood nav
  emit static JSON            meta.json              headline metrics + permit sparkline
```

No backend, no database — the pipeline emits static JSON that a static site serves.
Cheap, durable, forkable. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### The rebuild score

Each lot gets a 0–100 score that blends its current permit/inspection **stage** with how
it's **moving** relative to its cohort — so a lot permitted last week looks different from
one permitted eight months ago with no inspection since. Full method:
[docs/METHODOLOGY.md](docs/METHODOLOGY.md).

### Data sources

Built on LA County's and LA City's pre-joined parcel layers, enriched with the LADBS
per-permit feed (the rich timeline), construction inspections, CofO records, USACE debris
status, Malibu's rebuild dashboard, and Esri Wayback pre-fire imagery. Every endpoint is
documented and was live-verified: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

Pipeline output **reconciles against the official LADBS dashboard** every run (destroyed
parcels and CofO count match exactly; permits-issued within ~2%).

## Run it

```bash
# 1. data pipeline  →  writes web/public/data/*.json
cd pipeline
uv run run.py                 # live fetch + score + emit + validate vs official numbers
uv run run.py --offline       # rebuild artifacts from cache (fast, no network)
uv run pytest                 # scoring engine unit tests

# 2. web app
cd ../web
npm install
npm run dev                   # http://localhost:5173
npm run build                 # static site → web/dist/
```

## Phase 2 — 4D spatial twin core

`pipeline/core/spatial/` extends the tracker into a spatiotemporal 3D dataset:
LARIAC 3D building extraction (I3S, no Draco), a unified Gaussian-splat-ready
state model in partitioned GeoParquet keyed by H3 + APN, a full RANSAC+ICP
registration engine for crowdsourced captures, and a 3D Tiles 1.1 LOD tiler
for web-streamable splats. See [docs/SPATIAL_CORE.md](docs/SPATIAL_CORE.md).

```bash
cd pipeline && uv run run_spatial.py --limit 25   # nightly; drains the prior backlog
```

## Keeping data fresh

The pipeline is idempotent and safe to run on a schedule (sources update daily). Run
`uv run run.py` from cron / GitHub Actions and commit the regenerated `web/public/data/`;
the git history of those artifacts doubles as a free time-series of the recovery.

## Coverage & honesty

- Covers the **full fire footprint**: City of LA (richest timeline), unincorporated LA
  County, and Malibu (coarser status where only that's published — labeled as such).
- A lot with no data shows **deep red, never hidden**.
- Every lot card deep-links to its official LADBS permit record so any number is auditable.
- Estimated-completion dates are model estimates, shown as ranges and labeled as such.

## License

Open source. Government data is public record; imagery/basemaps are used under their
respective attributions (shown in-app).
