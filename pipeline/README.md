# OpenPali · the evidence engine

This directory contains the Python platform behind OpenPali: source
acquisition, the PostGIS evidence ledger, snapshots, release publication,
analytics, spatial assets, orchestration, and the FastAPI API.

The main package is `openpali/`, exposed through the `openpali` CLI.
Python 3.12 matches the local stack and CI.

## Set up and explore

From the repository root:

```sh
./scripts/bootstrap
pipeline/.venv/bin/openpali --help
pipeline/.venv/bin/python -m pytest pipeline/tests/test_domain_semantics.py -q
```

Bootstrap creates `pipeline/.venv`, installs `requirements-lock.txt`, and
installs this package in editable mode. It also installs the web dependencies.
The full suite without services is available through `./scripts/check-fast`.

For the database, object store, API, and workers, follow
[infra/README.md](../infra/README.md). That guide initializes the schema and
buckets and explains the `slice-dev` job that publishes a first development
release. The local database is only reachable inside the Compose network;
run database-dependent operations through the defined job services.

With the stack running, API documentation is at
[`http://127.0.0.1:58000/v1/docs`](http://127.0.0.1:58000/v1/docs).
Readiness requires initialized dependencies and a valid current release.

## Follow a record

```text
Public source
    │ acquire + hash original bytes
    ▼
Immutable object store ──► normalized records + observations
                                      │
                                      ▼
                              PostGIS evidence ledger
                                      │ cutoff + policy versions
                                      ▼
                                Civic snapshot
                                      │ publication gates
                                      ▼
                              Release manifest + API
```

Source records, observations, parcels, and properties have distinct
identities. Snapshots freeze their inputs and policy versions. Publication
checks those inputs before selecting a release; the API uses release-qualified
routes and spatial asset URLs.

## Package map

| Directory | Responsibility |
| --- | --- |
| `openpali/adapters/` | Source acquisition, response parsing, and schema checks |
| `openpali/ingestion/` | Raw acquisition, normalization, ledger loading, and snapshots |
| `openpali/domain/` | Evidence lanes, dates, conflicts, revisions, and policy |
| `openpali/identity/` | Deterministic identifiers |
| `openpali/storage/` | SQLAlchemy/PostGIS models and hash-verified S3 objects |
| `openpali/publication/` | Release manifests, gates, promotion, and rollback |
| `openpali/metrics/` | Metric definitions and computations |
| `openpali/ml/` | Point-in-time datasets, experiments, review, and batch predictions |
| `openpali/spatial/` | USGS acquisition, derivation, asset registration, and reconstruction |
| `openpali/orchestration/` | Prefect flows, deployments, and jobs |
| `openpali/api/` | FastAPI routes, schemas, errors, and health checks |
| `migrations/` | Alembic database migrations |
| `tests/` | Unit, semantic, contract, spatial, and opt-in integration checks |

Configuration comes from environment variables, including
`OPENPALI_DATABASE_URL`, `OPENPALI_S3_ENDPOINT`, `OPENPALI_S3_ACCESS_KEY`,
`OPENPALI_S3_SECRET_KEY`, `PREFECT_API_URL`, and `MLFLOW_TRACKING_URI`.
The Compose configuration supplies local fixture values. See
[SECURITY.md](../SECURITY.md) before deploying elsewhere.

## Operator commands

Use `openpali <command> --help` for arguments. These commands are implemented
in [`openpali/cli.py`](openpali/cli.py):

| Task | Command family |
| --- | --- |
| Acquire and load evidence | `source-refresh`, `refresh-all` |
| Build and publish | `snapshot-build`, `release-publish`, `dev-slice` |
| Recover and verify | `release-rollback`, `replay`, `restore-verify` |
| Schedule work | `orchestrate-deploy`, `orchestrate-run` |
| Evaluate and serve models | `ml-dataset`, `ml-experiments`, `ml-promote`, `ml-serve` |
| Prepare spatial assets | `spatial-acquire`, `spatial-derive` |
| Export the API schema | `export-openapi` |

Most commands require initialized services and may acquire public-source
data or create releases. Use the existing Compose jobs for the local stack.
Model promotion and release publication have their own checks; successful
acquisition alone does not make data ready to publish.

## Static bundle and earlier spatial code

There are also two retained paths in this directory:

- `run.py` and `palisades/` build the static fallback under
  `web/public/data/`. They now emit evidence lanes with provenance and
  validation checks. `run.py --offline` needs previously cached source
  responses; a fresh checkout does not contain that cache.
- `run_spatial.py` and `core/spatial/` contain the earlier GeoParquet,
  LARIAC, and splat tooling, including geometry helpers. Keep rights and
  asset-selection requirements in mind before generating distributable data.

The old `palisades/score.py` remains as deprecated, characterization-tested
reference code. Its scores and heuristic completion dates are not emitted
by `run.py` and must not be reintroduced into public recovery claims.

The root `Makefile` still includes these static and spatial entrypoints.
Use the `openpali` package and Compose workflow for platform work.
[`Docs/initialbuild_docs/`](../Docs/initialbuild_docs/) is historical context,
not the current platform specification.

## Validation

Run a focused test file while developing, then the shared fast gate from
the repository root. Integration tests in `tests/integration/` are enabled
by `OPENPALI_INTEGRATION=1` in the `test-integration` Compose job.
`./scripts/check-full` adds the service-backed checks, ML and spatial drills,
replay, browser checks, and other extended validation.

When changing API schemas, update `contracts/openapi.json` and regenerate
the web client; see [the API contract workflow](../web/README.md#api-contract).
For contribution expectations and source-data care, see
[CONTRIBUTING.md](../CONTRIBUTING.md).
