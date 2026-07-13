# Mission: build the OpenPali production MVP

## Purpose

OpenPali is intended to become open-source recovery intelligence for the
Pacific Palisades. It
should help residents understand what public evidence exists for their property,
help the community see where recovery is moving or bottlenecked, and give
researchers and policymakers reproducible longitudinal data without converting
partial records or imagery into false certainty.

The repository is already a meaningful prototype: Python source adapters and
scoring, static public artifacts, a React/MapLibre product, a GeoParquet spatial
store, registration code, splat tiling, and a custom WebGL2 renderer. Fable's
mission is to turn that prototype into an integrated, locally deployable
production-MVP release candidate. The work must include the platform and feature
engineering needed for OpenPali to keep collecting, learning, mapping, and
serving recovery evidence after this run.

## Authority

Andrew Ross is the applied-AI researcher and project manager. respring.ai is
the sponsoring applied-AI lab. Fable 5 is the principal implementer, architect,
and CTO for reversible repository work in this mission.

Andrew retains decisions over source-code licensing, proprietary data rights,
private resident data, material external spend, production deployment, and
irreversible action. Those decisions may gate public release; they do not narrow
the safe local implementation scope.

## Non-negotiable outcome

Deliver a release candidate with six connected capabilities:

1. **Recovery data platform.** Immutable raw/source artifacts, source and run
   lineage, stable property/parcel/structure identity, append-only bitemporal
   recovery observations, point-in-time snapshots, audited metrics, and atomic
   last-known-good publication.
2. **Production backend.** Persistent geospatial/query storage, schema
   migrations, object-storage abstraction, idempotent jobs, a typed and
   versioned API, health/readiness, snapshot pinning, source/model/spatial
   metadata, and generated frontend contracts.
3. **Continual ML system.** Point-in-time datasets and features, a naive
   baseline, a censoring-aware baseline, at least one justified challenger,
   temporal backtesting, calibration/coverage/cohort analysis, experiment and
   model tracking, manual promotion gates, snapshot-triggered reevaluation,
   batch predictions, and honest insufficiency behavior.
4. **Spatial and 3D platform.** A rights-safe source/capture-to-asset path,
   acquisition time and CRS/datum provenance, registration and quality gates,
   a deterministic reconstruction fixture/job, versioned spatial publication,
   coherent top-down 2D and interactive 3D layers, and measured fixes for the
   most important renderer, z-fighting, GPU/memory, request, picking,
   registration, or visual-quality defects.
5. **Public product.** API-backed resident/property and community/bottleneck
   journeys with evidence, freshness, conflicts, unknowns, model status and
   uncertainty, spatial coverage and observation kind, correction path,
   research exports, mobile/accessibility behavior, and graceful stale/offline
   states.
6. **Production operations.** Reproducible local topology, fast/full/CI gates,
   scheduled refresh entrypoints, observability, performance budgets, release
   bundles, security/privacy/rights enforcement, SBOM/scans, backup/restore,
   rollback, runbooks, and governance foundations.

The property recovery journey is the first integration spine across these
capabilities. It is not the ceiling of the one-shot.

## Required architecture

Use the implementation blueprint in
`openpali-one-shot/research/production-mvp-architecture.md`. Its default is a modular monolith
plus workers:

- the current Python project evolves into domain, storage, ingestion, metrics,
  ML, spatial, publication, API, and orchestration modules;
- PostgreSQL/PostGIS is the canonical query and transactional plane;
- an S3-compatible abstraction holds immutable source, feature, model,
  spatial, and publication objects, with a pinned SeaweedFS S3 service for the
  local stack;
- Prefect runs source, snapshot, analytics, model, spatial, and release flows;
- MLflow records experiments and model artifacts;
- FastAPI exposes versioned read contracts and health;
- React/MapLibre/WebGL consumes the API and immutable assets; and
- deterministic static JSON/Parquet/tiles remain portable derivatives, not the
  sole backend.

This is not a mandate for microservices or a greenfield rewrite. Reuse and
migrate existing code behind tested boundaries. Fable may adopt an equivalent
design only with a measured ADR showing how it preserves every contract,
operator command, failure mode, and product capability.

## Phase 0: safe labels and public truth

The first product checkpoint must repair the known load-bearing defects:

- scheduled, future, failed, canceled, missing-status, or ancillary-permit
  inspections cannot prove physical construction;
- `PALISADES_WF_REBUILD`, permit type, jurisdiction, multi-permit, and
  multi-structure semantics are explicitly resolved from source evidence;
- private cleanup opt-out is not cleanup completion;
- missing event times remain null or interval-censored rather than becoming
  the fire date, run date, or today;
- current state is a versioned projection over parallel cleanup,
  design/review, permitting, construction/inspection, and occupancy lanes;
- the invalid 0-100 score/ETA is removed from public API, forecast, sorting,
  color, map, and spatial behavior or explicitly deprecated outside the public
  product; every authorized downstream count, metric, prediction, color, and
  artifact is recomputed; and
