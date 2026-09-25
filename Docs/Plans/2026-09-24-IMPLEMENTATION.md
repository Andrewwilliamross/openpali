# Recovery intelligence implementation

Owner: OpenPali / RE\SPRING. Started September 24, 2026.

## Outcome

A runnable evidence workspace covering standing and destroyed parcels, with
source-linked property histories, cleanup documents, permit detail, visual and
utility context, acquisition tasks, and professional project claims. Estimates
must disclose their support and abstain when the data cannot support a number.
This executes the research in [the expansion report](../Research/2026-09-24-DATA-EXPANSION.md).

## Execution order and acceptance

1. **Release integrity.** Persist ingestion-run membership even for unchanged
   records. Freeze parcel details and geometry in releases. Reject invalid map
   bounds. Unsupported survival evaluations return no score. Regression tests.
2. **Evidence integration.** Reproducibly import the acquired parcel universe,
   cleanup inventory, assessor histories, PCIS detail, and visual/utility samples.
   Retain source, capture/observation dates, hashes, coverage, and limitations.
   All-parcel and destroyed cohorts remain explicit; unknown is never undamaged.
3. **Acquisition and analytical workflows.** Generate actionable coverage tasks,
   neighborhood exposure measures, screened sale comparables, and honest model
   support gates. Project claims remain unverified until evidence is reviewed;
   ranking requires observed role-specific start/end dates and scope.
4. **Frontend.** Replace the absent frontend with React, official coss components,
   and a parcel map. Search, property evidence, history, documents, visual/utility
   context, market support, and project claims must work against the same release.
5. **Verification and handoff.** Run Python and frontend checks, exercise the local
   application, document exact counts and commands, and record remaining external
   dependencies. Do not publish or describe an unvalidated prediction as a result.

## Decisions

- Retain the canonical PostGIS ledger and immutable publication architecture.
- Ship portable, hash-addressed evidence releases for local inspection and open
  data export as well as database ingestion; raw restricted materials are not
  silently republished. Public source links remain available.
- Begin with reproducible spatial features and interpretable baselines. Price
  effects of neighboring vacancies require temporal controls, held-out geography,
  transaction screening and uncertainty evaluation before causal claims.
- LiDAR is a dated geometric baseline. Current construction classification needs
  repeat captures and independently labeled validation parcels.
- Browser extraction uses deterministic parsing, bounded retries and retained
  failures. A denied HTTP request is not a reason to discard a property.
- Verified professional contributions and completed trade durations are separate
  from a submitted claim. No leaderboard based on permit issue-to-final shortcuts.

## Execution record

Implementation in progress. See the final section for verified delivery and
remaining dependencies; planned work above is not a claim of completion.

## Delivered and verified — September 25 UTC

### Data execution

The portable release is `evidence-ae1dee2a6a226cbb9fd92626`.

| Delivered evidence | Count / interpretation |
|---|---:|
| Property records | 10,155: ZIP + destroyed-fire cohort + an exact-AIN reference |
| Valid parcel geometries | 10,141; 14 unresolved AINs retained as tasks |
| Agency destroyed parcels | 5,877 |
| County PDF links | 4,289; link presence is not cleanup completion |
| Current LADBS permit inventory | 6,485 acquired; 6,409 linked to this universe |
| Scheduled inspection requests | 1,024 acquired; 953 linked unambiguously |
| Actual PCIS inspection outcomes | 34 rows on one detailed permit |
| Assessor histories | 29 complete matched parcel samples |
| Listing samples | 2 browser-verified research transcriptions |
| LiDAR | One dated crop, 52,808 points; ground-normalized measurements |
| Sewer engineering context | Four segments within 50 m of one sample parcel |
| Acquisition tasks | 20,720; tasks are gaps, not adverse property conditions |

Executed three additional live acquisitions: 1,210 exact-AIN geometry results,
25 balanced missing-history samples, and complete current LADBS permit/request
inventories. Source rows that cannot join remain archived and are reflected in
source acquired/linked counts; they are not treated as successful parcel matches.
The original unmatched assessor reference was resolved by the exact-AIN lookup.

### Software delivered

- Canonical acquisition-run/record membership with a migration and explicit
  historical-backfill limitation. Reobserved unchanged records remain members.
- Canonical release detail, bbox search and vector-tile geometries now use frozen
  snapshot membership. Identity fields are frozen for new snapshots. Legacy
  identity fields are empty rather than filled from current mutable identities.
