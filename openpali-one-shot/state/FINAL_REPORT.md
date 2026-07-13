# OpenPali production-MVP release candidate — founder report

**Date:** 2026-07-12 · **Branch:** `codex/openpali-one-shot-harness`
**Deployment:** single-host Docker Compose (`infra/compose.yaml`), driven
exclusively through the audited wrapper. Evidence for every claim below is a
command, container exit code, API response, or browser assertion recorded in
`openpali-one-shot/state/evidence/`.

---

## 1. What is demonstrated (verified behavior, not plans)

### Truth semantics (the foundation)
- Evidence-backed, fail-closed taxonomy over seven public sources. Scheduled
  inspections never count as outcomes (the public LADBS feed contains only
  `Insp Scheduled` — verified against the live service). Qualifying rebuild =
  the city's own `Bldg-New` + Palisades-rebuild flag. Missing dates stay
  unknown; nothing is backfilled with the fire date or "today".
- Bitemporal ledger: occurrence time and observation (acquisition) time are
  separate everywhere; corrections/retractions are append-only revisions;
  conflicting sources surface as conflicts, not silent picks.
- Live truth-gate result on real data: the legacy pipeline's 489 invalid
  "under construction" parcels reduce to 1 evidenced + 436 scheduled-only;
  certificate-of-occupancy inflation (23.8% baseline error) reduced to 0.0%
  drift against the county service.

### Platform
- PostgreSQL/PostGIS + content-addressed immutable object store (SeaweedFS)
  + Prefect process worker + MLflow + FastAPI (17 routes) + React/MapLibre.
  All third-party images digest-pinned; one labeled egress proxy with a
  documented allowlist; runtime networks internal; non-root images.
- Releases are atomic single-transaction promotions behind fail-closed gates
  with last-known-good rollback; the API serves only release-qualified,
  manifest-selected artifacts (stale asset versions 404).
- Zero-network replay: 35 representative raw pages digest-verified and
  32,459 observations recomputed byte-deterministically offline.

### Continual ML (fixture-proven, honestly gated on real data)
- Point-in-time datasets with a PRECOMMITTED history gate; chronological
  rolling-origin folds; an untouched final holdout. Two independent methods
  reviews were commissioned; both blockers (leaky interleaved folds,
  unenforced promotion gates) were repaired and re-verified.
- In-cluster drill 12/12: byte-identical rebuilds, N→N+1 semantics (late
  arrivals by OBSERVATION time, retraction propagation), Cox challenger
  beats the censoring-aware KM baseline on forward evaluation, a
  fold-evaluated model is REFUSED promotion, one final-holdout evaluation is
  promoted by a named reviewer under fail-closed gates (calibration,
  per-cohort regression, dataset contracts), and 59 predictions serve from
  the immutable artifact in a fresh process.
- On the real ledger the gate correctly fails (single-burst acquisition):
  the challenger emits typed `INSUFFICIENT_POINT_IN_TIME_HISTORY`, baselines
  still run, serving records a typed insufficiency, and the public forecast
  endpoint explains it. A fixture-trained champion is structurally barred
  from serving civic data (domain lineage check, verified live).

### Spatial / 3D (rights-safe, live)
- Frozen 4-tile USGS 2025 post-fire lidar AOI (public domain; 1,728+
  destroyed parcels) acquired through the SAME production contract as civic
  sources; GEOID18 grid-based datum normalization (guarded against silent
  identity fallback); 1M-surfel 3D-Tiles pyramid + 231 terrarium terrain
  tiles; registry rows carry CRS/datum, flight-vs-processing time, rights,
  lineage, seam quality (2.5 cm), and parcel coverage reconciliation
  (1,579/1,773).
- Browser-verified (containerized Playwright, 6/6): release-qualified tile
  requests over the wire, real instanced draw calls, click-picking into the
  property card with the post-fire provenance badge, legend labeled with the
  FLIGHT date, 2D journey intact.
- Reconstruction fixture 12/12: a withheld 1.476 m / 3.0° transform is
  estimated by production registration to 0.002 m / 0.002° (after fixing a
  real ground-dominant-scene RANSAC defect), candidates carry
  residual-derived confidence, and only reviewed acceptance appends civic
  observations (rejection/retraction auditable). GPU worker boundary returns
  typed `unsupported_hardware`.
- Renderer improvement measured before/after on deterministic scenes: a
  per-frame splat budget cut wide-view instanced draws 24% and resident GPU
  memory 10% with the correctness gate green. Frame-time numbers under
  SwiftShader are honestly scoped as software-raster; GPU frame-time claims
  require a headed run (below).

### Product journeys
- ONE snapshot everywhere: the parcel map paints from the pinned release's
  MVT tiles, the header counts come from the release manifest, the card's
  lanes/timeline come from the release API, and a visible badge names the
  release + snapshot (or says "offline · last-known-good" explicitly when
  the API is unreachable and the bundled fallback serves).
