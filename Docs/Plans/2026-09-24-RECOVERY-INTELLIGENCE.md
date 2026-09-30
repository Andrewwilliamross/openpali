# OpenPali recovery intelligence: implementation and research plan

September 24, 2026 · proposed technical direction following the
[CTO audit](../Research/2026-09-24-CTO-AUDIT.md)

This is a sequenced work program with acceptance criteria. It is not a claim
that these capabilities are implemented or that commercial data access exists.
The [source inventory](../Research/2026-09-24-SOURCE-INVENTORY.md) grounds the
available data, candidate providers and known gaps.

**Discovery update:** [verified data expansion](../Research/2026-09-24-DATA-EXPANSION.md)
records completed acquisition spikes, including 2026 assessments, the expanded
parcel cohort, private-cleanup evidence and primary inspection outcomes. Its
[visual program](../Research/2026-09-24-VISUAL-PROGRAM.md) and
[market spike](../Research/2026-09-24-MARKET-SPIKE.md) refine sections 3–4 below.
These datasets are staged; release-consistency and production integration work
remain open.

## Product outcome

A stakeholder should be able to answer: what is documented here, what can be
seen on dated imagery, what has changed in the market, what is happening nearby,
and how current and complete is each answer?

Keep distinct typed histories for:

| History | Examples | What it can establish |
|---|---|---|
| Agency records | Permit submitted, issued, inspection passed, CofO issued | Administrative assertions with specific project scope |
| Observed site | Debris removed, new footprint, roof appeared | Physical features visible within a capture interval |
| Market | Listing, asking-price change, recorded sale, transfer | Marketing and transaction events with their own effective/recording times |
| Community | Road access, school reopening, business return | Context at the published geographic unit |
| Estimates | Probability of a roof stage; conditional time to permit | A model output with version, uncertainty, validation domain and abstention |

A roof cannot establish occupancy authorization. A CofO cannot establish that
a displaced household has returned. A recorded mortgage cannot establish that
construction started. Preserve these distinctions in the database and API so
they survive future UI and agent changes.

## 1. Repair release consistency and observation history

**First implementation slice.** Finish the shared data contract before adding
new streams to a system that can mix revisions.

- Join property detail, bbox queries and MVT to the exact `parcel_version`
  members frozen in each snapshot. Define deterministic release IDs and
  immutable caches across geometry, evidence, metrics, imagery and models.
- Add one frontend `ReleaseContext`. Resolve the API release once, independently
  of the spatial capability probe. Fetch all application data through that
  context. Static fallback must be a complete, hash-checked compatible bundle
  with its own visible date; changing modes switches the whole context.
- Add a permits view to the API. Fetch property details on demand. Expose
  pagination completeness and errors; never present a truncated timeline as
  complete. Bind search, filters, totals and tiles to the same property universe.
- Model source assertions as revisions. Preserve raw versions and historical
  knowledge, but supersede derived assertions when a source corrects its value,
  date, subject or qualification. Absence from an incomplete page is not a
  deletion. Define removal semantics separately for each source.
- Make snapshot membership select exact source-record versions, not all rows
  belonging to source IDs before a cutoff. Policy changes need explicit
  re-derivation lineage. Audit v1→v2 before publishing the new county status.
- Commit failure records outside the rolled-back ingestion transaction; carry
  typed retryable failures through Prefect. Establish source-specific schedules
  and record acquisition time, upstream editing time, observed lag and last
  successful complete refresh separately.

**Acceptance:** a local integration scenario creates release A, revises a
parcel/permit, creates B, and proves every A endpoint remains identical.
It also exercises API outage during hydration, missing pages, source withdrawal,
rebuild-flag correction, new vocabulary and interrupted refresh. Promotion
requires explicit mandatory sources, complete pagination, expected count/join
ranges, compatible policy versions, and a freshness policy. Last-known-good
remains available with its original dates. Run the full service gate for this
slice; unit tests alone cannot verify PostGIS query semantics.

Retain the modular Python service and PostGIS/object storage. The existing
Prefect and MLflow installations can be retained if their operational costs
are justified. Additional microservices are unnecessary for the initial pilots.

## 2. Expand agency coverage and entity resolution

Start where missing fields could change thousands of misleadingly sparse
parcel histories without buying a new sensor.