- Corrected unsupported IPCW scoring and geographic/tile input validation.
- Portable artifact builder, cryptographic verification, repeatable release ID,
  source links and dates, evidence APIs and an optional canonical ledger importer.
- New React/coss/MapLibre interface, coverage page, parcel evidence, recorded
  transfers/listing samples, source packets, inspections, dated visual and sewer
  context, and local project-role claims / acquisition actions.
- Metric 100/250/500 m destroyed-neighbor exposure. No asserted current vacancy
  share or causal price effect. Primary-home permit projection excludes explicit
  ADU/garage uses and rejects impossible/future milestone dates.
- Descriptive primary-home submission-to-issuance summary: 904 issued records
  with valid dates, median 87 days, 292 not yet issued. Completed-case timing is
  explicitly not a forecast or contractor performance measurement.
- LiDAR measurements: nearest classified ground within 2 m, noise exclusion,
  explicit CRS provenance, support fraction and height quantiles. No current
  building-state classifier is claimed.
- Bounded assessor batch worker, exact-AIN and permit inventory collectors,
  plus a PCIS browser worker that retains failure pages and stops on access denial.
  PCIS worker parsing and job validation are tested; its browser navigation has
  not been exercised end to end in this execution.

### Verification

- Python: **194 passed, 17 skipped**. New boundary tests cover false cleanup
  inference, malformed coordinates, censored evaluation, ADU completion, source
  hashes, transfer screening, neighborhood counts and local draft isolation.
- Frontend: **3 tests passed**, TypeScript/lint passed, production build passed.
- Browser parsers/work queue validation: **5 Node tests passed**.
- OpenAPI regenerated; drift check passes. `git diff --check` passes.
- Rebuilt the real release from identical inputs and verified identical manifest,
  release ID and every artifact hash.
- Live API read checks passed. Desktop visual review showed the map, selection,
  property details and collection controls rendering. Browser DOM automation was
  unavailable; native screenshot inspection succeeded. Mobile interaction and
  full browser journey automation remain unverified.
- PostGIS/S3 integration, the ledger migration/import, container build and full
  deployment suite were **not run**: this machine has no functioning Docker
  executable/daemon or available PostGIS server. The new exact-run regression is
  included in the service integration suite. No production pointer was changed.

### Start and operate

See the root README for `make evidence-build`, `make evidence-api`, and
`make evidence-web`. Open http://127.0.0.1:5173. The browser pins a release;
reload to adopt a newer one. Drafts are local, persistent operational records.
The backend defaults to denying writes unless the local-workspace flag is set.

### Remaining program work

These are not delivered capabilities or deferred fixes disguised as predictions:

1. Run real PostGIS migration/replay/import and publication drills on a working
   isolated service stack, then authorize a production release separately.
2. Extend browser navigation verification and continuous listing/PCIS collection;
   broaden assessor coverage with resumable batches. Listing pages in this release
   are two sourced transcriptions, not a running Redfin/Zillow feed.
3. Obtain repeat current visual observations, label evaluation parcels, register
   sensors/CRS, evaluate change/height/roof/framing models and uncertainty. TorchGeo
   remains an appropriate future training tool; no trained model is shipped here.
4. Expand water/power/gas/civic infrastructure beyond the sampled sewer context,
   including dated assets, outages, plans versus actual work and telemetry access.
   No wildfire prevention prediction or water-network simulation is asserted.
5. Assemble screened closing-price labels and as-of property/site features; fit
   and evaluate spatial/temporal holdouts before publishing valuations or vacancy
   effects. No housing-price prediction is currently returned.
6. Public identity, property-role evidence verification, moderation, consented
   field submissions, and comparable trade-duration benchmarks must precede public
   claims and professional rankings. Current claims are explicitly local drafts.

The absent frontend was rebuilt with new source files. The pre-existing deletion
of old bundled assets, old frontend tests and unused old components was not
reversed. CVP informed the parcel-ID, dated-imagery and capability-boundary design;
no client data, credentials or private CVP assets were copied.

## Pull request packaging

The review branch preserves the 3,146 existing `web/public` files (including
legacy map data and 3D tiles) in Git. The new Vite configuration sets
`publicDir: false` so these unused legacy assets are not copied into its build.
The replacement frontend removes obsolete source modules and old frontend test
configuration. Raw acquisitions, generated releases and local operational drafts
are not committed; the acquisition manifests and build recipe are included.
