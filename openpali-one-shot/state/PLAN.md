# Mutable execution plan

Full plan detail: `~/.claude/plans/joyful-forging-micali.md` (approved). This
file tracks the live critical path only.

| # | Checkpoint | Acceptance IDs | State |
|---|---|---|---|
| CP0 | Baseline + env manifest | ENV-001 (partial: manifest, probes) | DONE 2026-07-11 |
| CP1 | Semantic truth gate | TRUTH-001 | NEXT |
| CP2 | Platform spine: Compose/PostGIS/SeaweedFS/migrations/object store/first API slice | DATA-002, BACKEND-001 (start) | pending |
| CP3 | Multi-source orchestration, metrics, atomic publication, representative release + replay | DATA-001, PUB-001, ANALYTICS-001 | pending |
| CP4A | Continual ML | ML-001, ML-002, ML-003 | pending |
| CP4B | Spatial/3D/multimodal | SPATIAL-001, SPATIAL-002, MULTIMODAL-001 | pending |
| CP4C | Product journeys | FRONTEND-001, FRONTEND-002 | pending |
| CP5 | Integration, CI/ops/security, releases | E2E-001, OPS-001, OPS-002, GOV-001 | pending |
| CP6 | Final report + evaluator + evidence commit | RELEASE-001 | pending |

Key structural decisions (blueprint defaults, no deviation ADR needed):
- `pipeline/openpali/` modular monolith: domain, adapters, storage, identity,
  ingestion, metrics, ml, spatial, publication, api, orchestration,
  observability. Alembic under `pipeline/migrations/`.
- `infra/compose.yaml` services: postgres(PostGIS), object-store(SeaweedFS S3),
  prefect-server, prefect-worker, mlflow, api, web (+observability profile).
- Stack: SQLAlchemy2+GeoAlchemy2+psycopg3, FastAPI+Pydantic v2, boto3,
  lifelines, Prefect 3, MLflow, openapi→TS types, Playwright+axe.
- Scripts: `scripts/bootstrap`, `scripts/check-fast`, `scripts/check-full`,
  release/rollback/restore commands via `openpali` CLI in pipeline project.

Risks being tracked:
- uv unusable under sandbox → venv ensurepip + pip route; keep uv.lock coherent.
- SeaweedFS S3 subset (multipart/conditional writes) must be tested for the
  exact operations used; immutability enforced by our hashes/manifests.
- Playwright headless WebGL on macOS arm64: record hardware vs software; GPU
  perf claims need headed runs.
- DINS endpoint/filter must be verified live before implementation
  (source-research in flight).