1. Inspect actual County `FSO_URL`, `DEBRIS_REMOVAL_EPICLA` and
   `BUILD_PLAN_APPROVED` examples and dictionaries. Trace private cleanup
   sign-offs. Determine whether `DEBRIS_CLEARED=Yes` asserts a distinct event;
   its prevalent `NA` value must remain uninterpreted until documented.
2. Resolve an inspection-outcome path through LADBS record services, using a
   bounded set of known permits before building a connector. Verify completion,
   result, inspection type and date separately. Scheduling-only feeds remain
   activity signals.
3. Audit `Bldg-New` subtypes and project families: replacement dwelling, ADU,
   accessory work and multiple structures. Preserve permit amendments, parent
   cases, addresses and building links. A single APN milestone must disclose
   which project earned it.
4. Integrate DINS as structure evidence. Add all affected and nearby undamaged
   parcels as separate cohorts rather than redefining the destroyed cohort.
   Keep original incident and damage definitions. Create an unmatched/ambiguous
   join queue with explanations; do not silently pick a parcel near a boundary.
5. Build parcel split/merge lineage and stable property/building/project IDs.
   Normalize APNs at source boundaries while retaining original source keys.
   APNs are parcel references, not eternal building identities.

**Acceptance:** a stratified evidence audit covers each jurisdiction, each new
status, private cleanup, multiple-project parcels, ambiguous joins and source
corrections. Publish a coverage matrix by source × jurisdiction × evidence
type, match rates, omissions and examples. New counts require reconciled
units and filters; structure totals and parcel totals must never be equated.

## 3. Establish current imagery and a site-change benchmark

### Acquire the smallest useful archive first

