# Run status

State: `CP0_BASELINE_VERIFIED`

Verified checkpoint: CP0 (environment + baseline reproduction) — evidence in
`state/evidence/env-manifest-2026-07-11.md`.

- Starting commit `aa51c93`, clean tree, branch `codex/openpali-one-shot-harness`.
- Baseline commands reproduced: pipeline 69 pass; web 24 pass; build OK;
  lint 6 errors. Docker Compose v2.40.3 via wrapper. Apple M4 Pro, no CUDA.
- uv panics under sandbox → use `pipeline/.venv/bin/python` directly;
  ensurepip when new deps are needed.

Technical criteria: all 20 MUST remain `FAIL`. APPROVAL-001 `UNRESOLVED`.

In flight:
- Research agents running: repo-audit (archaeology), source-research (official
  INSP_STATUS / PALISADES_WF_REBUILD / DINS / USGS semantics), platform-research
  (image pins, Prefect/MLflow/survival/Playwright specifics).

Immediate next action: CP1 semantic truth gate — build
`pipeline/openpali/domain/` taxonomy + repair `pipeline/palisades/sources.py`
defects (scheduled inspections, ancillary permits, cleanup fabrication,
PALISADES_WF_REBUILD) behind golden fixtures; block on source-research evidence
for official domain values before finalizing taxonomy constants.
