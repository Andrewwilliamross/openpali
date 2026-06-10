# Data Sources — verified endpoints

All endpoints below were **live-curl-verified** during research (workflow `wf_aa2adff4`,
raw payload in [data/research/](../data/research/research-output-wf_aa2adff4.json)) and
spot-re-verified 2026-06-10. Every join is on **APN** (10-digit, dashes stripped).

## The architecture in one paragraph

LA County and LA City each publish a *pre-joined* parcel layer, which collapses most of
the join work. We use the **County debris-removal layer as the base** (polygon geometry +
damage + jurisdiction + debris + pre-fire attrs + a coarse county rebuild status for all
12,387 Palisades parcels), then **overlay LA City's per-permit LADBS feed** to get the
rich permit/inspection/CofO timeline that powers the rebuild *score* on the ~4,700
City-of-LA destroyed lots. County-unincorporated and Malibu lots get a coarser stage
mapped from their own status fields — full-footprint coverage with graceful degradation.

## Tier 1 — load-bearing (the pipeline depends on these)

### Base layer · LA County Parcels Debris Removal (Public)
`services.arcgis.com/RmCCgQtiZLDCtblq/.../Parcels_Debris_Removal_Public/FeatureServer/0`
- **Geometry:** polygon (esriGeometryPolygon), `f=geojson&outSR=4326`, maxRecordCount 2000
- **Filter:** `FIRE_NAME='Palisades' AND DAMAGE='Destroyed (>50%)'` → **5,877 parcels** (the universe)
- **Fields:** `APN`, `AIN`, `SITUSFULLADDRESS`, `SITUSZIP`, `CENTER_LAT/LON`, `LCITY`
  (`Los Angeles`|`Malibu`|`Unincorporated` — **authoritative jurisdiction**), `DAMAGE`,
  `STATUS_EPA`, `ROE_STATUS` (debris milestone), `DEBRIS_CLEARED`, `REBUILD_PROGRESS`
  (county-jurisdiction rebuild stage), `USETYPE/USECODE/YEARBUILT1/SQFTMAIN1` (pre-fire)
- **Cadence:** updated through 2026-06-09; pull nightly.
- ROE_STATUS taxonomy → debris milestone: `Final Sign Off - Complete`/`- Ineligible` and
  `Opt-Out and Manage Cleanup Independently` ⇒ **cleared**; `No ROE`/`Non-responsive` ⇒ not cleared.

### City of LA permit timeline · LADBS Wildfire Permit Data — Palisades Recovery Area
`services5.arcgis.com/7nsPwEMP38bSkCjy/.../LADBS_WF_Fire_Data_Palisades_Recovery_Area/FeatureServer/0`
- **Geometry:** point. ~4,861 rows (one row per permit/plan-check application). Group by APN.
- **Fields:** `PERMIT`, `APN` (dashed), `ADDRESS`, `PERMIT_TYPE` (`Bldg-New`, `Bldg-Demolition`,
  `Grading`, `Swimming-Pool/Spa`, …), `PERMIT_SUBTYPE`, `TYPE` (`Plan Check Application`|`Permit`),
  `PERMIT_STATUS` (`Plans Submitted` → `Plan Check in Progress` → `Corrections Issued` →
  `Plans Approved & Permit Not Issued` → `Plans Approved & Permit Issued`), `SUBMIT_DATE`,
  `PC_APPROVED_DATE`, `ISSUE_DATE`, `COFO_DATE`, `STATUS_DATE` (all **epoch ms**),
  `PALISADES_WF_REBUILD` (`Rebuild`|`No`), `ELIGIBILITY`, `DAYS_TO_PC_APPROVED/_PERMIT_ISSUE`
- **This is also the validation oracle** — server-side group-by counts must reconcile with ours.

### Construction inspections · LADBS WildfireRecovery MapServer, table 4
`maps.lacity.org/lahub/rest/services/WildfireRecovery/MapServer/4`
- Table `LADBS_WF_Inspection_Data_tbl`. Join on `PERMIT`. Fields: `PERMIT`, `INSP_DT`,
  `INSP_STATUS`, `INSP_DESC`, `CRNT_STAT`. Maps to stage-4 construction milestones
  (foundation → framing → MEP → drywall → final). ~1,014 rows currently.

