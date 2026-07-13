# Supplementary domain probe — 2026-07-11

Retrieved live through `palisades.http.cached_get_json` (raw bytes + sha256 in
`data/raw`, provenance-recorded).

## County `DEBRIS_CLEARED` (FIRE_NAME='Palisades')

| value | n |
|---|---|
| "Yes" | 308 |
| "NA" | 12,075 |
| null | 0 |

Only 308 "Yes" versus 4,027 `ROE_STATUS='Final Sign Off - Complete'` — the
field's meaning relative to the ROE program is NOT documented. Decision:
record the domain, never derive milestone observations from it until an
official definition is found (fail-closed posture).

## Malibu marker feed `iconShape` (live, 269 rows)

| value | n |
|---|---|
| PendingBSReview | 92 |
| PermitIssued | 85 |
| InBPC | 51 |
| InPlanning | 41 |

Feed: `mlb-pptsrv.ci.malibu.ca.us/Home/GetProjectDashMarkers?sFireView=PalisadesRebuildStatsDetailWithBPComplete`
(undocumented internal endpoint of the official city dashboard; observations
derived from it carry a coarse/unofficial-feed detail flag and jurisdiction
warning).

## LADBS permit-type × rebuild-flag cross-tab (live)

Bldg-New: Rebuild 1,135 / No 750. Grading: Rebuild 699 / No 489.
Nonbldg-New: 4/583. Bldg-Alter/Repair: 67/474. Fire Sprinkler: 0/467.
Swimming-Pool/Spa: 2/248. Plumbing: 0/137. Bldg-Addition: 32/94.
Electrical: 0/70. Bldg-Demolition: 0/30. Nonbldg-Alter/Repair: 0/26.
HVAC: 0/11. Elevator: 0/9. Sign: 0/2. Nonbldg-Addition: 0/1.
Nonbldg-Demolition: 0/1.

Conclusion: `PALISADES_WF_REBUILD='Rebuild'` marks rebuild-related work of any
permit type. Qualifying primary rebuild application := `PERMIT_TYPE='Bldg-New'
AND PALISADES_WF_REBUILD='Rebuild'` (policy `qualifying-rebuild-v1`).
