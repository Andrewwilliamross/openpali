# Run status

State: `CP1_TRUTH_GATE_COMPLETE`

Verified checkpoints:
- CP0 environment/baseline (`edde389`), evidence `state/evidence/env-manifest-2026-07-11.md`.
- CP1 semantic truth gate — this commit.

CP1 outcomes (all executed, evidence in `state/evidence/`):
- New production domain layer `pipeline/openpali/{domain,ingestion}`: evidence-
  backed taxonomy (fail-closed on undocumented values), occurred/observed split
  with interval censoring, parallel-lane projection (`lanes-v1`), qualifying
  policy `Bldg-New ∧ PALISADES_WF_REBUILD='Rebuild'` (`qualifying-rebuild-v1`),
  conflict detection, retractions.
- Live domain probes 2026-07-11 (`domain-probe-2026-07-11.json` + supplement):
  INSP_STATUS is 100% 'Insp Scheduled' (1,014 rows, both endpoints); WF_REBUILD
  ∈ {Rebuild,No}; full PERMIT_TYPE/STATUS/ROE/REBUILD_PROGRESS/Malibu domains.
- Golden corpus (15 cases: positive/negative/scheduled/ancillary/opt-out/
  missing-date/future/non-rebuild/flag-missing/undocumented/conflicting/
  corrected/multi-structure/cross-jurisdiction/ambiguous) + independent
  differential implementation; 120 pipeline tests pass.
- Legacy pipeline rewired through the new layer; score/stage/ETA removed from
  all artifacts and map styling (score.py retained deprecated, uncalled).
- Live corrected run (`truth-gate-live-run-2026-07-11.log`): 5,877 destroyed;
  qualifying applications 1,126; reconciliation drift ≤0.7% (CofO 27 vs 27 =
  0.0%, was 23.8% FAIL); invalid 489 under-construction → 1 evidenced + 436
  scheduled-only; 1,595 opt-outs no longer fabricated as fire-date cleanups.
- Web migrated to lane/milestone artifacts; categorical evidence legend; splat
  score-tint neutralized in shader; lint 0 errors (baseline: 6), 24 tests, build OK.

Technical criteria: TRUTH-001 substantially implemented (pending methods review
+ evaluator). Remaining 19 MUST items FAIL. APPROVAL-001 UNRESOLVED.

Research inputs received: source-research (DINS endpoint verified: services1
POSTFIRE_MASTER_DATA_SHARE, 12,137 Palisades records; USGS prd-tnm staged
tiles; county metric-definitions PDF; Socrata CC0), platform-research (pins:
baosystems/postgis:17-3.5 arm64, SeaweedFS 4.39, Prefect 3.7.8 process worker,
MLflow 3.14 aliases, lifelines/rasterio/laspy arm64 OK, no PDAL, Playwright
1.61 + --enable-unsafe-swiftshader, @hey-api/openapi-ts), repo-audit (409 MB
tracked splat tiles need object policy; registration.py dead; renderer lacks
workers/BVH picking — CP4B targets).

Immediate next action: CP2 platform spine — infra/compose.yaml via docker_safe
wrapper (postgres/PostGIS + SeaweedFS + Prefect + MLflow + api), Alembic
canonical schema, object store client, County source end-to-end to FastAPI +
browser. Methods review of CP1 semantics runs in parallel.
