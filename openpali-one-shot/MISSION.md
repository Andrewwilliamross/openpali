# Mission: evidence-first OpenPali production MVP

## Why this exists

OpenPali should help Pacific Palisades residents, recovery organizations,
researchers, and policymakers understand the rebuild without turning partial
public records into false certainty. Its public claims must be reproducible,
source-backed, current, and explicit about what is observed, inferred, unknown,
or not comparable.

The repository already contains meaningful engineering: a Python ingestion and
scoring pipeline, static publication artifacts, a React/MapLibre product, a
GeoParquet spatial store, and a custom WebGL2 splat renderer. The mission is not
to replace those components reflexively. It is to turn the strongest parts into
a trustworthy production release candidate and remove or quarantine claims the
evidence cannot support.

## Stewardship and authority

Andrew Ross is the applied-AI researcher and project manager. respring.ai is
the sponsoring applied-AI lab. Fable 5 is the principal implementer and
architect for this experiment, with authority for reversible repository work
inside the mission. Product scope, source-code licensing, proprietary-data
rights, private resident data, material spend, deployment, and irreversible
actions remain with Andrew and the sponsor.

## Outcome

Deliver one complete public journey:

1. An authoritative public source is acquired into an immutable, identified
   snapshot with source metadata and schema evidence.
2. Records are normalized without inventing missing facts.
3. A versioned property/parcel identity and append-only recovery event ledger
   preserve source record, event time, observation time, and provenance.
4. Current recovery state is a documented milestone vector—not a forced linear
   ladder—and distinguishes scheduled, attempted, failed, approved, issued,
   observed, inferred, and unknown activity. Cleanup, design/review, permits,
   construction/inspections, and occupancy may progress in parallel.
5. Community throughput and bottleneck metrics use explicit numerators,
   denominators, windows, sample sizes, and validation state.
6. A forecast is shown only when a temporal, censoring-aware evaluation proves
   it is useful and calibrated. Otherwise the product honestly presents a
   descriptive baseline or “insufficient evidence.”
7. A user can find a property and inspect its source-backed timeline, current
   state, freshness, limitations, and the evidence behind consequential claims.
8. A reproducible CI/release process stages, validates, and atomically promotes
   a coherent snapshot while retaining the last known good snapshot.

The result is a deployable **release candidate**, not an actual production
deployment. Do not push or deploy during this experiment.

## Critical starting facts to re-verify

The checked-in 2026-06-11 publication calls 489 parcels “under construction,”
yet all 817 emitted inspection events are labeled `insp scheduled`. Inspections
from ancillary permits can also advance the home-rebuild stage. Missing cleanup
dates are replaced with the 2025-01-07 fire date, including 1,595 private
opt-outs. `PALISADES_WF_REBUILD` is fetched but ignored. The existing
reconciliation has no construction oracle and a later run reports 23.8% CofO
drift. These defects contaminate the score, ETA, and any prospective learning
system.

Therefore the first accepted checkpoint must repair source semantics and
publication safety. New ML, orchestration, data sources, or 3D features cannot
compensate for invalid labels.

## Product boundary

### In scope

- Repository archaeology and a reproducible current-state report.
- Formal definitions for parcel, structure, qualifying fire rebuild,
  milestone/state, event, source record, snapshot, and public metric.
- Source-contract tests and golden semantic fixtures for the existing County,
  LADBS permit, LADBS inspection, Malibu, and Socrata integrations.
- Immutable raw/run manifests, bitemporal normalized events, stable event IDs,
  idempotency, lineage, schema drift detection, and true offline behavior.
- Atomic publication with one shared snapshot ID, critical fail-closed gates,
  last-known-good retention, and rollback instructions.
- A defensible current-state/bottleneck engine and a lightweight versioned
  experiment path for future learning.
- A naive and a censoring-aware statistical baseline, temporal backtesting,
  calibration/coverage reporting, and a data-sufficiency decision.
- One tested property journey plus community metrics, freshness, evidence,
  uncertainty, limitations, and accessible/mobile behavior.
