# Repair round 5 — evaluator round-2 findings and re-verification (2026-07-12)

Evaluator round 2 (on candidate 97685ab): FAIL — 14/19 MUSTs verified by the
evaluator's own execution; failing MUSTs ENV-001, ML-003, MULTIMODAL-001,
OPS-001, GOV-001 via findings F1–F3 (+ defects D3, D4). This round repairs
each finding and re-verifies at the new candidate.

## F1 — ml-drill structurally non-rerunnable once the fixture release exists

`reset_fixture` deleted ALL fixture snapshots; the published fixture release
rel-464d5ce8 pins snap-09bea1f1 and the database FK correctly refused.
Repair (`pipeline/openpali/ml/fixture.py`): the reset now preserves
publication-pinned snapshots and — when any pin exists — the civic fixture
base rows their membership references; only unpinned drill state is deleted.
The fixture builders are deterministic get-or-create everywhere (run ids,
records with on_conflict_do_nothing, identities, snapshots, datasets,
prediction sets), so the rebuild converges onto the identical pinned content.
VERIFIED: `up -d ml-drill` → **12/12 checks passed, TWICE back-to-back**, with
rel-464d5ce8 published throughout.

## F2 — recon-drill not idempotent

Prior-run candidates (retracted/rejected) and drill observations collided
with the rerun. Repair (`pipeline/openpali/spatial/reconstruction.py`):
`reset_drill_state` deletes only the drill's own unpublished review-state —
candidates first (FK to the accepted observation), then
fixture_reconstruction observations/revisions. These rows belong to no
snapshot membership or publication; the fused fixture ASSET rows/objects are
content-addressed and survive (the fixture release manifest pins them).
VERIFIED: `up -d recon-drill` → **12/12 checks passed, TWICE back-to-back**.

## F1 (gate) — the full gate as ONE command

`infra/compose.gate.yaml` chains all nine service-half jobs behind
`service_completed_successfully` conditions (order: test-integration →
ml-drill → ml-representative → recon-drill → spatial-refresh → replay →
e2e-browser → renderer-bench → full-gate terminal). The single command

    python3 openpali-one-shot/scripts/docker_safe.py \
      -f infra/compose.yaml -f infra/compose.gate.yaml up -d full-gate

blocks while each job runs, aborts on the first nonzero exit (observed live:
the first chain attempt failed fast on a conftest bug — the chain is
fail-closed, not decorative), and exits 0 only when the whole chain is
green. `scripts/check-full` prints exactly this command in its sandbox
fallback; on Docker-reachable hosts check-full runs the same jobs itself.
Chain result at the candidate: recorded below.

## F3 — README license claim + stale prototype prose

Root README.md rewritten: describes the actual platform (evidence lanes, no
scores, typed insufficiency), moves the retired 0–100-score/static-JSON
prototype to a History section, and states licensing is an undecided,
sponsor-owned decision — no license is granted (GOV-001 fail_if resolved;
FINAL_REPORT human-gate item updated to match).

## D3 — publication-status isolation and live heal

`tests/integration/conftest.py` now snapshots ops.publication statuses at
suite start and restores changed pre-existing rows at teardown (suite-created
rows stay, append-only). The live rel-8716f0cf row (flipped to "superseded"
by pre-fix suite runs) was healed through the production path:
`up -d release-republish` → publish_release existing-release promote branch
→ status "published", pointer unchanged. VERIFIED via /v1/releases.
A first chain attempt exposed a conftest bug (Result not dict-able — the
env-gated fixture body never runs in host unit tests); fixed with .all().

## D4 — generated-client boundary + report discrepancy

`web/src/App.tsx` release-info fetch now goes through the generated
`releaseInfoV1ReleasesReleaseIdGet`. The 12/12-vs-11/11 drill discrepancy is
a drill-version difference (the promotion-refusal control was added in the
repair rounds); dated addendum recorded in cp4a-ml-drill-2026-07-12.md.

## Gates at the round-5 candidate

- `scripts/check-fast`: green ×3 on the round-5 tree (pipeline tests, web
  tests/lint/typecheck, openapi-drift; latest 20260713T005706Z); host unit
  suite 161 passed after every product change.
- `scripts/check-security`: green (20260712T222023Z) — pip-audit,
  CycloneDX SBOMs (python+web), npm audit, checksum-pinned gitleaks over
  full history, planted-secret negative control.
- **Full-gate chain (single command): CHAIN_EXIT=0.**
  `docker_safe.py -f infra/compose.yaml -f infra/compose.gate.yaml up -d
  full-gate` ran test-integration (14 passed) → ml-drill (12/12) →
  ml-representative (typed INSUFFICIENT pset) → recon-drill (12/12) →
  spatial-refresh → replay (REPLAY OK) → e2e-browser (13/13) →
  renderer-bench → full-gate terminal ("FULL GATE CHAIN COMPLETE: all
  service-half jobs exited 0"); every container exit code 0. Two failed
  attempts preceded it, each caught fail-closed by the chain itself:
  (1) a conftest bug (SQLAlchemy Result not dict-able — the env-gated
  fixture body never runs in host unit tests); (2) a REAL versioning defect
  the immutability guard exposed — spatial derive's version id hashed only
  raw DEM bytes + params while the output also depends on the parcel grid,
  so a changed county base (6,216 parcels now) collided with immutable old
  bytes. Fixed as `usgs-derive-v3`: the parcel-content sha (apn, damage
  class, geometry hash per row) joins the version id; the chain run minted
  sv-60ba42f5 as a NEW version while the pinned release keeps serving its
  old version through release-qualified URLs.
- recon-gpu typed boundary (own command, `--profile gpu`): exit 0 with
  typed unsupported-hardware result (no nvidia devices; CPU fixture path
  remains the executable proof).
- Post-chain live state verified: current pointer rel-8716f0cf
  (representative, **published**, 6,216 properties) — the conftest
  isolation fix held through a full suite run inside the chain; fixture
  release rel-464d5ce8 still published and never current.
