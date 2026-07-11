# Artifact Contract

The pipeline emits four static files into `web/public/data/`. This is the full
interface between pipeline and frontend — neither side knows anything else about the
other.

Every run stamps one **`snapshot_id`** (`<UTC time>-<run_id prefix>`) into all four
artifacts so the frontend can detect mixed-vintage reads, and records per-source
provenance (raw-response sha256, query, schema fingerprint, true fetch time) in
`meta.json`. **Expectation gates** (`pipeline/palisades/checks.py`) run before emit:
`error`-level violations abort the run and leave the previously published artifacts
untouched; `warn`/`info` incidents publish but are recorded in `meta.json`.

## parcels.geojson — the map layer (lean on purpose)

FeatureCollection, WGS84, one feature per destroyed-structure parcel, plus a
top-level `snapshot_id` foreign member (RFC 7946 §6.1). Properties are flat and
minimal — only what MapLibre styling/interaction needs:

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

One `_snapshot_id` key (underscore-prefixed — cannot collide with 10-digit APNs)
plus one entry per APN:

```jsonc
{
  "_snapshot_id": "20260611T233350Z-db750e",
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

## summary.json — header metrics + sparkline + official reconciliation

`baselines` is **guaranteed populated** on every validated run (live runs query the
oracle fresh; `--offline` runs reuse the cached oracle responses). Each row carries
the `as_of` of the oracle fetch that produced it, our number, and the drift flag:

```jsonc
{
  "as_of": "2026-06-11T23:33:50+00:00",
  "snapshot_id": "20260611T233350Z-db750e",
  "totals": { "destroyed": 5877, "cleared": 5590, "plan_check": 911,
              "permitted": 628, "under_construction": 489, "complete": 17 },
  "weekly": [ { "w": "2025-02-03", "submitted": 4, "issued": 0 }, ... ],
  "baselines": [ { "source": "LADBS", "metric": "parcels_permit_issued_bldgnew",
                   "as_of": "2026-06-10", "official": 984, "ours": 1008,
                   "drift_pct": 2.4, "ok": true } ],
  "neighborhoods": [ { "name": "Alphabet Streets", "center": [-118.5265, 34.0438],
                       "zoom": 15.5, "destroyed": 612, "permitted": 188,
                       "under_construction": 102, "complete": 3 } ]
}
```

`ok:false` (drift >5%) is the METHODOLOGY.md data-quality condition: the UI must
show a notice rather than silently presenting our number as truth.

## coverage.json — the 3D honesty layer

One entry per destroyed parcel (the FULL 5,877 universe — emitted by the
spatial export). Every rendered 3D parcel carries its geometry provenance so a
placeholder can never masquerade as an observation; the detail card shows the
matching badge.

```jsonc
{
  "4412017012": {
    "geometry_source": "parcel_prism",   // lariac_model | footprint_extrusion
                                          // | parcel_prism | null
    "n_splats": 217,
    "acquired": "2026-06-13",            // date of the underlying source data
    "missing_reason": null                // set when geometry_source is null
  }
}
```

Classes: `lariac_model` (real pre-fire LARIAC scene surfels),
`footprint_extrusion` (LARIAC footprint × published HEIGHT/ELEV, approximate),
`parcel_prism` (county parcel polygon × default massing — a presence marker).
The tiles `manifest.json` carries the class counts as `coverage_sources`.

## meta.json — source health, provenance, incidents

```jsonc
{
  "generated": "2026-06-11T23:33:50+00:00",
  "run_id": "db750ef15f69",
  "snapshot_id": "20260611T233350Z-db750e",
  "sources": [
    { "id": "ladbs_permits",
      "as_of": "2026-06-10",              // when the data was ACTUALLY fetched
      "ok": true,                          // (cache mtime on offline runs)
      "records": 4861,                     // upstream rows fetched
      "note": "LADBS Palisades Recovery",
      "endpoint": "https://services5.arcgis.com/.../FeatureServer/0",
      "query": "1=1",
      "joined": 4596,                      // rows joined to the destroyed universe
      "sha256": "b07b37f17995…",           // raw bytes (sorted page hashes hashed)
      "schema_fingerprint": "3a140097f78a8a18",  // field set + value types
      "requests": 5, "bytes": 2052627, "cache_hits": 5,
      "fetched_at": "2026-06-10T18:39:18+00:00",
      "unparseable": 19, "parcels_matched": 1625 }  // per-source extras when nonzero
  ],
  "incidents": [                           // warn/info gate findings this run
    { "level": "warn", "code": "label_taxonomy", "message": "…" }
  ],
  "artifacts": {                           // sha256 of the bytes written this run
    "parcels.geojson": "0f7b4f08…", "details.json": "…", "summary.json": "…"
  }
}
```

Gate codes: `universe_empty`, `apn_parse_rate`, `duplicate_apns`, `missing_geometry`,
`source_failed`, `stage_taxonomy`, `label_taxonomy`, `universe_shrank` /
`universe_changed`, `reconciliation_unavailable`, `official_drift`, `schema_drift`.

Rules: stages/score bands are defined in METHODOLOGY.md; `parcels.geojson` stays under
~8 MB raw (simplify parcel rings to ~1e-6 deg tolerance if needed); all dates ISO-8601;
missing data is `null`, never fabricated.
