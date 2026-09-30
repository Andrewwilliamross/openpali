# OpenPali: verified data expansion and implementation decisions

September 24, 2026, Los Angeles. Acquisitions continued September 25 UTC.

This follow-up supersedes the initial audit's availability conclusions about
2026 assessor records, detailed inspection outcomes, and market research.
It separates **data already driving the old application**, **new evidence
acquired into local staging**, and **proposed capabilities**. No new production
release, price model, contractor ranking, or current visual classifier has been
published. The workspace's externally removed frontend was left untouched.

## 1. What we had, and what we now have locally

| Dataset | Shape, in plain language | Verified state | What a homeowner could use it for |
|---|---|---|---|
| Existing recovery bundle | Parcel polygons, property attributes, dated/status rows for permits and cleanup | July 12 bundle: **5,877 destroyed parcels**, not every Palisades property. 5,033 linked permits on 1,714 parcels; all permit valuations null. | See documented recovery steps, with the evidence date and project scope. It cannot currently value a vacant lot. |
| Expanded parcel inventory | **8,931 polygons**, each with a parcel number, address, use, building attributes and assessment fields | Fully acquired all property types whose County situs ZIP begins 90272. **8,905 have roll year 2026**, 26 have no roll year. [Acquisition report](2026-09-24-parcel-universe.json). | Include standing homes, commercial/institutional properties and comparison parcels in neighborhood and market analyses. |
| Detailed assessor histories | JSON tables: one current property record, multiple assessment/bill rows, multiple recorded ownership-event rows, parcel changes | All five public endpoints succeeded for four sample parcels. The first three contain **160 assessment-history rows and 26 ownership-event rows**. [Three-parcel report](2026-09-24-assessor-portal.json), [fourth sample](2026-09-24-assessor-standing-sample.json). | Explain the property's pre-fire characteristics, reassessments, possible construction changes and transfer history. Distinguish asking price, recorded transaction evidence and taxable value. |
| Cleanup documents | A URL index plus PDF forms; some include photographs, signatures and checklists | Full 5,877-row inventory: **4,289 unique linked PDFs**. Downloaded a stratified 12-document sample, all successfully. [Report](2026-09-24-clearance-inventory.json). | See what was documented on the site, which features remained and when a particular clearance was signed. |
| Detailed LADBS permit/inspection record | Web page with six tables and property/project fields | One primary-source browser extraction: **34 inspection outcomes, 9 clearances and 6 application-history entries**. A reusable DOM extractor and validation tests were added. [Report](2026-09-24-pcis-browser.json). | Understand foundation/framing approvals, correction cycles, named professional roles and outstanding dependencies. |
| Market research samples | Live listing pages and dated listing/sale tables | Redfin live browser access succeeded, including five dated events. Zillow live listing access succeeded; its history sections reported unavailable, although the search service returned an indexed history. [Market spike](2026-09-24-MARKET-SPIKE.md). | Track asking-price reductions, pending transitions, historical sales and comparable properties. Search-index history alone is not a dependable current feed. |
| Utility context | Pipe lines on a map, asset attributes, plan references; power rebuilding maps/schedules in PDFs | Sewer/storm service schemas and bounded queries succeeded. A 50 m query near 677 Via de la Paz returned **four sewer segments** with installation-year/material/plan fields. [Context probe](2026-09-24-context-probes.json). | Identify infrastructure and planned works relevant to a rebuild; link a clearance to its engineering context. Nearby geometry alone does not prove a property's connection or available capacity. |
| Post-fire LiDAR | Millions of measured 3D points per tile, with ground/noise classes and intensity | Official catalog: **541 tiles**, approximately **11.55 billion cataloged points**, from the January 21, 2025 flight. Downloaded one 20.1-million-point tile and produced a **52,808-point parcel/context crop** and 3D preview. [Visual evidence](2026-09-24-visual-baseline.json). | Establish a measured post-fire terrain/site baseline and compare later surveyed surfaces. This is historical geometry, not a 2026 site observation or a ready-made building-label dataset. |

The ZIP inventory overlaps 4,654 of the destroyed parcels. It adds **4,277
parcels absent from that dataset**; 1,223 destroyed parcels fall outside this
ZIP cohort. Their union is 10,154 parcel IDs. Neither membership outside the
destroyed dataset nor a positive assessed building value proves an undamaged
house. Join structure-level DINS and dated observations before assigning damage.

ZIP, neighborhood, fire perimeter, agency jurisdiction and valuation comparison
area will be separate, versioned memberships. The broad study rectangle used in
probes also covers surrounding communities. Its counts are not Palisades totals.
The exact neighborhood census remains to be reconciled against a named boundary
and parcels without postal addresses.