- CI, scheduled-refresh configuration, operational runbooks, source-rights
  inventory, privacy/methodology notices, security policy, and contributor
  documentation appropriate to an open-source release candidate.
- A bounded 3D pass: truth-in-labeling, license gate, coherent snapshot/version
  selection, 2D-first loading, coverage disclosure, deterministic benchmarks,
  and only measured fixes required for MVP safety or usability.

### Non-goals

- Production deployment, DNS, cloud-resource creation, or live migrations.
- Purchasing imagery, satellite tasking, drone work, or collecting resident
  photos/private records.
- A general digital twin, new 3DGS training system, synthetic reconstruction,
  photorealistic completion, or survey/insurance-grade measurement.
- Automatic model promotion or retraining on every refresh.
- Wholesale Plexe integration, a large AutoML search, Prefect adoption without
  measured workflow need, or microservices.
- Parcel-level causal claims about policies, technologies, funding, insurers,
  contractors, or resident behavior. Observational trend reporting is not
  causal evaluation.
- Legal, insurance, financial, engineering, or permitting advice.
- Choosing the sponsor's source-code license or asserting imagery rights on its
  behalf.

## Execution policy

Fable owns the mutable implementation plan and may choose the simplest sound
design. The following ordering is a dependency graph, not a mandated class or
directory design:

1. Reproduce and independently audit the starting state. Preserve pre-existing
   changes and record exact commands.
2. Establish domain definitions against live schema metadata, source docs,
   golden records, and official dashboard definitions. Repair truth defects.
3. Build source/run manifests, bitemporal events, snapshot identity, offline
   semantics, atomic publication, and fail-closed validation.
4. Recompute all downstream artifacts and expose reconciliations and source
   health. Do not keep compatibility with invalid scores merely to preserve a
   color palette.
5. Implement descriptive metrics and the minimum valid forecasting experiment.
   If data is insufficient, suppress parcel ETAs and produce the collection
   plan rather than forcing a model.
6. Complete the property/community vertical slice and browser evaluation.
7. Harden CI, operations, governance, accessibility, and performance.
8. Perform the bounded spatial/license pass.
9. Run the fresh independent evaluator, repair every material failure, rerun
   all gates, and produce the final report.

At milestone boundaries, preserve a coherent commit and update the compact
state. A best-valid pointer may advance only after required machine gates and
fresh evaluator evidence. Experimental work must not erase that checkpoint.

## Subagent policy

Use the supplied agents proactively:

- `openpali-repository-auditor`: read-only archaeology and regression mapping.
- `openpali-source-researcher`: official schemas, definitions, licensing, and
  public-data candidates.
- `openpali-methods-reviewer`: censoring, temporal evaluation, calibration,
  metric design, and causal-claim review.
- `openpali-spatial-reviewer`: acquisition time, asset truth, browser/GPU
  profiling, rights, and benchmark design.
- `openpali-independent-evaluator`: fresh, skeptical final and milestone
  verification; it must not modify product code.

Keep working while background research runs. Resolve disagreements with primary
sources and observed behavior. Do not delegate the architectural synthesis or
final integration.

## Human/external gates

The sponsor must choose the source-code license. Written permission or a valid
license must cover LARIAC/EagleView/Pictometry imagery, derived 3D assets,
redistribution, and any model training before those assets can ship. A public
URL is not permission. Default-disable or replace unresolved assets; document
the exact decision needed from Andrew.

No non-public resident material may enter Fable's context. Design future
privacy and consent boundaries without ingesting real private data.

## Definition of completion

`contract/acceptance.json` is authoritative and initially fails. Fable may add
stricter tests and acceptance items, never weaken or delete the supplied ones.
Results and evidence belong under `state/`; do not edit status fields in the
contract.

Completion requires a captured fresh evaluator `VERDICT: PASS`, all mandatory
machine gates green, a clean worktree, coherent commits, and a final report for
a founder who did not watch the run. The report must lead with what demonstrably
works, then evidence, limitations, external release gates, and the next three
highest-value missions.