- publication fails closed on undocumented taxonomy, schema drift,
  reconciliation failure, partial acquisition, or mixed snapshots.

Create executable positive, negative, ambiguous, conflicting, corrected,
future, missing-date, ancillary-permit, multi-structure, and cross-jurisdiction
fixtures. Phase 0 supplies valid domain types and labels to every later track.
It is not a terminal outcome.

## Mandatory implementation workstreams

### Backend and data plane

Implement real production behavior, not architecture diagrams:

- database schemas and migrations for sources, acquisition runs, raw objects,
  identities, source-record versions, observations/revisions, snapshots,
  metrics, reconciliations, datasets, experiments, models, predictions,
  spatial assets/candidates/review state, jobs, publications, and corrections;
- content-addressed immutable object storage and an exact run/snapshot manifest;
- online acquisition plus true zero-network offline replay;
- deterministic paging, schema/domain drift detection, idempotency,
  corrections/retractions, late-arrival behavior, and point-in-time queries;
- orchestrated source refresh, civic snapshot, analytics, model evaluation,
  spatial refresh, and release-candidate flows with typed retry/failure policy,
  worker restart/idempotency, and reconciled Prefect/OpenPali lifecycle IDs;
- transactional staging/promotion with PostgreSQL/API as the sole current/LKG
  authority, a non-authoritative object mirror, rollback, and fault-injection
  tests; and
- `/v1/releases/current` plus release-qualified property/search/observations/
  forecast/community/bottleneck/source/spatial/tile interfaces, separate live
  operational health, liveness/readiness, OpenAPI, generated TypeScript types,
  release-bound pagination/cache semantics, and bounded queries.

Migrate every applicable core civic source named in the architecture source
policy and consequential new CAL FIRE DINS data through the production path.
DINS counts only when the verified full incident-filtered result, pagination,
damage distribution, APN/address/spatial join and ambiguity counts, and an
independently checked public property contribution all pass.
Execute a separate current representative release and zero-network replay of
its exact raw hashes; a polished fixture release cannot substitute for it.

### Analytics and continual ML

Replace the 0–100 heuristic as a prediction mechanism. Model explicit recovery
questions and risk sets rather than a universal rank.

The first target is qualifying rebuild application submission to permit
issuance: censoring-aware time-to-issuance and probability by 180 days. The
unit is one qualifying application, never a silent property-level aggregation;
withdrawal/cancellation/expiration policy and post-horizon behavior are
predeclared. The implementation must build historical features using only observations
known at each cutoff; declare populations, targets, horizons, censoring and
competing events; create rolling-origin splits plus an untouched final period;
and version data, features, labels, code, configuration, seeds, environment,
metrics, calibration, cohorts, and artifacts.

Run a naive cohort baseline, a valid censoring-aware baseline, and at least one
interpretable challenger. Evaluate discrimination/error as appropriate,
time-specific loss, calibration, interval coverage, sample size, censoring,
follow-up, missingness, and cohort failure. A new snapshot must trigger a
reproducible challenger evaluation and report; model promotion remains manual
and independently gated.

The current representative ledger must always produce a real dataset,
late-entry/sufficiency report, and any statistically valid naive or
censoring-aware estimate. It may fit a representative challenger only when a
precommitted methods-reviewed point-in-time-history gate passes; otherwise it
must emit `INSUFFICIENT_POINT_IN_TIME_HISTORY`. The complete challenger,
serialization, MLflow/OpenPali lifecycle, rejection, and serving path still
executes on a nontrivial temporal fixture. Filesystem dates, current-row
presence, retrospective status, and outcome dates never prove historical
availability.

If real observations cannot support a public parcel estimate, serve a typed
`insufficient_evidence` result and descriptive cohort history. That suppresses
an unsafe prediction; it does not excuse omitting datasets, experiment runs,
tracking, registry, promotion logic, batch serving, drift/reevaluation, or the
fixture-backed eligible path.

### Spatial, multimodal, and 3D

Treat spatial engineering as a core track. Preserve source/vintage,
acquisition/observation/processing time, horizontal CRS, vertical datum,
registration transform/residual, extent, resolution, coverage, quality,
lineage, observation kind, rights state, and format version for every asset.

Ship all of the following:

- a real bounded public-domain USGS post-fire 3DEP Palisades AOI through the
  production source-to-browser path, covering at least 25 damaged-universe
  parcels and four requested LOD tiles and producing a nonempty USGS-derived
  point/surfel layer in the custom renderer as well as terrain;
- a source/capture registry and immutable asset pipeline;
- terrain/elevation and parcel/evidence layers for the coherent snapshot;
- independently labeled Gaussian/surfel/fallback vintage slots without
  concatenating stale epochs;
- a multimodal observation candidate/review state machine integrated with the
  recovery ledger, where only accepted candidates append observations;
- a CPU-runnable reconstruction/registration fixture and production job path,
  plus an optional pinned GPU worker profile and bounded pilot when available;
