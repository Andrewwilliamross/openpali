# Run status

State: `REPAIR_ROUND_4_VERIFY__THEN_CP6_TERMINAL_PROTOCOL`

Verified checkpoints: CP0 (`edde389`), CP1 (`9c24e27`), CP2 (`0310c98`),
CP3 (`691ea8c`), CP4A+CP4B (`d85793e`..`9ca6588`), CP4C (browser gate 6/6),
CP5 drills (cp5-ops-drills-2026-07-12.md). Evaluator round 1: FAIL (10
MUSTs) -> repair rounds 1-3 committed (`f75f956`, `7d4c7d5`, `4d7f797`) +
FINAL_REPORT update (`d726f60`, now at openpali-one-shot/state/FINAL_REPORT.md).

REPAIR ROUND 4 (in progress, uncommitted): battery on the repaired build
found real defects, all fixed:
- REGRESSION: release-pinned header summary in App.tsx dropped `weekly`
  -> Header sparkline threw -> React unmounted -> `__mapReady` never fired
  -> 8/13 browser specs dead. Fixed with explicit static-base +
  release-overlay merge (also removes a static-vs-release fetch race).
- ISOLATION DEFECT (root cause of a corrupted pointer): publish_release
  defaults kind="fixture", promote=True; test_platform_integration's
  publication test called it bare -> PROMOTED a fixture release
  (rel-c1534264, 334 props) over rel-3b1f5b45; publication_faults' restore
  fixture then preserved the corruption. Fixes: (1) PRODUCTION GATE:
  publish_release now refuses promote of kind="fixture" (PublicationGateError,
  negative control in test_platform_integration); (2) suite-wide
  session-scoped pointer restore in tests/integration/conftest.py;
  (3) release-republish + ml-representative jobs fail closed unless the
  current release kind is representative; (4) CLI release-publish grew
  --no-promote. NOTE: never run test-integration concurrently with
  e2e-browser/api-bench (pointer flaps mid-suite by design of the drills).
- restore-drill race: verify compared restored counts against the MOVING
  live DB; now compares against references captured at dump time. PASS.
- journeys spec bugs: fetch before goto (URL parse); header asserts
  permit_issued raw count but Header renders it as a rate -> assert
  properties count + derived rate on .metric-num nodes.
- model-status: no prediction set existed for the (then-corrupted) current
  snapshot; StatusPage text was the honest fallback. ml-representative
  requires representative pointer now; re-run after heal.

ROUND-4 VERIFY SEQUENCE (after api/web/worker redeploy on rebuilt images):
1. full-release -> fresh representative release heals the pointer (RUNNING)
2. ml-representative -> typed INSUFFICIENT pset for the new snapshot
3. test-integration (new gate control; pointer unchanged after)
4. e2e-browser 13 specs; 5. renderer-bench; 6. api-bench already 0;
restore-drill already PASS on fixed compose. Then replay + check-fast,
commit candidate, CP6 protocol per openpali-one-shot/state/README.md
(evaluator-attestation.json must be ABSENT before launch — it is).

CP6 terminal protocol (openpali-one-shot/state/README.md governs):
candidate commit w/ FINAL_REPORT -> fresh openpali-independent-evaluator on
clean tree (hook captures) -> if PASS exactly ONE child commit touching only
state/evaluator-latest.md + state/evaluator-attestation.json ->
`python3 openpali-one-shot/scripts/verify_completion.py` exits 0.

Standing facts: fixture release rel-464d5ce8 (published, never current);
replay REPLAY OK (zero network, exact hashes); ml-drill 12/12; recon-drill
12/12; GPU probe typed unsupported_hardware; security gate 6/6; observability
alert fired+resolved; restore v2 3-DB drill + restore-verify; 19 API paths;
OpenAPI drift gate in check-fast.