Search existing EagleView/LARIAC, Nearmap, Planet and public catalogs before
requesting a new capture. Record scene footprints, capture intervals, native
and delivered resolution, off-nadir angle, cloud/shadow, processing level,
alignment quality, and display/analysis/training rights. An offered 50 cm
output pixel does not guarantee 50 cm native detail or framing visibility.
[SkySat documentation](https://docs.planet.com/data/imagery/skysat/)
and the [tasking interface](https://docs.planet.com/develop/apis/tasking/)
are discovery starting points, not proof of a deliverable Palisades scene.

Use STAC metadata, immutable raw objects and Cloud Optimized GeoTIFFs, with
tile rendering for the browser. Store world/pixel transforms and processing
lineage. Compare in a local projected coordinate system; do not compute area
in longitude/latitude degrees. Test raster registration with independent stable
road/terrain control features. Store vertical datum separately if using DSMs.
[STAC](https://stacspec.org/en/about/stac-spec/) provides the catalog contract.

**Pilot design:** initially 200–400 properties, 2–3 usable capture dates, sampled
across jurisdictions, topography, canopy, apparent progress, private cleanup,
and gaps. These are proposed pilot sizes, not a guarantee of statistical power.
Include unchanged and undamaged controls. Increase the sample until individual
target classes have adequate independently reviewed examples; withhold rare
classes from public prediction when they do not.

Use a feature ontology that annotators can actually see: debris/material piles,
cleared ground, excavation, slab/foundation, structural frame, roof, vegetation,
and occluded/unobservable. Keep separate masks and parcel/building summaries;
several classes can coexist on one property. Define “roof appeared between
capture A and B” as an interval, rather than assigning date B as construction
completion. Aerial imagery generally cannot settle interior completion.

### Model ladder and evaluation

First measure image co-registration error, seasonal/shadow differences and
human agreement. Compare simple registered image/feature differences, a
building segmentation baseline, and a pretrained two-date change model.
Use [TorchGeo](https://github.com/torchgeo/torchgeo) for geospatial datasets,
sampling and training; its [BTC models](https://docs.torchgeo.org/en/stable/api/models/btc.html)
are a concrete candidate for binary change. Binary change still needs a
separate validated stage classifier or segmenter. SpaceNet/LEVIR/xView2 can
bootstrap representations; their domains and labels do not substitute for
local reconstruction labels. The
[Be the Change paper](https://arxiv.org/abs/2507.03367) is a methods reference,
not a local accuracy claim.

Reserve whole street blocks and acquisition dates for evaluation. Keep all
chips of a property and adjacent overlapping image footprints in one split.
Use a held-out sensor or acquisition condition to measure domain shift when
possible. Measure event precision/recall, false changes per 100 properties,
stage confusion, spatial overlap, calibration and abstention coverage. Report
confidence intervals by block, not by correlated image chip. Evaluate dark
roofs, slopes, canopy, shadows and small sites separately.

Proposed public high-confidence-event gate: a lower 95% confidence bound on
precision of at least 0.90 for that event class, plus reported recall and
coverage. Treat this as a starting product requirement to validate against
error costs; if it cannot be demonstrated, publish reviewed examples and
coverage rather than unsupported automatic claims. Preserve model outputs
as estimates even when a reviewer accepts them. A small dual-review label
set and disagreement log must precede any performance claim.

Satellite foundation models are candidates only when their input resolution
and task match the problem. For example,
[Prithvi-EO-2.0](https://arxiv.org/abs/2412.02732) uses 30 m HLS pretraining;
pretraining scale does not create parcel-level framing detail absent from an
input image. Benchmark transfer on the actual local sensor, alongside simpler
models, before investing in adaptation.

### Tasking and field observations

Rank an acquisition by expected reduction in decision uncertainty, weighted
by stakeholder value, usable coverage and source lag, divided by total cost
(capture + license + processing + review). Prefer multi-parcel coverage and
capture diversity over repeatedly observing already-clear sites. Retain a
random sentinel sample and selection probabilities: targeting only uncertain
or rapidly changing areas would otherwise bias neighborhood trend estimates.

If archives leave a material gap, prepare a concrete tasking specification:
polygon, date window, required feature visibility, off-nadir/cloud limits,
revisit, usable-delivery criteria, rights and a quoted all-in cost. Only then
does a human need to choose a spend. No quote or tasking approval is required
to perform the preceding catalog and sample evaluation.

Resident/contractor photos can provide evidence under canopy or between flights.
Use consented upload, public/private visibility, time/location provenance and
review; retain a route to correct or withdraw submissions. Do not treat EXIF or
geolocation alone as proof. Public-space field capture or authorized drone
work is another targeted option after defining the evidence gap and permitted
collection conditions.

## 4. Add market and neighborhood intelligence

### Build an event ledger before a price score

Create separate listing, transaction, assessment and insurance-context tables.
Store provider/native record IDs, parcel/building links, effective time,
recording/publication time, first observed time, raw hash and permitted uses.

- **Listings:** lifecycle events, asking-price revisions, pending/closed/
  withdrawn states, marketing exposure, relisting linkage, lot vs standing vs
  rebuilt home, advertised floor area and source-attributed features. Avoid
  double-counting cross-listed or relisted inventory.
- **Transfers:** document type, record date, stated sale date, consideration,
  partial interest, multi-parcel allocation and arm's-length classification.
  Trust changes, gifts and intra-family transfers are not automatically sales.
  Avoid exposing unnecessary personal details in the public product.
- **Assessments:** roll year, land/improvement values, property attributes,
  reassessment and calamity changes. Taxable value is not market price.
- **Insurance:** begin with CDI's published aggregate policy/claims measures
  at their native geography. No parcel-level policy or payout inference from
  ZIP data. Consented household financial information belongs in a separate
  private product with clear access boundaries.

The public Assessor sales endpoint tested in the audit is only historical
context. Current listings require an actual MLS partner/license; RESO is the
transport standard. Compare licensed transaction vendors using 100 stratified
APNs, including known post-fire transfers, multi-parcel transactions and
non-sale changes. Measure coverage and publication lag against independently
checked records. Ask for event history, backfill and permitted derived outputs,
not just a current property snapshot.

**First useful output:** neighborhood inventory by property type, new/withdrawn/
closed listings, price reductions, transaction counts and coverage/lag. Display
small-sample suppression and uncertainty. Add prices only with a defensible
property-type and unit comparison; vacant lot price per square foot of land
cannot share an axis with rebuilt-home price per interior square foot.

### Test the neighbor effect instead of assuming it

Maintain both versioned neighborhood polygons and continuous spatial exposure:
adjacent properties, distance bands, street segments and construction access.
Record unknown observation coverage separately. A raw completed fraction with
unknown sites treated as zero confounds missing data with slow recovery.

An initial price model can use a partially pooled hedonic specification:

`log(price_it) = property_features_it · β + area_effect_i + month_effect_t
                 + γ · nearby_recovery_(i,t-lag) + error_it`

Fit vacant land and homes separately; account for lot size, view/slope, access,
building size/age, sale type, and inventory composition. Include nearby activity
with temporal lag so future construction cannot explain an earlier sale.
Backtest on held-out time blocks and neighborhoods, compare against simple
comparable-sale and area/month baselines, and show prediction intervals.

This estimates an association. Wealth, rebuilding intention, infrastructure,
financing and selection into sale can affect both recovery and prices. Nearby
construction could temporarily reduce amenity while later improving it.
Repeat-sales methods also need care: the post-fire asset may be a different
building or only land. A causal claim would need a separate identification
design with justified controls, pre-trends and spillover handling. Sparse data
should produce descriptive evidence and wide intervals, not a precise multiplier.

Broaden community measures beyond price: road/utility availability, school and
business reopening, building completion and consented reports of household
return. Rising prices alone are not a complete recovery outcome.

## 5. Make forecasting an empirical program

Separate two targets: *what is visible/known now* and *what might happen next*.
Keep current-state estimation independent of the legal evidence flags.

For future milestone timing, define the unit (project or building), origin
(e.g. submission), event, censoring and competing outcomes before choosing a
model. Withdrawal, redesign or expiration may change the project process;
selling a property does not by itself end rebuilding. Calendar and jurisdiction
effects matter, and observation delay differs by source.

Repair the evaluation helpers first. Require a supported horizon and censoring
distribution; return a typed unavailable result when support is absent. Estimate
calibration with censoring-aware methods under stated assumptions and compare
with mature-cohort estimates. Do not drop early-censored cases and call the
remaining success fraction full-cohort calibration.

Reconstruct features as they were known at each training origin. Truncate
training outcomes at that origin, then use later data only to evaluate the
frozen prediction. Execute multiple forward folds. Keep properties/project
families and relevant spatial groups together. Evaluate 30/90/180-day targets
only when the test cohort has sufficient follow-up for that horizon; a recent
60-day submission window cannot validate a 180-day non-event outcome.

Use Kaplan–Meier/appropriate competing-risk summaries as descriptive baselines,
then Cox or a discrete-time hazard model. Add nonlinear survival boosting only
if it wins on held-out calibration, scoring, subgroup coverage and useful
decision thresholds. Report uncertainty using resampling that respects project
and spatial dependence. Record immutable data/code/config/model hashes and
independent promotion evidence. Fit no public forecast solely to a synthetic
drill, and never use a fixture win as an empirical result.

For multi-source site-state estimation, a later semi-Markov model could estimate
`P(state at t | observations known by t)` while representing stage duration and
source-specific detection delays. Administrative, physical and market events
should remain distinct. Correlated permit mirrors cannot be multiplied as
independent evidence. Missingness, source sensitivity and transition rates
require labels or identifiable assumptions; model complexity cannot resolve
an unidentifiable observation process. Start with reviewed observations and
intervals, then compare this approach against simpler calibrated classifiers.

## 6. Adopt COSS and redesign the evidence workflow

[COSS UI](https://coss.com/ui/docs/get-started) uses Base UI and Tailwind CSS.
Add its components and tokens to the existing React/Vite application, with
source ownership and focused adaptations. A framework migration is not needed.

| User task | Proposed interface | COSS building blocks |
|---|---|---|
| Find an address or APN | Keyboard-accessible search with clear match/location context | Combobox, Input, Button |
| Understand one property | Responsive property panel with Public records, Site observations, Market, Nearby | Sheet, Tabs, Badge, Separator |
| Inspect a claim | Source, event date or interval, retrieval date, underlying document/image and uncertainty | Table, Tooltip, Alert, Dialog |
| Compare areas | Explicit metric, cohort, period, coverage and denominator; linked map/table | Select, Toggle Group, Table, Skeleton |
| Compare imagery | Synchronized dated swipe with capture metadata and missing-coverage state | Slider, Button, Tooltip |
| Correct evidence | Structured correction and optional private contact fields | Field, Input, Textarea, Checkbox, Alert |

Set typography, spacing, color, focus and motion tokens once. Replace the
ordinary controls and property workflows before restyling complex WebGL code.
Use source freshness and capture dates near the relevant claim. Label agency
milestones and inferred observations explicitly. Provide text/pattern cues
alongside color, adequate contrast, reduced-motion behavior and a useful table
alternative to the map. Avoid a single recovery score that conceals coverage.

**Acceptance:** mobile and desktop flows for address/APN search, map selection,
shareable property URL, source inspection, imagery comparison, complete/static
fallback and correction submission; keyboard/focus/error-state checks; no
mixed-release renders. Measure actual cold-load transfer, parse time and memory
before setting performance budgets. Load property data and optional 3D on demand.

## Reuse from CVP

CVP's useful contributions are specific contracts and working evidence plumbing.
Local review used `Client_Code/CVP.nosync` at commit
`d5be08e2ae600ce392ee0243beb69002269a29be`; no CVP files were changed.

| CVP location | Reuse in OpenPali | Adaptation boundary |
|---|---|---|
| `Docs/contracts/ParcelFeatureIdContract-v1.md` | Stable opaque feature IDs through database, tiles, `promoteId` and selection | Preserve LA APN normalization at ingestion; do not copy Ohio parcel rules |
| `Docs/contracts/ParcelMapContracts-v1.md` | Match geometry generation, projection generation, manifest census and viewport completeness | Freeze these to OpenPali release membership and evidence policies |
| `api.spring-ai.xyz/src/services/parcel_imagery.py` | `ParcelAerialEvidence/v2`, immutable image/source descriptors, capture-date basis, overview and neighborhood frames, explicit fallback reason | Replace county/provider configuration; preserve original provenance |
| `api.spring-ai.xyz/src/services/aerial_imagery.py` and `county_imagery.py` | Source catalogs, scene selection, full-frame coverage checks, bounded acquisition and content hashes | Add LA catalogs and analytical raster assets, not only screenshots |
| `app.spring-ai.xyz/src/lib/maps/county-imagery.provenance.ts`, `imagery-gateway.ts`, `imagery-capability.ts` | Typed fallback/capture metadata, bounded responses and capability-controlled vendor access | Use OpenPali deployment/auth and source contracts |
| `api.spring-ai.xyz/src/graphs/land_research/` | Versioned checkpoints, bounded research loops and retained evidence state | Adapt a narrow operator research workflow; external actions retain explicit controls |

Port one tested contract at a time with small fixtures demonstrating parity.
Do not copy client data, credentials, commercial entitlement assumptions,
opportunity scores or unrelated services. CVP is not a drop-in recovery model.

## Agent capabilities worth building

1. **Source investigator:** detect schema/status changes; retrieve bounded
   official examples and documentation; propose a mapping with evidence and
   tests. Unknown terms stay quarantined until the interpretation is established.
2. **Parcel researcher:** assemble source-linked agency records, dated imagery
   and market events for one property; report conflicting claims and missing
   coverage. Every extracted claim needs a document span or image region.
3. **Observation planner:** identify where an archive query, a record request,
   or a reviewed photo would resolve a consequential uncertainty. Produce a
   costed acquisition proposal and retain a representative sentinel sample.
4. **Release auditor:** compare releases, explain count deltas as source changes,
   corrections, entity joins or policy revisions, and produce a review queue.

Persist tool inputs/results, provenance and checkpoints; bound requests and
spend; use idempotent operations. An agent's prose is a research artifact, not
an authoritative parcel observation. Evaluate claim support, extraction error,
abstention, duplicate work, coverage gained and cost per resolved case.

## Sequence, decision points and operating measures

| Order | Concrete deliverable | Exit condition |
|---|---|---|
| A | Release/supersession repair and diagnostic UI | Frozen A/B replay and failure scenarios pass full service gate |
| B | Fresh civic candidate plus coverage report | Complete source acquisition; reviewed semantic and count deltas; rollback demonstrated |
| C | COSS property workflow and imagery catalog | One consistent release; capture/source metadata and accessible core flows |
| D | Imagery benchmark and market-provider sample evaluation | Local labels and measured accuracy; transaction/listing coverage and lag measured |
| E | Reviewed physical changes and descriptive market/neighborhood dashboards | Evidence-backed outputs with coverage and type-specific denominators |
| F | Forecasts and richer state/market models | Supported horizons, reproducible historical evaluation and calibrated uncertainty |

B–D can overlap once their contracts are stable. A new satellite capture,
commercial data subscription, production publication or expanded household
product requires a concrete choice with cost, scope and expected value. Prepare
the sample results and specifications first so human judgment is grounded.
There is no evidence here for a credible delivery date or dollar budget yet.

Track: fresh-source fraction; source-to-publication lag; unmatched/ambiguous
record share; percentage of properties with recently *observable* imagery;
reviewed changes per acquisition; event precision/recall and abstention;
market-event coverage and recording lag; unsupported/suppressed metrics;
map/search/detail consistency; cold-load performance; and cost per useful
observation. The success criterion is a more complete and demonstrably accurate
recovery picture that stakeholders can inspect and act on.
