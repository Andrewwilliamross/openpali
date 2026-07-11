# Artifact Contract

The pipeline emits four static files into `web/public/data/`. This is the full
interface between pipeline and frontend — neither side knows anything else about the
other.

## parcels.geojson — the map layer (lean on purpose)

FeatureCollection, WGS84, one feature per destroyed-structure parcel. Properties are
flat and minimal — only what MapLibre styling/interaction needs:

```jsonc
{
  "apn": "4423016021",
  "address": "123 ALMA REAL DR",       // situs, title-cased by UI
  "neighborhood": "Alphabet Streets",
  "jurisdiction": "LA",                 // LA | COUNTY | MALIBU
  "struct": "SFR",                      // SFR | MFR | COM | OTH
  "stage": 3,                           // 0..5 (see METHODOLOGY.md)
  "stage_label": "Permitted",
  "score": 44.5,                        // 0..100 → red-green gradient
  "last_event": "2026-04-17"            // most recent activity, for staleness UI
}
```

## details.json — per-parcel drill-down (loaded once, keyed by APN)

```jsonc
{
  "4423016021": {
    "address": "123 Alma Real Dr",
    "pre_fire": { "use": "SFR", "year_built": 1952, "sqft": 2410,
                  "beds": 3, "baths": 2, "units": 1 },
    "events": [                          // unified timeline, ascending
      { "date": "2025-03-02", "kind": "debris_cleared", "label": "Lot cleared (USACE)" },
      { "date": "2025-06-14", "kind": "permit_submitted", "label": "Permit application", "ref": "25016-10000-01234" },
      { "date": "2025-11-03", "kind": "permit_issued", "label": "Building permit issued" },
      { "date": "2026-02-21", "kind": "inspection", "label": "Foundation approved" }
    ],
    "permits": [ { "no": "25016-10000-01234", "type": "Bldg-New", "status": "Issued",
                   "submitted": "2025-06-14", "issued": "2025-11-03",
                   "valuation": 850000, "url": "https://..." } ],
    "est_completion": "Late 2027",       // human label, null when stage 0/5
    "score": 44.5,
    "score_explain": "Permitted 7 months ago; cohort median to first inspection is 2.9 months — slower than typical."
  }
}
```

## summary.json — header metrics + sparkline

```jsonc
{
  "as_of": "2026-06-09T18:00:00Z",
  "totals": { "destroyed": 5438, "cleared": 5301, "plan_check": 712,
              "permitted": 1290, "under_construction": 794, "complete": 13 },
  "weekly": [ { "w": "2025-02-03", "submitted": 4, "issued": 0 }, ... ],
  "baselines": [ { "source": "LADBS", "as_of": "2026-06-01", "metric": "permits_issued",
                   "official": 2120, "ours": 2098 } ],
  "neighborhoods": [ { "name": "Alphabet Streets", "center": [-118.5265, 34.0438],
                       "zoom": 15.5, "destroyed": 612, "permitted": 188,
                       "under_construction": 102, "complete": 3 } ]
}
```

## meta.json — source health (honest freshness)

```jsonc
{ "generated": "2026-06-09T18:00:00Z",
  "sources": [ { "id": "ladbs_permits", "as_of": "2026-06-09", "ok": true,
                 "records": 4310, "note": "" } ] }
```

Rules: stages/score bands are defined in METHODOLOGY.md; `parcels.geojson` stays under
~8 MB raw (simplify parcel rings to ~1e-6 deg tolerance if needed); all dates ISO-8601;
missing data is `null`, never fabricated.
