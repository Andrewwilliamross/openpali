# OpenPali source inventory — September 24, 2026

**Follow-up:** [verified data expansion](2026-09-24-DATA-EXPANSION.md) supersedes
initial availability conclusions below. We acquired 8,931 all-type ZIP-90272
parcels (8,905 with 2026 roll data), current assessor histories, a complete
clearance-link inventory, 12 PDFs, and a primary PCIS inspection sample. Live
market-page access and public classified LiDAR were also verified. The older
PAIS sales endpoint's stale dates do not apply to these other assessor routes.

This inventory distinguishes bundled observations, implemented connectors, and
candidate sources. A working endpoint establishes access and schema; it does
not establish completeness, a service commitment, or rights to every use.
Probe timestamps are UTC (September 25); the audit date is September 24 in Los Angeles.

Evidence: [bundle profile](2026-09-24-bundle-audit.json),
[live civic probes](2026-09-24-source-probes.json), and
[Assessor sales probes](2026-09-24-assessor-probe.json). The civic probes
record request parameters, response hashes, metadata, and aggregate results.
They do not ingest new parcel records into the application.

## Civic sources already in the code

| Source and role | Bundled July 12 data | September probe | Interpretation and gap |
|---|---:|---:|---|
| [County debris parcels](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Parcels_Debris_Removal_Public/FeatureServer/0): parcel universe, boundaries, pre-fire attributes, cleanup, county progress | 5,877 parcels | 5,877 with the identical destroyed-Palisades filter | A parcel universe drawn from a debris program. It excludes damaged-but-standing properties and does not count homes, households, or buildings. |
| [LADBS recovery permits](https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/LADBS_WF_Fire_Data_Palisades_Recovery_Area/FeatureServer/0): application, review, issue, CofO events | 5,331 source rows; 5,033 attached permits on 1,714 parcels; 1,126 qualifying applications | 6,485 source rows; 2,250 flagged `Rebuild` across all permit types | A flag alone does not identify a replacement home. Existing qualification requires `Bldg-New` AND `Rebuild`. Multiple permits can describe one project. Counts of permits and counts of parcels differ. |
| [LADBS inspections](https://services5.arcgis.com/7nsPwEMP38bSkCjy/ArcGIS/rest/services/LADBS_WF_Inspection_Data_tbl_Palisades_Recovery_Area/FeatureServer/0): inspection activity joined through permit number | Static path used [LAHub MapServer/4](https://maps.lacity.org/lahub/rest/services/WildfireRecovery/MapServer/4), 1,014 rows; 904 attached; 110 orphaned | Canonical connector has 1,024 rows, **all `Insp Scheduled`** | No passed, failed, or completed outcomes in this source. Comparing the two endpoint counts requires checking equivalence. The static metadata calls this `inspections`, while observations call it `ladbs_inspections`. |
| [Malibu dashboard markers](https://mlb-pptsrv.ci.malibu.ca.us/Home/GetProjectDashMarkers?sFireView=PalisadesRebuildStatsDetailWithBPComplete): coarse local progress | 269 markers; 265 joined | 288 markers | Undocumented dashboard JSON. Icon categories carry limited state; no event chronology. This is an official municipal host, but the internal endpoint is not a documented data contract. |
| [CAL FIRE DINS](https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0): structure identity and damage | No DINS observations in the static bundle | 12,137 Palisades structure assessments; 6,845 destroyed, 4,261 no damage, 732 affected, 171 minor, 72 major, 56 inaccessible | Implemented in `openpali/`; does not drive the bundled frontend. Structures are not parcels. APN match followed by point-in-polygon; unmatched and ambiguous counts are tracked. |
| [Socrata building permits](https://data.lacity.org/resource/gwh9-jnip.json): reconciliation / portal links | Presence lookup found 4,181 of 5,033 requested permit numbers | Canonical bbox/post-fire-submission query: 11,588 records | Static path checks links. Canonical path stores records for named reconciliation; does not create milestone observations. This is another view of city permit records, not necessarily independent evidence of physical work. |
| [Socrata CofO](https://data.lacity.org/resource/3f9m-afei.json): reconciliation | Not included as its own static source | 18,707 since-fire records **citywide** | Requires APN/permit/project and geography qualification before comparing with the 27 bundled parcels. A citywide count is not a Palisades recovery denominator. |

All seven configured civic adapters responded successfully to the bounded
metadata/count probes. All configured fields checked against ArcGIS/Socrata
metadata were present. This does not prove a full paginated refresh will pass.

### Exact fields and their uses

The authoritative implemented selections are in
[`adapters/registry.py`](../../pipeline/openpali/adapters/registry.py).
The static acquisition path is in
[`palisades/sources.py`](../../pipeline/palisades/sources.py).

| Source | Fields consumed | Where they go |
|---|---|---|
| County identity/location | `APN`, `AIN`, `SITUSFULLADDRESS`, `SITUSADDRESS`, `SITUSZIP`, `CENTER_LAT`, `CENTER_LON`, `LCITY`, `COMMUNITY`, polygon geometry | APN normalization, jurisdiction, display address, map, nearest-center neighborhood. Not every selected field becomes a public field. |
| County pre-fire context | `STRUCTURECATEGORY`, `USETYPE`, `USEDESCRIPTION`, `YEARBUILT1`, `SQFTMAIN1`, `BEDROOMS1`, `BATHROOMS1`, `UNITS1`, `TOTAL_UNITS` | Property card, struct/type and units in static path; parcel version in ledger. These are assessor-like attributes, not observed current construction. |
| County recovery | `DAMAGE`, `ROE_STATUS`, `DEBRIS_CLEARED`, `FSO_PKG_APPROVED_USACE`, `REBUILD_PROGRESS` | Destruction interval; government sign-off; private opt-out context; coarse county milestones. `DEBRIS_CLEARED` is selected but does not currently yield a completion observation. |
| LADBS permits | `PERMIT`, `APN`, `ADDRESS`, `PERMIT_TYPE`, `PERMIT_SUBTYPE`, `TYPE`, `PERMIT_STATUS`, `PALISADES_WF_REBUILD` | Record identity, join, qualifying rebuild classification, raw context and card. `PERMIT_SUBTYPE` is fetched but not used to distinguish primary dwellings from other new-building work. |
| LADBS times | `SUBMIT_DATE`, `PC_APPROVED_DATE`, `ISSUE_DATE`, `COFO_DATE`, `STATUS_DATE` | Exact-date events when populated; status-derived bounded intervals in some cases. Missing times stay unknown. Future/source-inconsistent dates need explicit quarantine. |
| Inspection rows | `OBJECTID`, `PERMIT`, `INSP_DT`, `INSP_DESC`, `INSP_STATUS`, `ADDRESS` | Permit join and status interpretation. Scheduling dates are not inspection completion times. Construction relevance is inherited from permit qualification. |
| DINS | `OBJECTID`, `GLOBALID`, `INCIDENTNAME`, `INCIDENTNUM`, `INCIDENTSTARTDATE`, `DAMAGE`, `STRUCTURETYPE`, `STRUCTURECATEGORY`, `APN`, `SITEADDRESS`, `CITY`, `COUNTY`, `LATITUDE`, `LONGITUDE`, geometry | Structure records, damage observations, parcel links. DINS damage bands differ from County damage bands. |
| Socrata permits | `permit_nbr`, `apn`, `permit_type`, `permit_sub_type`, `status_desc`, `status_date`, `submitted_date`, `lat`, `lon`, `primary_address`, `zip_code` | Reconciliation corpus with immutable source versions. |
| Socrata CofO | `cofo_number`, `cofo_issue_date`, `latest_status`, `assessor_book`, `assessor_page`, `assessor_parcel`, `pcis_permit`, `permit_type`, `permit_sub_type`, `street_name`, `zip_code` | Reconciliation after concatenating parcel identity and qualifying the permit. |
| Malibu markers | `apn`, `iconShape` and endpoint marker fields | APN-linked coarse planning/building-review/permit assertions. Full observed field list is in the probe. |

`valuation` exists in the static permit shape but the producer sets it to null.
**All 5,033 bundled permit valuations are null.** There is no current market
data connector, listings ledger, sales history, title history, insurance ledger,
or neighborhood price model.

### Immediate opportunities inside existing agency data

1. County's live `REBUILD_PROGRESS` now includes `Rebuild In Construction`
   for 82 parcels. The patch accompanying this audit adds it as coarse,
   agency-reported work underway, dated unknown. It does not invent a passed
   inspection, construction completion, or occupancy certificate.
2. County metadata exposes `FSO_URL`, `DEBRIS_REMOVAL_EPICLA`, and
   `BUILD_PLAN_APPROVED`, which current field selection does not request.
   Inspect their records and definitions, especially private cleanup evidence.
   The current `DEBRIS_CLEARED` domain under the destroyed filter is `Yes` 286,
   `NA` 5,590, null 1; `NA` cannot be interpreted as uncleared.
   A follow-up probe found 4,289 non-null `FSO_URL` values; two sampled values
   point to parcel-specific PDFs under County Public Works' blob-storage route.
   It also found 124 non-null `BUILD_PLAN_APPROVED` values, with both sampled
   values reading `Building Plans Approved`. All 5,877 rows have non-null
   `DEBRIS_REMOVAL_EPICLA`, but both samples say `No Data`: non-null counts alone
   do not measure usable evidence. These were aggregate queries with the same
   destroyed-Palisades filter and two-row samples per field.
   Subsequent direct retrieval and visual inspection of
   [one example PDF](https://pwgis.blob.core.windows.net/epd/Debris_Removal/4412-013-017_FSO.pdf)
   succeeded: a seven-page USACE Final Property Clearance Form for 677 Via De
   La Paz, with March 21, 2025 USACE/contractor signatures, a separate County
   final-sign-off stamp, and six ground-level photographs. The checklist records
   foundation removal, utility capping/marking, access grading, erosion controls,
   retained features and other site conditions. Soil sampling is marked NA in
   this example; the document must not be presented as a soil-safety guarantee.
   The photographs belong to a dated clearance packet; individual photograph
   capture times were not independently verified. Text extraction missed the
   County stamp, which was visible when rendering the page: extraction must
   account for both digital text and embedded image content. One verified packet
   does not establish identical content or accessibility for all 4,289 links.
   **Completed follow-up:** all 5,877 records were inventoried with frozen ID
   completeness checks. There are 1,489 EPICLA `Finaled` statuses, including
   1,441 private opt-outs. Twelve PDFs downloaded successfully; some are
   withdrawal forms. See the follow-up before interpreting URL presence as
   cleanup completion or the initial two-row sample as field coverage.
3. [LADBS building-record services](https://www.ladbs.org/services/check-status/online-building-records)
   describe permit/inspection reports and a request route for PCIS/CofO/CEIS
   data. Investigate a supported bulk outcome feed and a small record sample.
   A purchase/request option is not proof that a free bulk API exists.
   **Completed follow-up:** normal browser access to the primary PCIS page
   supplied 34 inspection outcomes, nine clearances and professional/reviewer
   context for one permit. A validated DOM extraction adapter now exists;
   sustained bulk-worker reliability has not yet been measured.
4. The [City debris page](https://recovery.lacity.gov/debris-removal) covers
   government and private cleanup and describes final sign-off. Trace its
   dashboard's source and reconcile denominators before changing completion
   semantics. Its aggregate narrative cannot fill every individual parcel.

## Existing spatial and visual data

| Asset | Actual use | Limits |
|---|---|---|
| OpenFreeMap Positron / OSM | Base map, labels, roads | Basemap context; does not measure rebuilding. |
| AWS Mapzen Terrarium elevation tiles | Hillshade and optional terrain; max zoom 15 | Coarse global elevation; not a new local survey. |
| EagleView/LARIAC `CALOSA26` WMTS | Opt-in ground layer, hardcoded vendor account/layer route | Code/UI assert 2026 and even May 2026 without per-tile capture metadata. Current account access, image dates, coverage, and analytics/display rights need verification. A UI toggle does not establish rights. No imagery bytes were acquired in this audit. |
| Esri Wayback release 10842 | Fallback underneath the ground layer | May display pre-fire structures when newer imagery fails. Visible fallback/vintage disclosure is required. |
| Esri Wayback release 16453 | Property-card pre-fire tile | Code calls an archive date a capture date. [Esri explains that archive dates represent publication versions](https://www.esri.com/content/dam/esrisites/en-us/media/pdf/teach-with-gis/wayback-imagery.pdf). Query location metadata for actual acquisition dates. |
| LARIAC scene extraction and synthetic fallbacks | Bundled 3D atlas and coverage file | 4,976 LARIAC models, 184 footprint extrusions, 717 parcel prisms. All 5,877 have `missing_reason=null`, although 901 are synthetic fallback geometry. Coverage `acquired` dates are June 2026 processing-era values and must not stand in for historic flight dates. |
| [USGS emergency DEM](https://www.usgs.gov/3d-elevation-program/science/2025-post-wildfire-lidar-data-los-angeles-ca) | Canonical pipeline derives hillshade, terrain, surfels over four frozen Alphabet-area tiles | January 21, **2025** capture, 0.5 m grid. The selected asset is bare earth, which removes above-ground buildings. Excellent terrain baseline; unsuitable as current framing/roof evidence. USGS also advertises DSMs, worth cataloging separately. |
| Reconstruction fixture | Generated point clouds, ICP alignment, candidate review lifecycle | Synthetic demonstration. No operational imagery-to-framing detector or trained public change classifier was found. Its “confidence” multiplies heuristic factors and is not calibrated probability. |

The 3D directory occupies about 409 MiB on disk; its manifest reports 362 MB
of tile bytes, 11,077,461 splats, and 2,673 nodes. It still records all splats
as score-tinted from the old build. Inspect/rebuild the atlas before treating
its binary colors as compatible with the new evidence policy. Serving a
historical mesh is different from observing a new building.

## Market and community data to add

| Candidate | Verified access or evidence | Intended intelligence | Remaining dependency |
|---|---|---|---|
| [Assessor historical rolls](https://www.arcgis.com/home/item.html?id=70d93266f45a4080a97b285a471493cd&sublayer=0) | Catalog documents 2021–2025 rolls, AIN, recording date, land and improvement assessed values | Pre-fire baseline, taxable-value changes, building attributes | Fetch bounded extract and data dictionary; annual timing, reassessments, and calamity relief differ from sale prices. |
| [Assessor PAIS sales layer](https://assessor.gis.lacounty.gov/assessor/rest/services/PAIS/pais_sales_parcels/MapServer/0) | Live schema has AIN, SALEDATE, SALEPRICE; 75,854 countywide records | Historical comparables and ingestion prototype | **Stale**: latest countywide sale June 5, 2024; latest in study bbox May 10, 2024; zero post-fire rows. Not a post-fire turnover source. |
| MLS through a partner / licensed feed | [RESO](https://www.reso.org/reso-web-api/) describes standardized transport and local MLS licensing | Listing events, price changes, pending/closed/withdrawn, market time, lot vs rebuilt-home inventory | RESO supplies a standard, not data access. Obtain specific MLS coverage, historical-event rights, and public display/derived analytics terms. No credential or purchase assumed. |
| Licensed deed/transaction vendor | [ATTOM docs](https://api.developer.attomdata.com/docs), [ICE public records](https://www.ice.com/publicdocs/events/Public_Records_Data.pdf) describe relevant products | Recorded transfers, actual sale consideration, transaction documents, parcel lineage | Evaluate 100 stratified APNs and recording lag; quote and license required. Classify trusts, gifts, partial interests, multi-parcel packages, and non-arm's-length transfers. |
| County Recorder | [Official access policy](https://www.lavote.gov/home/recorder/real-estate-records/general-info) says online records/index access is unavailable | Audit selected transfers and resolve title discrepancies | Individual requests or licensed access path. Do not propose an imaginary public title API. |
| CDI insurance data | [CDI ZIP-level policy series](https://www.insurance.ca.gov/01-consumers/200-wrr/DataAnalysisOnWildfiresAndInsurance.cfm) and [wildfire claims tracker announcement](https://www.insurance.ca.gov/0400-news/0100-press-releases/2025/release016-2025.cfm) | Insurance availability and payment trends at their published geography | Aggregate reporting cannot reveal a parcel's policy, denial, payout, or coverage gap. Consented household submissions would be a separate private dataset. |
| Nearmap / EagleView archive | [Nearmap documents post-fire aerial captures](https://www.nearmap.com/au/blog/before-and-after-view-of-la-fire-impact) | Submeter dated imagery pairs for lot clearing, footprint and roof changes | Ask for exact scenes, GSD, dates, coverage, analysis/training and derived-output rights; current local catalog not verified. |
| Planet archive/tasking | [SkySat](https://docs.planet.com/data/imagery/skysat/) and [Tasking API](https://docs.planet.com/develop/apis/tasking/) document high-resolution collection | Fill critical temporal/spatial gaps after archive search | Contract, quote, cloud/off-nadir quality, minimum area, usable resolution and delivery constraints. No tasking order placed. |
| Public works, utilities, schools, businesses | Discovery targets, not validated connectors in this audit | Street reopening, utility restoration, school/business return, construction access | Find actual published geographies and timestamps; household-level reconnection needs an authorized data path. |
| [County ARDI Wildfire and Windstorm Impact Dashboard](https://ceo.lacounty.gov/2026/05/07/ardi-latest-news/new-dashboard-understanding-the-impact-of-the-january-2025-wildfires/) | Official May 2026 announcement confirms neighborhood, housing/displacement, worker/business and environmental layers | Broader community context beyond destroyed parcels | Discover underlying layers, dates, units and permitted reuse; dashboard availability does not establish a current longitudinal recovery feed. |
| Resident / contractor contributions | Product proposal | Dated site observations, document evidence, corrections, community return | Consent, authentication, capture provenance, review, withdrawal and explicit public/private separation. Empty site imagery does not establish whether a household intends to return. |

## Source selection policy proposed for implementation

Follow-up vintage check: the CDI policy-series page currently links ZIP-level
2020–2023 counts and 2022 FAIR Plan percentages. Those are historical exposure
baselines, not post-fire insurance availability measurements. Its separate
wildfire claims tracker needs its own reporting-period and geography contract.

Each source needs a small executable contract: geography; unit of observation;
stable native key; allowed joins; known omissions; event time vs retrieval time;
update cadence and observed lag; vocabulary/schema fingerprint; raw response
hashes; allowed display/analysis/training/redistribution; retention; and tests
on actual source examples. Version schema and meaning independently.

Audit refreshes should distinguish a source outage, a changed schema, a new
status, an empty valid response, an unmatched parcel, and an unobserved state.
Those cases require different repairs and must not all appear as gray parcels.

For imagery, use [STAC](https://stacspec.org/en/about/stac-spec/) Items and
Collections to describe footprints, capture intervals, assets, resolution,
providers, and licenses. Keep raw scene IDs and processing lineage. An archive
publication timestamp, HTTP Last-Modified value, and a flight time are distinct.
