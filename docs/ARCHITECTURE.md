# Architecture — Palisades Rebuild Tracker

## Design philosophy

**Static-first.** Government data systems are slow-moving (daily updates at best) and
this is a civic project that must stay cheap, durable, and forkable. So:

```
┌─────────────────────────────────────────────────────────────────┐
│  PIPELINE (Python, runs on a schedule — local cron / GH Actions) │
│                                                                  │
│  fetch/     pull raw data from public APIs (cached to data/raw)  │
│  normalize/ clean + key everything on APN                        │
│  join/      DINS damage ⟕ parcels ⟕ permits ⟕ inspections ⟕ CofO │
│  score/     rebuild score 0–100 + predicted completion           │
│  emit/      static artifacts → web/public/data/                  │
└────────────────────────────┬─────────────────────────────────────┘
                             │  parcels.geojson   (one feature per destroyed lot)
                             │  summary.json      (headline metrics + sparkline series)
                             │  meta.json         (as-of timestamps, source health)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  WEB (Vite + React + TS + MapLibre GL — fully static site)       │
│                                                                  │
│  Map view: parcel polygons, fill color = score gradient          │
│  Detail card: permit history, inspections, pre-fire imagery,     │
│               predicted completion, deep link to LADBS record    │
│  Header: headline metrics + permit-velocity sparkline            │
└──────────────────────────────────────────────────────────────────┘
```

No backend server. No database. The "database" is versioned JSON artifacts; git history
of the artifacts doubles as a free time-series of the recovery (each pipeline run is a
snapshot we can diff later).

## Why these technologies

- **Python + uv** for the pipeline: pandas for the joins/cohort statistics, shapely for
  the spatial work, httpx with retry/caching for polite API consumption.
- **MapLibre GL JS**: open-source WebGL maps, no API key, vector rendering handles ~6k
  polygons effortlessly with data-driven styling (score → color is a paint expression).
- **GeoJSON over vector tiles**: ~6k parcel polygons gzip to a few MB — fine as a single
  fetch. PMTiles is the escape hatch if we ever cover larger fire footprints.
- **Static hosting** (GitHub Pages / Cloudflare Pages): free, fast, zero ops.

## Data flow & join strategy

Everything joins on **APN** (LA County Assessor Parcel Number), with normalized-address
and lat/lon point-in-parcel as fallbacks:

1. **Universe of lots** = DINS records with damage in {Destroyed} (optionally Major),
   deduped to parcels via APN. DINS is the authoritative "what was lost" source.
2. **Geometry** from county/city parcel services, fetched once per APN and cached
   (parcel lines don't change; only re-fetch on cache miss).
3. **Status events** per parcel, merged into a single event timeline:
   - debris cleared (USACE/archival)
   - permit application submitted / plan check (LADBS, EPIC-LA)
   - permit issued
   - inspections (foundation → framing → MEP → drywall → finals)
   - certificate of occupancy
4. **Score** computed from the event timeline (see METHODOLOGY.md).

## Freshness

Each source records an `as_of` timestamp into `meta.json`; the UI shows data age
honestly. Pipeline is idempotent and safe to run hourly; sources mostly change daily.
A `make refresh` target runs the whole thing; CI cron does the same on a schedule.

## Repo layout

```
pipeline/   Python ETL (uv project)
web/        Vite + React + MapLibre frontend
data/raw/   cached upstream responses (gitignored)
data/out/   pipeline outputs before publish (debug)
docs/       this file, METHODOLOGY.md, DATA_SOURCES.md
```
