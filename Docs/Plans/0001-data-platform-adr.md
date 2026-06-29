# ADR 0001 — OpenPali Data-Platform Architecture

- **Status:** Accepted — orchestrator = **Dagster** (Phase 0 spike complete, see §Decision 3)
- **Date:** 2026-06-29
- **Context doc:** `Docs/Research/SYNTHETIC_SPATIAL_DATA_MEMO.md` (the OpenPali data-strategy memo)
- **Execution plan:** `/Users/andrewross/.claude/plans/vectorized-baking-flamingo.md`
- **Supersedes:** the implicit "three manual scripts + `make`" architecture

---

## Context

The repository began as the **Palisades Rebuild Tracker** and is the seed of **OpenPali** — the platform intended
to be the single most robust data source for the Pacific Palisades. A deep review of the codebase reached a
specific, non-obvious conclusion that frames every decision below:

> **The transform logic is genuinely strong. The engineering *system* around it is absent.**
> "The pipelines are poor" is really "the pipelines have no orchestration, no durable observability, no real
> store, and no enforced contracts." The algorithms are not the problem and must not be rewritten.

What is already good (and load-bearing — **preserve, do not rewrite**):
- A normalized domain model — `palisades/model.py` (`Parcel` / `Event` / `Permit`, stage bands, milestone classifier).
- A cached, retrying HTTP layer with content-hashed disk cache + offline mode — `palisades/http.py`.
- **Self-validation against an authoritative oracle** — `palisades/validate.py` re-queries LADBS server-side
  group-bys and flags >5% drift. This is a crown jewel that currently prints to stdout and disappears.
- A sophisticated spatial core — `core/spatial/` (I3S mesh → surfel/Gaussian → ICP registration → octree-LOD
  3D-Tiles), persisted to an **H3-partitioned GeoParquet store** by an **idempotent, fail-safe nightly runner**
  whose asset index carries a `live` / `stale_cached` / `static_baseline` status lifecycle.

What is missing (the actual problem):
1. **No orchestration.** "Nightly" is aspirational — only `Makefile: refresh: data build` and a code comment exist;
   runs are manual; there is no CI (`.github/` is absent).
2. **Files + git are the database.** The repo is **4.6 GB**; **318 MB / 2,378 splat-tile files are committed to
   git** (`web/public/tiles/`), plus 4.7 MB GeoJSON + 4.2 MB details regenerated every run. The "time-series" is
   `git checkout`.
3. **Observability is `print()`.** The oracle reconciliation and the spatial `NightlyReport.anomalies` — the two
   most valuable signals in the system — evaporate to a terminal.
4. **Three manual scripts, not a pipeline.** `run.py`, `run_spatial.py`, and `python -m core.spatial.web_export`
   share APN keys but nothing coordinates them; `web_export` is not even in `refresh`.
5. **The pipeline↔web contract is unenforced.** `emit.py`'s dicts and `web/src/lib/types.ts` must agree, with
   nothing validating it; a field rename silently breaks the site.

OpenPali's roadmap (per the research memo) — ingest dozens of government sources, add physical capture, and run
CV models that *generate* new spatial layers — cannot be served by "one box runs three scripts against a disk
cache." This ADR defines the substrate that can.

---

## Decision summary

We adopt a **five-layer reference architecture** and commit to a **backendless** realization of it (no always-on
database or API) until a concrete paying use-case requires otherwise. The prime directive across all work is
**wrap, don't rewrite**.

### The five layers

| Layer | Today | Target (backendless) |
|---|---|---|
| **1. Ingestion** | `http.py` content-hashed cache | same pattern, promoted to a raw landing zone in object storage |
| **2. Storage / system-of-record** | files + git + local GeoParquet | object-store **lakehouse**: GeoParquet + **STAC** catalog; **DuckDB** as the serverless query engine; date-partitioned score time-series. *No DB.* |
| **3. Orchestration** | none (manual `make`) | **Dagster or Prefect** (Phase 0 spike decides) |
| **4. Quality / observability** | `print()` + oracle to stdout | durable run records + oracle-reconciliation history + drift/anomaly **alerting** |
| **5. Serving** | static files in the web build, **tiles in git** | static artifacts + **PMTiles** (2D vector) + **object storage + CDN** (3D splat pyramid), web app reads via env-configured base URLs |

