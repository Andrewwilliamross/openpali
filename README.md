# OpenPali — recovery evidence workspace

By RE\SPRING. A parcel-level evidence platform for Pacific Palisades recovery.

## Run the implemented workspace

```sh
npm --prefix web ci --cache .npm-cache
make evidence-build
make evidence-api  # terminal 1: http://127.0.0.1:8000
make evidence-web  # terminal 2: http://127.0.0.1:5173
```

The Python environment is `pipeline/.venv` (Python 3.12+). Install the pipeline
with its locked requirements when creating a new environment. The release build
requires the acquired source files referenced by `Docs/Research` manifests;
it fails on missing or altered bytes. Raw acquisitions and generated releases
are excluded from Git. A generated release can be copied as a portable artifact.

The current implementation covers the ZIP 90272 parcel cohort, destroyed
Palisades Fire parcels, and exact-AIN lookups. It does **not** establish that
this is every parcel within an authoritative Palisades neighborhood boundary.
Unknown damage and unknown current vacancy remain unknown.

### Working features

- React, official coss components, and MapLibre parcel search and map.
- Immutable, hash-verified evidence releases and a release-pinned read API.
- Cleanup status and source PDF links, current permit rows, inspection requests,
  detailed sampled PCIS outcomes, assessor and recorded transfer histories.
- Sourced listing samples; asking prices, transfer-tax-derived amounts and
  assessed values remain distinct.
- Metric neighborhood destruction exposure, descriptive permit timelines,
  dated LiDAR geometry measurements, and sampled sewer engineering records.
- Persistent local project-role drafts and acquisition-task actions. Claims are
  unverified and never change agency evidence or generate contractor rankings.
- Expanded source collectors, a bounded assessor acquisition command, and a
  deterministic PCIS browser worker with retained failures.

### Start with detailed examples

- **677 Via de la Paz / 4412013017:** cleanup packet, assessor history, LiDAR, sewer.
- **758 Radcliffe / 4412006025:** pending lot listing and recorded transfers.
- **1201 Villa Woods / 4409004001:** actual PCIS inspection outcomes and clearances.

## Architecture

- `pipeline/openpali/intelligence/`: portable release builder, source integration,
  spatial features, permit/market support logic, LiDAR measurements and local drafts.
- `pipeline/openpali/discovery/`: bounded source collectors with retained raw bytes.
- `pipeline/openpali/api/`: FastAPI. `/v1/evidence/current` resolves a research
  release; all property and artifact reads pin its ID.
- `pipeline/openpali/{ingestion,storage,publication}/`: canonical PostGIS ledger,
  source-run membership, snapshots and production publication. The portable import
  command stages data here without moving the production release pointer.
- `web/`: coss / React / Tailwind 4 / MapLibre client.
- `infra/`: PostGIS, S3, orchestration and canonical service stack. The optional
  `compose.evidence.yaml` mounts portable artifacts read-only.
- `pipeline/palisades/`: legacy static producer, retained for comparison; the new
  frontend uses the evidence API.

The local draft workspace uses SQLite for **operational submissions only**;
civic facts and production publication retain PostGIS. `make evidence-api`
enables draft writes and binds loopback. Public authentication, ownership/license
verification, moderation and abuse controls must precede public claim intake.

## Grow coverage

```sh
# Up to 25 histories per batch; retains selection scope, raw bytes and failures.
PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.intelligence.acquire --limit 25 --register
# Add --queued-only to consume explicitly queued history tasks.
make evidence-build

# Refresh complete agency permit and inspection-request tables.
PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.discovery.permit_inventory

# Stage in canonical PostGIS after migrations, without publication.
make evidence-import
```

`Docs/Research/evidence-extra-inputs.json` is an explicit input recipe. Building
again from the same inputs produces the same release ID and artifact hashes.

## Verification

```sh
sh scripts/check-fast
npm --prefix web run build
```

The full service suite requires real PostGIS and S3; it is not represented by
SQLite tests. See the [implementation record](Docs/Plans/2026-09-24-IMPLEMENTATION.md)
for measured counts, checks, and outstanding work.

## Remaining research and engineering

Validated price predictions, vacancy price effects, current construction vision,
continuous listing acquisition, broader utility feeds, public identity verification,
and fair contractor rankings are **not shipped claims**. The workspace exposes
missing evidence and acquisition paths, rather than manufacturing those results.

- [Data expansion research](Docs/Research/2026-09-24-DATA-EXPANSION.md)
- [Market research](Docs/Research/2026-09-24-MARKET-SPIKE.md)
- [Visual acquisition and modeling program](Docs/Research/2026-09-24-VISUAL-PROGRAM.md)
- [Long-term recovery intelligence plan](Docs/Plans/2026-09-24-RECOVERY-INTELLIGENCE.md)
- [Frontend source and coss attribution](web/README.md)
