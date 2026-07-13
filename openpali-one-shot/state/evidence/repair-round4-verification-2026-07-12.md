# Repair round 4 — battery findings and re-verification (2026-07-12)

All commands via `python3 openpali-one-shot/scripts/docker_safe.py -f
infra/compose.yaml …` unless noted. Stack: rebuilt `openpali-pipeline:local`,
`openpali-web:local`, e2e image on the round-4 working tree.

## Defects the battery exposed (all repaired in production code)

1. **Web regression (round-1 change)** — the release-pinned header summary in
   `web/src/App.tsx` replaced the static summary object WITHOUT `weekly`;
   `Header`'s sparkline read `.length` of undefined, React unmounted, the map
   never emitted `__mapReady`, and 8/13 browser specs timed out (the API-down
   spec passed because the throwing path needs a SUCCESSFUL release fetch).
   Fix: explicit static-base + release-overlay merge (`staticSummary` +
   `releaseSummary` + `useMemo`), which also removes the fetch race where a
   release response landing first permanently discarded the static bundle.

2. **Pointer-isolation defect (found as a corrupted live pointer)** — the
   current pointer resolved to `rel-c1534264` (kind=fixture, superseded, 334
   properties = 321 fixture + 13 test rows). Root cause:
   `publish_release` defaulted `kind="fixture", promote=True`, and
   `test_platform_integration.py`'s publication test called it bare against
   the shared cluster — promoting a synthetic release over the real one;
   `test_publication_faults.py`'s pointer-restore fixture then faithfully
   preserved the corruption it inherited. Repairs:
   - **Production gate**: `publish_release` raises `PublicationGateError` on
     `promote=True` + `kind="fixture"` (synthetic corpora stay
     release-qualified and API-addressable, never current) — negative control
     asserted in the integration suite.
   - `release-republish` and `ml-representative` jobs fail closed unless the
     current publication kind is `representative`.
   - Suite-wide session-scoped CURRENT-pointer restore in
     `pipeline/tests/integration/conftest.py`; the platform test publishes
     `kind="dev"`.
   - CLI `release-publish` gained `--no-promote`.
   - Operational note: test-integration legitimately flaps the pointer
     mid-suite; never run it concurrently with e2e-browser/api-bench.

3. **restore-drill race** — verification compared restored counts against the
   MOVING live DB (integration tests committed 8 observations during the
   ~40s window → exit 5). Fix: reference values captured at dump time;
   restored namespaces compared against those references.

4. **Spec defects (never-green round-3 specs)** — forecast spec fetched
   relative URLs before any `goto`; one-snapshot spec asserted the raw
   `permit_issued` count while the header renders it as a rate (now asserts
   `.metric-num` nodes: properties verbatim + derived rate); deep-link spec
   asserted the raw source id `calfire_dins` while the card shows the
   human source label ("DINS damage assessment…").

5. **Product improvement from a failing spec** — search indexed addresses
   only; APN search (how county records cite parcels) now matches digit
   prefixes in the same index.

## Heal + re-verification on the final images

- `full-release` (worker-executed): fresh representative release
  **rel-8716f0cf0692470db51059e9** / snap-143a32b51bd06233f498fb3e —
  6,216 properties, permit_issued 965, cofo 27, cleanup 3,982. Pointer healed
  through the production path (no manual pointer surgery).
- `ml-representative`: passes the new representative guard; typed
  `INSUFFICIENT_POINT_IN_TIME_HISTORY` prediction set
  `pset-aa88d2d54a9f68e535e2` (0 rows) for the new snapshot; /status and the
  property forecast panel surface it (browser-verified below).
- `test-integration`: **14 passed** (incl. the fixture-promotion negative
  control and rights-withdrawal drill). Current pointer verified UNCHANGED
  after the suite (rel-8716f0cf, 6,216 properties).
- `restore-drill` (fixed): **RESTORE DRILL OK** — 3-DB destructive
  clean-namespace restore; all dump-time references match (33,378+
  observation rows at drill time, manifest sha, prefect flow_run=14,
  mlflow runs=39).
- `replay`: **REPLAY OK** against rel-8716f0cf — 32,459 recomputed
  observations == ledger; 27,265/27,302 non-derived memberships reproduced
  from this release's exact bytes, 37 honestly attributed to earlier
  acquisitions of the same sources; zero network.
- `e2e-browser`: **13/13 passed (51.4s)** — a11y (methods/status/map/
  keyboard), deep-link DINS evidence, one-snapshot coherence (badge +
  header metrics + release-pinned MVT request), APN search, forecast
  insufficiency, model status + research export, correction journey,
  API-down last-known-good, USGS surfels draw/pick/legend, 2D hillshade.
- `scripts/check-fast`: green twice on the round-4 tree (pipeline tests,
  web tests/lint/typecheck, openapi-drift). Host unit suite: 161 passed.
- `api-bench`, `renderer-bench`: re-run on the final images — results
  appended below.

## Benchmarks on the final images

- `api-bench` (exit 0) against rel-8716f0cf: cold p50 71.4 / p95 159.5 /
  max 308.8 ms; warm p50 57.5 / p95 134.3 / max 189.5 ms; 200 requests x
  2 passes, 20 concurrent clients; zero errors, zero payload-cap violations;
  all four verdicts true (budgets: warm p95 750 ms, cold p95 3000 ms).
- `renderer-bench` (exit 0, report-only, SwiftShader — relative evidence
  only): hysteresis (round 3) removed the same-frame re-traversal. Medium
  scene now beats the PRE-BUDGET baseline: 156,934 splats/frame (-13%) at
  p50 1600.0 ms (vs 1866.6 baseline; the retraversal version had regressed
  to 2150.0). Wide scene converges across frames by design: 199,790
  splats/frame after 11 slow software frames (-8% vs baseline 217,559).
  Full table appended to cp4b-renderer-bench-baseline-2026-07-12.md
  ("AFTER v2"). No GPU frame-time claims from software rasterization.