The point: an orchestrator (Layer 3) alone changes nothing about Layers 2, 4, and 5. The decision is the **whole
column**, sequenced so the lowest-risk, highest-leverage slice ships first.

---

## The six decisions

### Decision 1 — Wrap, don't rewrite (prime directive)
Every migration step wraps existing functions (`build_parcels`, `score_all`, `emit_all`, `run_nightly`,
`export_web_tiles`) rather than reimplementing them. Enforcement: a **byte-diff regression guard** — the emitted
`parcels.geojson` / `details.json` / `summary.json` must be identical before and after the migration.
**Rationale:** the most common way an infra migration fails is rewriting good business logic under cover of the
migration. We refuse to.

### Decision 2 — Backendless lakehouse, not a database
System-of-record becomes an **object-store lakehouse** (GeoParquet curated tables + a **STAC** catalog over
spatial/raster assets), queried serverlessly with **DuckDB**. We keep the no-DB, forkable civic ethos: cheap,
durable, and a `git clone` (or bucket sync) reproduces the whole dataset.
**Rationale:** the current design's instinct (static, forkable, no server to operate) is correct for a civic
project; it just needs to graduate from "files in git" to "cloud-native files in object storage." Aligns with the
research memo's verified cloud-native-format finding (COG / COPC / GeoParquet / PMTiles / STAC).
**Explicitly deferred:** PostGIS + a serving API (see Non-goals).

### Decision 3 — One orchestrator, chosen by spike *(PENDING)*
We will model the real DAG (`build_parcels → score_all → emit_all → run_nightly → export_web_tiles`, with the
oracle reconciliation as a data-quality check) in **both Dagster and Prefect** as throwaway code (Phase 0), then
commit.
**The hypothesis to test:** the spatial core already models the world as **versioned assets with a status
lifecycle** — that is Dagster's software-defined-asset model almost 1:1, and would yield lineage, a data catalog,
and asset-checks (our `validate.py` oracle) for free. Prefect is lighter and excels at the dynamic per-parcel
fan-out the nightly runner already does.
**Spike result (Phase 0, 2026-06-29).** Both spikes wrap the identical DAG over the existing functions and run
end-to-end offline (`pipeline/orchestration/{dagster_spike,prefect_spike}.py`). Both surfaced the *same real
finding*: the LADBS oracle reconciliation drifts >5% on `parcels_complete_cofo` — Prefect logged it as a warning;
Dagster recorded it as a failing **asset check** in the catalog.

| Criterion | Dagster 1.13 | Prefect 3.7 |
|---|---|---|
| Maps to existing `assets.parquet` model | **1:1** — assets *are* the model | Tasks/flows; asset model is yours to build |
| Lineage + catalog out-of-box | **Yes** (recorded automatically) | No (ephemeral; build your own) |
| Oracle → first-class data-quality check (Decision 4) | **Yes** — `@asset_check`, queryable, severity levels | Ad-hoc `if drift: log.warning` |
| Selective / on-demand materialization (heavy spatial assets) | **Yes** — just don't select them | Manual flags (`--spatial`) |
| Retries | Per-asset config | **Trivial** — `@task(retries=2)` |
| Imperative simplicity / ran as plain script | Subprocess-per-step; fussier CLI selection | **Yes** — `python prefect_spike.py` |
| Ephemeral-run noise | Clean | `EventsWorker failed` spam without a server |

**Recommendation: Dagster.** The decisive factor is Decision 4 + the existing asset shape — Dagster gives lineage,
a catalog, and the oracle-as-asset-check (the core of "most robust data source") *for free*, exactly matching the
`live`/`stale_cached`/`static_baseline` model the spatial core already uses. Prefect is the lighter tool and wins
on imperative simplicity, but you would hand-build the observability that Dagster ships.
**Decision:** **Dagster** (confirmed 2026-06-29).