## Tier 2 — full-footprint coverage (non-City-of-LA)

### Malibu rebuild markers
`mlb-pptsrv.ci.malibu.ca.us/Home/GetProjectDashMarkers?sFireView=PalisadesRebuildStatsDetailWithBPComplete`
- Plain GET (browser UA), **server-side only** (no CORS guarantee — proxy via pipeline).
  264 markers: `apn`, `latlng`, `caseNo`, `iconShape` (`InPlanning`|`PendingBSReview`|`InBPC`|`PermitIssued`).
- 4-stage taxonomy → our stages: InPlanning⇒2, PendingBSReview/InBPC⇒2, PermitIssued⇒3.

### County unincorporated rebuild detail (optional enrichment)
`services.arcgis.com/RmCCgQtiZLDCtblq/.../EPIC-LA_Case_History_view/FeatureServer/0`
- `where=DISASTER_TYPE='Palisades Fire (01-2025)'` → 398 cases, `MAIN_AIN`, `REBUILD_PROGRESS`,
  `REBUILD_PROGRESS_NUM` (1–7). For v1 we use the coarser `REBUILD_PROGRESS` already in the base layer.

## Tier 3 — context & enrichment

| Purpose | Endpoint | Notes |
|---|---|---|
| Fire perimeter (map outline) | `egis.fire.ca.gov/.../FRAP/FirePerimeters_FS/FeatureServer/0` `where=FIRE_NAME='PALISADES' AND YEAR_=2025` | 1 polygon, final, cache once |
| DINS damage (cross-check) | `services1.arcgis.com/jUJYIo9tSA7EHvfZ/.../POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0` | 6,845 destroyed structures; baseline |
| Pre-fire beds/baths | `services.arcgis.com/RmCCgQtiZLDCtblq/.../Parcel_Data_2021_Table/FeatureServer/0` `RollYear='2024'` | optional; base layer already has use/year/sqft |
| Pre-fire lot imagery | Esri Wayback release **16453** (last pre-fire, 2024-08-15 capture) `wayback.maptiles.arcgis.com/.../tile/16453/{z}/{y}/{x}` | **client-side**, per detail card (license: no bulk export). Note Y-before-X. Attribution required. |
| Post-fire aerial (before/after) | NOAA ERI `stormscdn.ngs.noaa.gov/20250128a-rgb/{z}/{x}/{y}` | standard XYZ; future before/after slider |
| Basemap | OpenFreeMap `tiles.openfreemap.org/styles/positron` | keyless, no limits |

## CofO cross-check (Socrata)
`data.lacity.org/resource/3f9m-afei.json` — `pcis_permit` (dashed), `assessor_book/page/parcel`
(concat = APN), `cofo_issue_date`, `permit_type`. Use to validate our CofO count. The LADBS
layer's `COFO_DATE` is the primary completion signal.

## Validation baselines (reconcile pipeline output against these)
- Official city dashboard: `experience.arcgis.com/experience/733fd745b763467a944b673e017c06ab`
- Official county dashboard: `recovery.lacounty.gov/rebuilding/permitting-progress-dashboard/`
- Community: Palisadian-Post (`palipost.com`), Pali Builds (`palibuilds.com`), Crosstown (`xtown.la`)
- **Reconciliation rule:** computed counts (destroyed, permitted, under construction, CofO) must
  match the LADBS oracle's server-side group-by under identical filters; drift >5% ⇒ data-quality notice.

## Known caveats
- DINS counts **structures** (6,845); we count **parcels** (5,877). Don't validate one against the other.
- LADBS permit numbers are dash-separated; Socrata inspections are space-separated — normalize.
- Malibu feed is an unofficial internal API — snapshot raw responses, alert on shape change.
- A lot can have multiple permits/cases — group by APN, take the furthest stage.
- Epoch-ms dates everywhere in ArcGIS layers; Socrata uses ISO calendar dates.