## 2. Property history: substantially more than a tax number

The [County parcel service](https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0)
provides bulk polygons and 2026 roll fields. The
[Assessor portal](https://portal.assessor.lacounty.gov/parceldetail/4412013017)
provides richer histories through these public JSON routes, with `ain=4412013017`:

- `/api/parceldetail`: property/lot dimensions, usable lot area, use, building
  quality, year built/effective year, beds/baths, current and preparation values,
  assessor neighborhood cluster, zoning and recorded sewer/view/site flags.
- `/api/parcel_ownershiphistory`: recording dates, document numbers, transfer
  categories, reassessment flags, parcel-count/interest fields and a
  documentary-transfer-tax-derived sale-price field (`DTTSalePrice`).
- `/api/parcel_assessmenthistory`: annual, corrected, supplemental and preparation
  rows with land/improvement values, reason codes, valuation dates and
  construction-date/type fields.
- `/api/parcel_parcelchange`: parcel-change history when supplied.
- `/api/pdbdate`: the upstream effective date, **September 11, 2026** in these samples.

These are fielded tables, not scanned deeds. The sampled ownership API does not
provide owner names or establish current legal title. It gives document keys for
subsequent deed retrieval. Tax assessments do not measure current market price,
and assessment histories do not prove tax payment or delinquency resolution.

**Observed traps now accounted for in discovery code:**

- Current roll is 2026 while preparation is already 2027. Taking the maximum
  year would mislabel a draft/preparation value as the latest completed roll.
- One parcel has several bill rows in a year. Keeping only the first row loses
  corrections and changes.
- `NewConstructionDate="0"` is common; it is not a renovation. Repeated genuine
  dates across assessment rows are not separate construction projects.
- An ownership row contains `02/45/1967`, an impossible date. Preserve the raw
  value and flag it; do not silently manufacture a replacement date.
- Trust transfers and file corrections can have tiny/sentinel price values.
  A transfer event is not necessarily an arm's-length sale.

**Application proposal:** a property-history timeline with separate transaction,
assessment, renovation/permit and physical-observation tracks. Join old permits,
deed documents, historic roll snapshots and pre-fire imagery by parcel lineage,
address and dates. A lot valuation can then account for usable area, slope/view,
prior improvements, access and actual entitlements instead of just total area.
Every inferred renovation needs corroboration and an explicit source.

## 3. Cleanup: preserve evidence and close the gaps

The County source's `FSO_URL` links do not all represent the same document class:

| County ROE status | Parcels | Linked PDF URLs |
|---|---:|---:|
| Final Sign Off – Complete | 3,964 | 3,964 |
| Opt-Out and Manage Cleanup Independently | 1,590 | 252 |
| FEMA Ineligible | 38 | 27 |
| No ROE | 256 | 21 |
| Final Sign Off – Ineligible | 24 | 24 |
| Non-responsive Opt-out | 5 | 1 |

Sample PDFs range from **1–9 pages**. A verified seven-page packet contains a
site checklist, signatures, a separate County sign-off stamp and six ground
photographs. Checklist topics include foundations, utility capping, grading,
erosion measures, retained features and remaining work. A sampled private
opt-out packet is explicitly a **withdrawal form** with many items marked NA;
it does not prove the private contractor cleared the site. The 12-document
sample contains three documents mentioning withdrawal. This convenience sample
does not estimate the prevalence of document classes across all PDFs.

Separately, `DEBRIS_REMOVAL_EPICLA` contains **1,489 “Finaled” rows**, including
**1,441 of the 1,590 private opt-out parcels**. The initial two-row probe missed
this. Store the permit status now; verify its underlying case/scope/date before
converting it into a physical cleanup milestone. Government ROE status, EPICLA
status and a photograph are three distinct observations that may disagree.

**Extraction:** classify document type first; then OCR/layout extraction of
checkboxes, signatures, date stamps and page references; extract photographs
with document/page provenance. Text alone missed a stamp in a rendered example.
Capture dates for embedded photographs remain uncertain unless metadata or
another document establishes them. Clearance does not automatically certify
soil safety or utilities being ready for service.

**Acquisition queue:** missing evidence becomes a work item with a next source,
not a negative fact. The [field candidate list](2026-09-24-field-acquisition-queue.json)
contains 20 examples from **91 ZIP-90272 private-cleanup parcels** with neither
an FSO URL nor an EPICLA status beyond “No Data.” It is a coverage queue, not an
accusation that these lots remain uncleared or an optimized driving itinerary.
Check newer permit/document/imagery evidence first; unresolved sites become
targeted public-frontage photography requests. Each capture should establish
date, location, viewing direction, visible coverage and occluded areas.

## 4. Permits and inspections: build the context graph

The [primary LADBS example](https://www.ladbsservices2.lacity.org/OnlineServices/PermitReport/PcisPermitDetail?id1=25010&id2=10000&id3=03188)
is a replacement dwelling at 1201 N Villa Woods Drive. Direct HTTP returned 403;
normal browser navigation succeeded without a challenge. Its tables supply:

- Project description, permit/job ID, dwelling type and occupancy-certificate status.
- Application submission, reviewer assignment, correction, approval and issue dates.
- Sewer, drainage, hydrant/access, hillside, parkway-tree, grading and stormwater
  clearances with dates and reviewer names.
- Contractor/engineer roles, including an engineer license identifier.
- Inspection type, date, result and inspector. Of 34 rows: 9 approved,
  5 partially approved, 3 conditionally approved, 6 corrections, 9 not ready,
  and 2 no-access outcomes.

For example, the record distinguishes a July 29 conditional framing approval
from an August 19 full approval. Neither supplies the framer's actual start
date. Preserve that distinction in both recovery estimates and contractor metrics.

**Enrichment graph to implement:**

`parcel → building → rebuild project → permit/amendment → inspection/clearance`

Attach professional role assignments, reviewer/department, dated site images,
engineering report sections, zoning/precedent decisions, agency plan sheets and
utility work orders. Match documents by permit/case/plan ID first, then parcel,
address and geometry with review of ambiguous matches. Document retrieval must
preserve revision and sheet/page identity; a superseded structural drawing must
not describe today's approved design.

Engineering and geotechnical documents add soil/foundation assumptions, slope,
retaining-wall requirements and special inspections. City engineering
[geotechnical-report guidance](https://projectdeliverymanual.engineering.lacity.gov/chapter-8-design-phase/84-geotechnical-report)
establishes the document family, but access to a particular project's report
still requires a successful case/document lookup. This research did not acquire
a full structural or geotechnical packet for the sample dwelling.

For costs and logistics, the public BLS API successfully returned the lumber
producer-price series through August 2026. It is a **monthly index**, not a local
supplier quote or price per board. Join industry indices at their published
vintages, then add dated contractor quotes, bills of material, delivery estimates,
road restrictions, utility outages and actual work logs. Separate applicant
response time, agency review time, inspection scheduling and trade work time;
elapsed permit duration alone cannot identify the cause of a delay.

## 5. PaliPost and legacy systems

[PaliPost](https://map.palipost.com/) is a concrete benchmark. Its browser-facing
`/api/parcels` returned **1,968 APN-keyed records** with primary permit IDs,
project type, PCIS-derived event history, refresh dates and estimates. Its map
geometry contains 5,622 features, while `/api/stats` uses a denominator of 4,109.
Those are different cohorts; comparing its headline counts with our destroyed
parcels would be misleading without reconciliation.

Its application distinguishes primary dwellings, ADUs, accessory work and repairs.
We should match its source coverage and improve evidence inspection, project
resolution and model evaluation. Its observed estimate configuration uses small
completed-stage samples and heuristic adjustments; those are not validation of
forecast accuracy. Publicly delivered JavaScript/JSON also does not establish an
open-source code or redistribution license. Use primary agency sources for our
reproducible ingestion. No PaliPost scrape-triggering POST was invoked.

**Deterministic workflow design:**

1. Prefer ordinary public JSON/ArcGIS routes when available, as the assessor
   discovery demonstrates. Retain raw bytes, parameters, effective dates and hashes.
2. For browser-only records: permit/APN work queue → normal navigation → wait
   for the expected record identifier → semantic section/table extraction →
   schema and identifier checks → immutable capture → normalized events.
3. Quarantine missing sections, ambiguous identities, access blocks and changed
   table widths. They are acquisition failures, not empty parcel histories.
4. An agent diagnoses changed layouts using a captured page, proposes a new
   deterministic extraction recipe, and runs fixtures/canary records before the
   recipe is promoted. Keep per-host concurrency, backoff, incremental refresh,
   completeness checks and change alerts explicit.
5. Keep event time, upstream effective time and our observation time separate.
   Repeated snapshots are required to measure discovery lag.

The [Etchplan documentation](https://github.com/Egoist-Machines/etchplan/tree/main/docs)
provides a useful trace-to-recipe, validation and drift/fallback design.
[ego-lite](https://github.com/citrolabs/ego-lite) is useful for local browser access.
Neither was installed or treated as a proven production feed. Our current PCIS
adapter was exercised against one live page and tested against failure cases;
multi-case discovery, recovery, scheduling and sustained reliability remain work.

## 6. Utilities and prevention are a first-class workstream

Store **assets**, **observations**, **work orders**, **plans**, **dependencies** and
**service conditions** separately. A line drawn on a map is not telemetry.

| Vertical | Data shape and acquisition path | Useful outputs |
|---|---|---|
| Sewer | [City GIS](https://maps.lacity.org/lahub/rest/services/Sewer_Information/MapServer): pipe lines, structures/laterals, material, installation year, slope/elevation, plan references; a permit-image layer also exists | Site servicing context, lateral/clearance investigation and aging-asset questions. Four segments near the sample parcel include source installation years 1935 and 2014. |
| Stormwater | [City GIS](https://maps.lacity.org/lahub/rest/services/Stormwater_Information/MapServer): pipes, inlets, catchments, flood layers, design/capacity fields | Identify drainage constraints after grading and vegetation loss; join terrain, rain and burn/fuel changes. Null fields remain unknown. Its FEMA “Water Line” layer must not be mislabeled as drinking-water mains. |
| Drinking water | [Water-restoration records](https://www.ladwp.com/who-we-are/water-system/water-quality/water-quality-restoration-pacific-palisades), sampling/advisory maps, public plans/maintenance/board records; property pressure checks and owner service records | Distinguish water-quality clearance, site hookup and pressure/flow capability. A bulk live local pressure/tank/pump feed has not been acquired. Specify the missing measurements and pursue agency records, instrumentation or consented measurements. |
| Electricity | [LADWP March 2026 plan](https://www.ladwp.com/sites/default/files/2026-03/Master%20Schedule%20Presentation%20for%20PPCC_3.26.2026_FINAL_web.pdf), mapped undergrounding scope, project schedules; service-installation tracker | Explain temporary versus permanent service and planned street works. The plan gives Alphabets conduit work a Q1 2027–Q1 2028 target; that is a dated planning target, not completed work or a promise that a specific home must wait. |
| Gas | [CPUC leak-abatement program](https://www.cpuc.ca.gov/about-cpuc/divisions/safety-policy-division/risk-assessment-and-safety-analytics/natural-gas-leak-abatement), inspection/incident reports, utility restoration and customer service records | Understand capping, inspection and restoration evidence. Parcel-level coverage still needs verification; aggregate leak reports cannot identify an individual property's service state. |
| Fuel, roads and civic services | Brush-inspection records, vegetation/terrain measurements, weather, street/access closures, public works schedules, school/business reopening evidence | Detect overlapping access, weather, vegetation and infrastructure constraints. Authenticate owner-only brush records through consent; generate missing physical observations from lawful field/survey acquisition. |

**Research question:** which interventions reduce expected harm under plausible
wind, fire, demand and infrastructure-failure scenarios? A hydraulic simulation
requires topology, pipe/pump properties, tank levels, demands and calibration;
GIS geometry alone cannot answer it. Add power dependencies, weather/fuel state
and accessibility, and backtest event scenarios with only information available
before each event. Evaluate missed events, false alarms, warning lead time and
whether a proposed intervention is feasible.

The [state water-supply analysis](https://water.ca.gov/-/media/CNRA-Website/Files/NewsRoom/Educational-Portal/19Nov2025PalisadesFireWaterSupply.pdf)
finds both an empty Santa Ynez Reservoir and severe flow/pressure constraints;
it says a full reservoir would not have prevented the system being overwhelmed.
This supports explicitly modeling storage, delivery capacity and demand. It
does not establish that an AI system could have prevented this fire, nor a
single-cause explanation of its losses. Keep competing hypotheses testable.

## 7. Valuation, visual inference and professional performance

- **Vacant-lot valuation:** use confirmed transaction evidence, listing episodes,
  usable area, slope/view/access, entitlements, existing infrastructure and
  surrounding recovery. Start with comparable-sales and interpretable models;
  benchmark a learned model against those baselines. Predict a range and show
  supporting comparables and observation dates.
- **Standing-home neighborhood effects:** build time-varying exposure measures
  for adjacent and nearby vacant, active-construction and rebuilt sites. Include
  shared boundaries, distance, street context and measured visibility. Separate
  existing homes, new builds and vacant land. Learn a price association first;
  a causal discount requires a credible comparison design, pre-trend checks and
  adjustment for selection into sale, fire severity and neighborhood differences.
- **Validation:** hold out later sales and entire spatial blocks; keep repeat
  listings, the same parcel and adjacent correlated observations out of both
  train and test. No current permits or later photos may leak into a historical
  sale prediction. Report errors in dollars and percent, interval coverage,
  cohort sample sizes and geography-specific failures. A model trained on sold
  properties is conditional on sale, not automatically representative of every lot.
- **Visual inference:** implement the [multimodal plan](2026-09-24-VISUAL-PROGRAM.md).
  Predict observable physical components with confidence and source references;
  do not collapse agency authorization, visible structures and occupancy into a
  single linear score. Use uncertainty to select the next acquisition.
- **Professional claims:** allow a company/person to claim a **role on a project
  and scope of work**, not exclusive ownership of a parcel. Verify against
  license/permit evidence and owner or project confirmation. Multiple companies,
  trades and changing assignments must coexist. Record disputed and withdrawn
  claims and distinguish self-reported from independently supported dates.
- **Performance:** framing days per square foot can be a displayed descriptor,
  but comparisons need project size/complexity, slope, structural system,
  starting conditions, dependencies, crew/work-log evidence and quality/rework.
  Use a hierarchical duration model with partial pooling and censoring for
  unfinished projects; show adjusted duration, sample size and uncertainty.
  No public winner should be inferred from two projects or an inspection gap.
  Architectural review, trade work and agent marketing require different outcomes.

## 8. Delivery sequence and what remains

1. **Completed research slice:** complete County PDF-link census, 12-PDF sample,
   complete ZIP parcel cohort, current assessor-history collector, live PCIS
   extraction, market-page verification, utility/material probes, visual catalog
   discovery and a concrete field-acquisition queue. Raw files are local under
   ignored `data/raw/`; machine-readable proof reports are in this directory.
2. **Next integration:** fix release/source-version consistency identified in
   the original audit, add these staging contracts to the evidence ledger, and
   preserve separate project/structure/parcel identities. Refresh the application
   only through a verified complete release. Sampling success is not a fleet-wide
   reliability measurement.
3. **Coverage expansion:** exact neighborhood boundary and reference cohorts;
   stratified PCIS cases and engineering attachments; document classification;
   market listing-episode collector; deeper water/power/gas acquisition. Test
   coverage across city/county/Malibu, private cleanup and multi-project parcels.
4. **Owned observations:** resolve the queue with imagery first, then schedule
   standardized field/oblique survey capture for persistent gaps. No paid
   satellite order or field visit has been commissioned.
5. **Models and product:** measured visual benchmark, spatially and temporally
   held-out price/duration baselines, evidence timelines and verified role claims.
   Preserve the requested coss component direction in the frontend rebuild;
   this source-research slice does not implement that interface.

Reuse CVP's inspected parcel/feature ID contracts, imagery provenance and
capability/fallback patterns. Adapt implementations with clear dependency
boundaries; do not copy client records or credentials. TorchGeo supplies useful
geospatial dataset/sampler infrastructure; it does not supply validated Palisades
rebuild or property-value predictions out of the box.

For the open dataset, publish reproducible collectors, schemas, provenance,
coverage and permissible evidence/derived releases. Track source-specific reuse
rights and redaction at acquisition. Public listing access does not itself grant
redistribution rights to every photograph or full listing. This is a release
design issue; it does not stop investigation or construction of primary-source feeds.

### Reproduce the implemented collectors

From the repository root:

```sh
pipeline/.venv/bin/python pipeline/openpali/discovery/clearance.py --sample 12 --report Docs/Research/2026-09-24-clearance-inventory.json
PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.discovery.parcel_universe --report Docs/Research/2026-09-24-parcel-universe.json
PYTHONPATH=pipeline pipeline/.venv/bin/python -m openpali.discovery.assessor --ain 4412013017 --report Docs/Research/2026-09-24-assessor-portal.json
node --test scripts/pcis-extract.test.mjs
```

Use a new report name to preserve an earlier research manifest. Collectors write
timestamped raw runs, fail on incomplete/mismatched identities and do not alter
production state. The browser adapter in `scripts/pcis-extract.mjs` accepts an
already-open Playwright page (or CUA's `Tab.playwright`) and validates its permit ID.

### Verification completed

- Python pipeline suite: **179 passed, 16 skipped**; skipped integration gates were not exercised.
- PCIS parser: **3 Node tests passed**, plus validation of the captured live-page tables.
- All 8,931 parcel geometries are nonempty, valid polygons/multipolygons with positive area.
- The full LiDAR tile was read and the saved 52,808-point crop was reopened successfully; its PNG preview was inspected.
- Research JSON and discovery Python parse; `git diff --check` is clean.
- Frontend validation was not performed: the `web/` directory is absent in the current externally changed workspace.
