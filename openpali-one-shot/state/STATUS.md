# Run status

State: `ROUND_5_VERIFIED__FRESH_EVALUATOR_NEXT`

Verified checkpoints: CP0 (`edde389`), CP1 (`9c24e27`), CP2 (`0310c98`),
CP3 (`691ea8c`), CP4A+CP4B (`d85793e`..`9ca6588`), CP4C (browser 6/6),
CP5 drills. Evaluator round 1 FAIL (10 MUSTs) -> repairs `f75f956`,
`7d4c7d5`, `4d7f797`, `d726f60`. Round 4 (`97685ab`): fixture-promotion
gate, pointer isolation, header-merge regression, APN search, drill races —
browser 13/13, integration 14/14, replay OK on rel-8716f0cf (6,216 props),
api-bench green. Evaluator round 2 on `97685ab`: **FAIL — 14/19 MUSTs pass**;
failing: ENV-001/OPS-001 (F1 full gate not runnable end-to-end), ML-003 (F1
ml-drill unrerunnable once fixture release exists), MULTIMODAL-001 (F2
recon-drill not idempotent), GOV-001 (F3 README "open source" claim + stale
score/ETA prose). Defects D3 (conftest doesn't restore publication status),
D4 (raw fetch in App.tsx; 12/12-vs-11/11 report discrepancy).

REPAIR ROUND 5 (uncommitted, in verification):
- F1: reset_fixture preserves publication-pinned snapshots (deterministic
  get-or-create builders converge back); ml-drill rerun VERIFIED 12/12
  TWICE with rel-464d5ce8 published.
- F2: reset_drill_state clears only unpublished recon review-state
  (candidates first — FK to accepted observation); recon-drill VERIFIED
  12/12 TWICE.
- F1 one-command gate: infra/compose.gate.yaml chains all 9 service-half
  jobs behind service_completed_successfully; single command
  `wrapper -f infra/compose.yaml -f infra/compose.gate.yaml up -d full-gate`
  exits 0 only when the whole chain is green. check-full fallback prints it.
  CHAIN RUN IN PROGRESS (order: integration -> ml-drill -> ml-rep -> recon ->
  spatial-refresh -> replay -> e2e -> renderer-bench -> full-gate).
- F3: README rewritten — no license claim (explicitly undecided,
  sponsor-owned), prototype score/ETA prose moved to history section.
- D3: conftest restores publication-row statuses too; live superseded
  status on rel-8716f0cf healed via release-republish (status published,
  pointer intact, VERIFIED).
- D4: App.tsx release fetch through generated releaseInfoV1ReleasesReleaseIdGet.
- check-fast green x3; check-security 6/6; unit suite 161 passed.
- CHAIN GREEN: single command `wrapper -f infra/compose.yaml -f
  infra/compose.gate.yaml up -d full-gate` -> CHAIN_EXIT=0, all 9 jobs
  exited 0 (integration 14, ml-drill 12/12, ml-rep typed INSUFFICIENT,
  recon 12/12, spatial-refresh derive-v3 sv-60ba42f5, replay OK, e2e 13/13,
  renderer, terminal). Bonus defect found by the immutability guard during
  chain attempt 2: spatial version id ignored the parcel-grid input ->
  usgs-derive-v3 folds parcel-content sha into the version id.
- recon-gpu typed boundary exit 0; pointer rel-8716f0cf published +
  fixture release never current VERIFIED after the chain.
  Evidence: repair-round5-verification-2026-07-12.md.

REMAINING: commit candidate -> fresh evaluator (attestation ABSENT, required)
-> on PASS: ONE child commit with
only evaluator-latest.md + evaluator-attestation.json -> verify_completion.py
exit 0. Evaluator response format REQUIRED for hook capture: VERDICT/COMMIT
(40-hex)/CONTRACT_SHA256/CONFIDENCE headers; per-MUST lines
`- ID: PASS — reason`; exactly one each of COMPONENT MATRIX, MUST RESULTS,
HUMAN GATE, COMMANDS, FAILURES, UNTESTED RISKS headings (plugin
capture_evaluator.py enforces; FAIL is deliberately not captured).

Standing facts: current rel-8716f0cf (representative, published, 6,216
props); fixture rel-464d5ce8 (published, never current); pset-aa88d2d5 typed
INSUFFICIENT on current snapshot; security gate 6/6; restore v2 + verify
7/7; observability alert fired+resolved; 19 API paths; OpenAPI drift gate.