- a nontrivial two-view/depth-cloud fixture with withheld nonidentity transform,
  noise, occlusion, change/no-change regions, estimated alignment/fusion, and
  predeclared numeric transform/RMSE gates rather than a hard-coded result;
- the same scan/evidence structure meaning in top-down 2D and opt-in 3D, with a
  neutral contextual basemap, street labels, explicit fallback/no-coverage,
  and no score-tinted pre-fire geometry presented as current evidence;
- deterministic reference scenes, screenshots, numeric registration checks,
  z-fighting/ordering reproductions, and browser/GPU/network/frame/memory
  benchmarks; and
- at least one material, profiling-selected production improvement, with
  before/after evidence, to loading/cancellation, worker sorting/decoding,
  memory allocation/eviction, picking, GL lifecycle/context recovery,
  registration/datum, splat quality/LOD, or z-fighting.

Unresolved LARIAC/EagleView/Pictometry rights require default exclusion or an
open replacement. They do not permit disabling the entire 3D capability.

### Product and operations

Build routed, API-backed property, map, community, methods, and status
experiences. A user must be able to trace a consequential claim to its source
and snapshot, understand unknown/conflicting evidence, inspect bottleneck and
model limitations, distinguish current/prior/derived/inferred spatial content,
and use the core journey with keyboard, mobile, reduced motion, or no WebGL.

The repository must provide a documented validated-Compose-plus-bootstrap local
startup sequence, fast and full gates, a fixture release, a separate current
representative-data release, model
evaluation, spatial benchmark, browser E2E, release
bundle, rollback, and restore drill. CI must run the same executable checks as
local development; workflow YAML alone is not evidence. Add structured
run/request/snapshot/source/model/asset observability, alerts tied to runbooks,
dependency/secret/vulnerability checks, SBOM, privacy and methodology notices,
attribution, correction/contact, security policy, and technical rights gates.

## Execution sequence

1. Reconcile the intended local starting state and reproduce current behavior.
2. Repair source semantics and establish the golden truth gate.
3. Build the storage/object/API spine and migrate one source-to-property slice.
4. Complete multi-source orchestration, event storage, metrics, and atomic
   publication.
5. In parallel, implement the continual-ML, spatial/3D, and complete-product
   tracks against the shared snapshot and APIs.
6. Integrate all tracks into one fixture release and inject dependency,
   acquisition, schema, model, publication, browser, and renderer failures.
7. Complete CI, security, observability, operations, performance, and release
   packaging.
8. Run a fresh independent evaluation, repair material failures, and repeat
   until every technical criterion passes.

The principal owns the critical path. Read-only research subagents may run in
parallel, but their summaries never replace implementation or verification.

## Explicit non-goals

- Actual cloud/production deployment, DNS, live migration, or merging/pushing.
- Purchasing or tasking imagery; collecting private resident photos or records.
- Choosing a source-code license or asserting proprietary rights for Andrew.
- Automatic model promotion, unsupported causal impact claims, or resident,
  agency, contractor, insurer, or program rankings.
- Reconstructing the full Palisades at survey/insurance quality during this
  local run.
- Kafka, Kubernetes, a service mesh, microservice-per-source, a generic AutoML
  platform, or unrelated framework rewrites.

These exclusions limit authority and unnecessary scale. They do not remove the
local backend, continual-learning platform, reconstruction/asset path, 3D
product, or operations foundations.

## Completion rule


`openpali-one-shot/contract/acceptance.json` is authoritative and begins red.
Every technical MUST requires a production implementation artifact outside
`openpali-one-shot/` plus current runtime evidence of the declared kinds. A
generic test log, documentation, a schema with no caller, a workflow with no
executed flow, a model report with no reproducible run, or a benchmark with no
production change cannot satisfy it.

Completion requires:

- a Prefect-worker fixture release and a separate current representative release
  through acquisition, ledger, analytics, model, spatial publication, API, and
  browser, plus exact-hash zero-network replay of the representative inputs;
- a clean candidate commit with meaningful implementation in every component;
- all fast/full/data/API/model/spatial/browser/security/ops gates passing;
- a fresh skeptical evaluator PASS after independently exercising that exact
  candidate, captured automatically by the supplied hook; and
- a founder-readable final report committed in that evaluated candidate and
  leading with demonstrated product behavior,
  measured model/spatial/system results, limitations, external release gates,
  and the next three highest-value research or implementation efforts.

After the evaluator passes, make exactly one child evidence commit that changes
only `openpali-one-shot/state/evaluator-latest.md` and
`openpali-one-shot/state/evaluator-attestation.json`. The terminal
command `python3 openpali-one-shot/scripts/verify_completion.py` must pass at
that clean child commit. Do not add another control loop or modify product code
between the evaluated candidate and this evidence commit.

Only the source-code license and specific external rights/credential decisions
may remain human gates after all safe implementation and default-disable paths
are complete. Backend, data, ML, spatial, frontend, and operations cannot be
recorded as planned deferrals or external blockers.
