# OpenPali data pipelines

The repository contains an active static producer, a canonical ledger/API
pipeline, and a historical spatial producer. They are not interchangeable.
See the [September 2026 audit](../Docs/Research/2026-09-24-CTO-AUDIT.md) and
[source inventory](../Docs/Research/2026-09-24-SOURCE-INVENTORY.md) for measured
coverage and remaining consistency problems.

| Path | Produces | Entrypoint |
|---|---|---|
| `palisades/` using shared `openpali.domain` and normalization | Static parcel geometry, milestone flags, evidence timelines, summary and manifest | `run.py` |
| `openpali/` | Immutable acquisitions, PostGIS ledger, snapshots, metrics, experimental models, publication/API and selected spatial assets | `openpali` CLI and Prefect flows |
| `core/spatial/` | LARIAC-derived priors, synthetic fallbacks, GeoParquet store and historical splat atlas | `run_spatial.py`, `core.spatial.web_export` |

The 0–100 function in `palisades/score.py` is historical and is not called by
`run.py`. Milestones depend on specific evidence and permit qualification,
including `Bldg-New` AND the rebuild flag for city replacement-building
milestones. Scheduled inspections do not establish completed inspections.

## Setup and checks

From the repository root:

```sh
scripts/bootstrap
scripts/check-fast
scripts/check-full
```

`check-full` requires the local service stack and exercises integration gates.
The Python package requires Python 3.12 or later; the September audit used
3.12 and `requirements-lock.txt`. See `infra/compose.yaml` for PostGIS,
object storage, orchestration, API and model tracking services.

## Static producer

From `pipeline/`:

```sh
uv run run.py                 # acquire civic sources, derive evidence, check, emit
uv run run.py --offline       # reuse cached responses
uv run run.py --no-validate   # omit oracle reconciliation queries
```

These commands write the public static artifacts after the applicable gates.
They are not read-only audits. Raw caches live under `data/raw/` and are
ignored by git. `Makefile` targets `data` and `data-offline` wrap these paths.

The County destroyed-Palisades debris layer defines the static parcel universe.
LADBS permits and the static inspection endpoint add city events; County and
Malibu supply coarser assertions. Reconciliation is against explicitly filtered
agency data, with denominators that must match the metric. Mirrored agency
records are not independent evidence of physical construction.

| Module | Role |
|---|---|
| `palisades/sources.py` | Fetch and join sources; call shared normalization/projection |
| `palisades/model.py` | Static parcel and permit representations |
| `palisades/emit.py` | Write geometry, detail, summary and metadata artifacts |
| `palisades/checks.py` | Static expectation gates |
| `palisades/validate.py` | Agency reconciliation |
| `palisades/neighborhoods.py` | Nearest-center grouping, not validated neighborhood polygons |
| `openpali/domain/` | Typed times, taxonomy, evidence, conflicts and lane projections |

## Canonical pipeline

The `openpali` executable is declared in `pyproject.toml`. Inspect its available
commands with `uv run openpali --help`. Implementation areas:

```text
openpali/adapters/       civic source contracts and fetchers
openpali/ingestion/      acquisitions, normalization, ledger loading, snapshots
openpali/storage/        PostGIS models and content-addressed object storage
openpali/metrics/        metric definitions and computation
openpali/ml/             datasets, experiments, registry and serving
openpali/publication/    release manifests, gates and rollback
openpali/api/            release-qualified JSON and vector tiles
openpali/orchestration/  Prefect flows and deployment registration
openpali/spatial/        USGS assets, derivation and reconstruction experiments
```

The audit identifies unresolved snapshot membership, assertion supersession,
frontend mixing and model evaluation defects. Registering Prefect deployments
does not itself configure a refresh schedule. Do not infer deployed freshness
or valid forecasting performance from the presence of these modules.

## Spatial producer

`run_spatial.py` and `core.spatial.web_export` operate the older LARIAC prior
and atlas path. The committed atlas contains pre-fire models and synthetic
fallback geometries, with score-era color metadata. It is not a current
construction survey. The canonical USGS asset is January 2025 bare-earth
elevation. See the source inventory before presenting either as recovery
progress or using processing dates as image capture dates.

## Read-only audit tools

The [data expansion report](../Docs/Research/2026-09-24-DATA-EXPANSION.md)
documents the new `openpali.discovery` collectors for public assessor histories,
all property types in ZIP 90272, and clearance-document inventories. They stage
timestamped source evidence under ignored `data/raw/` and do not write the
application database. Use `PYTHONPATH=pipeline` when invoking these modules from
the repository root without an editable installation. The PCIS DOM adapter is
in `scripts/pcis-extract.mjs`; worker scheduling is not yet implemented.

From the repository root with the pipeline environment installed:

```sh
pipeline/.venv/bin/python scripts/audit_data.py --output /tmp/openpali-bundle-audit.json
pipeline/.venv/bin/python scripts/probe_sources.py --output /tmp/openpali-source-probes.json
```

The first profiles local artifacts; the second contacts public services for
metadata/counts without ingesting or publishing records. Historical prototype
architecture and scoring documents remain in `Docs/initialbuild_docs/`.