- Routed, shareable journeys: `/map`, `/property/:apn` (URL-synced),
  `/methods` (definitions + claim boundaries + release-pinned policy
  versions), `/status` (release, LKG, per-source freshness, the learning
  system's typed status, and the snapshot-addressed research export).
- Forecast-or-insufficiency is inspectable in the product: the property
  card shows the submission-time estimate from the reviewed champion or the
  typed reason none is served; /status shows the model state for the
  release.
- 2D-first: 3D loads only on explicit request, a WebGL2 probe disables the
  toggle where unsupported, and context loss falls back to the full 2D
  journey. The rights-pending pre-fire county model renders only behind its
  own labeled opt-in; vendor ground imagery is opt-in too.
- Corrections: rate-limited POST verified live (202, idempotent resubmit,
  429, 404), contact stored in a restricted table, human moderation only.
- Accessibility: axe gate over every route (three real violations found and
  fixed), keyboard operability, reduced motion.

### Operations (drilled, not asserted)
- Publication authority hardening from a drill finding: an integration run
  promoted a synthetic fixture release to the public pointer. The publisher
  now structurally refuses to promote fixture-kind releases (they stay
  release-qualified and API-addressable, never current), the republish and
  batch-model jobs fail closed unless the current release is representative,
  and the integration suite restores the pointer AND publication statuses it
  found.
- Gate rerunnability from an independent-evaluation finding: the ML and
  reconstruction drills are rerunnable on a cluster where the published
  fixture release exists — the fixture reset preserves publication-pinned
  snapshots (deterministic builders converge back onto identical content)
  and the recon drill clears only its own unpublished review-state. The
  entire service-half gate runs as ONE command via the compose gate chain
  (`infra/compose.gate.yaml`, `up -d full-gate`), serialized with
  fail-closed `service_completed_successfully` conditions.
- Restore: destructive clean-namespace restore (all three databases) with
  dump-time reference verification — PASS.
- Scheduling: a scheduler-created run executed by the worker — PASS.
- Worker kill: a mid-run worker restart was injected; the REAL finding
  (zombie Running runs are never marked failed) was remediated with
  `flow-reap` making failures visible; recovery re-run converges thanks to
  idempotent acquisition + atomic promotion.
- Observability: pinned Prometheus/blackbox profile; injected mlflow outage
  fired `ServiceDown` and resolved after restoration.
- Security gates EXECUTE locally with artifacts (scripts/check-security):
  locked-dependency audits, CycloneDX SBOMs for both stacks, a
  checksum-pinned gitleaks scan of the full git history (findings triaged —
  PowerBI public embed URLs, not credentials) and a planted-secret negative
  control proving the scanner works. CI runs the same gates. SECURITY.md
  documents the threat model; RUNBOOKS.md ties every alert to wrapper
  commands; release-bundle records commit/images/artifacts/risks. Failed
  independent cross-checks ride as disclosures ON the affected public
  metrics, and the OpenAPI contract is drift-gated on every fast-gate run.

## 2. Limitations (known, deliberate, disclosed)

- **Point-in-time ML on real data is honestly insufficient**: every source
  was acquired in one burst, so no public forecast is served — by design the
  gate must see ≥3 acquisition dates over ≥60 days. The complete learning
  system runs today on the temporal fixture; it will graduate automatically
  as scheduled acquisitions accumulate history.
- **Renderer GPU performance**: headless evidence is SwiftShader-only. A
  headed benchmark run on real hardware (one command: the renderer-bench job
  against a headed browser) is required before any GPU frame-time claim.
- **Permit enrichment (portal links/valuations) in the card** still comes
  from the pipeline's static bundle; the evidence timeline, lanes, map
  paint, and header counts are all release-API-served.
- **Single-host trust model**: fixture credentials, loopback HTTP accel,
  in-process rate limiting — documented in SECURITY.md; multi-instance
  deployments need a shared limiter and real secrets.
- CofO cross-portal reconciliation runs with predeclared tolerance and its
  failures surface as metric disclosures; the underlying portal lag/format
  question remains open and disclosed rather than hidden.

## 3. APPROVAL-001 — decisions that remain the sponsor's (human gates)

1. **LARIAC-derived pre-fire corpus rights**: registered `unresolved` and
   technically excluded from every public release manifest (visible in the
   manifest's `excluded` list). Publishing it, licensing it, or using it for
   model training is a county-license decision only the sponsor can make.
2. **Public launch of forecasts**: even after the history gate passes,
   promotion requires a named human reviewer; no automatic path exists.
3. **Repository license**: no LICENSE is claimed; the README now states
   licensing is an undecided, sponsor-owned decision (the baseline README's
   "open source" claim and retired score/ETA prose were removed). Releasing
   under any terms is sponsor-owned.
4. **EagleView/Pictometry imagery**: consumed as county-published WMTS at
   display time only; any deeper use needs vendor terms review.
5. **Resident-facing corrections policy**: the moderation queue exists;
   staffing it and the response SLA are operational decisions.