### Decision 4 — Promote the oracle to a durable data-quality gate
`validate.py`'s reconciliation and the spatial `anomalies` list stop being `print()` and become first-class:
each run's `reconcile()` output and `NightlyReport.to_json()` are appended to a date-partitioned `data/runs/`
Parquet table (DuckDB-queryable), and >5% drift / spatial anomalies fire an **alert**.
**Rationale:** "robust data source" is a promise about *knowing when we are wrong*. The capability already exists;
it is merely invisible.

### Decision 5 — PMTiles + object-store/CDN serving; tiles leave git
- The **3D-Tiles splat pyramid** (318 MB / 2,378 files) moves to **object storage + CDN** (recommend **Cloudflare
  R2** for zero egress fees) and is removed from git tracking.
- The 2D **`parcels.geojson`** (4.7 MB, loaded whole) becomes a **PMTiles** vector archive served as map tiles.
- The web app reads tiles and data via env-configured base URLs (`VITE_TILES_BASE` / `VITE_DATA_BASE`).
**Rationale:** serving must be decoupled from the source repo before OpenPali can offer companies real endpoints,
and a 4.6 GB repo is already an operational liability.
**Note:** PMTiles covers 2D vector/raster only; the splat pyramid is a different format and is decoupled via
object storage, *not* PMTiles.

### Decision 6 — Heavy / GPU compute dispatched off the scheduler
As the roadmap adds physical capture and CV models that generate layers (per the memo), those jobs run on
**separate compute** dispatched by the orchestrator — never inline on the scheduler box. Designed for now,
built later.
**Rationale:** ICP, octree tiling, and future CV/3D-reconstruction (e.g. the lingbot-style pipeline) are
GPU/CPU-heavy and must not block or co-locate with orchestration.

---

## Non-goals (for now)

- **No PostGIS / relational system-of-record.** Revisit only when a concrete B2B use-case needs server-side
  spatial queries.
- **No always-on serving API.** Static artifacts + CDN until a customer needs live endpoints.
- **No rewrite of transform logic.** See Decision 1.
- **No new data sources in this phase.** The memo's DINS / LADBS / 3DEP / FEMA sources are Phase 4 — added as
  new assets once the substrate exists.

---

## Consequences

**Positive:** the same proven logic gains retries, lineage, a UI, durable + alertable quality signals, and a
clean serving boundary; the repo sheds hundreds of MB; adding a future source becomes "add an asset," not "add a
script."

**Costs / risks:**
- A one-time **git history rewrite** (`git-filter-repo` + force-push) is needed to actually reclaim the 4.6 GB —
  a coordinated, all-hands, SHA-rewriting step, never bundled into a routine PR.
- The team takes on an orchestrator dependency (operational surface), justified by everything it replaces.
- DuckDB-over-Parquet is excellent for analytics/serving reads but is not a transactional store — acceptable
  given the backendless decision.

---

## Roadmap (documented here, built later)

- **Phase 0 — Orchestrator spike** (decides Decision 3).
- **Phase 1 — Foundation:** orchestrate (promote spike winner + CI) · observe (durable quality records + alerts) ·
  serve (tiles → CDN, PMTiles). *This is the concretely-detailed, executable phase.*
- **Phase 2 — One generated contract:** Pydantic as the single source of truth → generate JSON Schema +
  `web/src/lib/types.ts`; validate `emit.py` output in CI.
- **Phase 3 — Formalize the lakehouse:** raw landing zone + curated GeoParquet + STAC catalog + DuckDB query
  layer + date-partitioned score time-series (retires "git-as-time-series").
- **Phase 4 — New sources & generated layers:** ingest the memo's sources and CV-generated layers as new assets;
  implement the Decision-6 GPU dispatch boundary.
