# Actual geography for the 2D field notebook

## Recommendation

Use [`map/close/alphabet-streets-linework.svg`](../../assets/brand/field-notes-2d/map/close/alphabet-streets-linework.svg) for the hero. It shows **61 actual parcel features** around **Galloway Street and Hartzell Street where they meet Bestor Boulevard**, in the Alphabet Streets area of Pacific Palisades. The tighter frame makes individual lots readable at the proposed website size. The slight curve of Bestor and the angled parallel streets give it a specific local arrangement.

Use the 150-parcel [`map/alphabet-streets.svg`](../../assets/brand/field-notes-2d/map/alphabet-streets.svg) when more neighborhood context is useful. That version also labels Fiske and Albright Streets. Both variants use exactly the same 1100 × 720 SVG coordinate system and reserve a right-hand margin.

The close map is a neutral geographic drawing. It carries no damage, rebuilding, permit, construction, occupancy, property-value, owner, or address fields. It contains no building footprints or building designs.

## Why the bundled map was not used as the neutral base

The bundled `web/public/data/parcels.geojson` contains 5,877 real polygons, but `web/public/data/meta.json` identifies its source query as `FIRE_NAME='Palisades' AND DAMAGE='Destroyed (>50%)'`. That snapshot is appropriate to its original application context. Using it as a complete neighborhood base would silently omit parcels outside that selected universe.

The checked-in spatial AOI covers `[-118.532835, 34.036386, -118.516832, 34.050111]` and references an emergency USGS elevation acquisition. It is useful project context, but neither its damage-universe count nor its elevation vintage establishes current construction conditions. The new drawing therefore uses freshly retrieved **general County parcel geometry** and **County street centerlines**, selected only by a geographic window.

## Coordinates for composition

### Close hero — recommended

| Item | Coordinates |
| --- | --- |
| SVG viewBox | `0 0 1100 720` |
| WGS84 display extent, west/south/east/north | `[-118.52230, 34.05015, -118.51980, 34.05170]` |
| Actual map rectangle in SVG units | `x49.51, y92, width726.98, height544` |
| Parcel source features | 61 |
| Street source features | 8 |
| Verified visible street labels | Galloway St, Hartzell St, Bestor Blvd |
| First bird foot position | `(140.34, 270.08)`, aligned with Galloway St |
| Second bird foot position | `(452.42, 322.28)`, aligned with Hartzell St |
| Blank right margin | `x825, y100, width240, height520` |
| Suggested illustrative detail inset | `x830, y390, width230, height205` |

The bird positions are decorative animation anchors. They are not a pedestrian route, a location observation, or an assertion about access. Scale the geometry uniformly. Keep the map stationary while the pelican moves. A foot point is the contact point at the bottom of the character, not the character’s center.

### Wider context

Extent: `[-118.52345, 34.04920, -118.51950, 34.05170]`. Map rectangle: `x56.92, y92, width712.15, height544`. It contains 150 parcel features and 16 street features. Bird foot positions: `(139.67,239.62)` on Fiske and `(523.51,286.46)` on Hartzell.

Both variants preserve these layer IDs:

- `actual-parcels`
- `actual-street-centerlines`
- `verified-street-labels`
- `illustrative-margin`
- `character-layer`

The complete white-paper versions add `paper`, `map-heading`, `orientation`, and `source-caption`. The transparent linework versions remove those four framing groups. The parcel and street paths remain identical.

## Sources and confidence

**Parcel geometry:** Los Angeles County Office of the Assessor, general parcel map service. The saved query requests only `OBJECTID` and geometry, with no damage or recovery filter. [Official catalog](https://www.arcgis.com/home/item.html?id=5b277305f006459586a70165065d0fd6) · [Official geometry endpoint](https://cache.gis.lacounty.gov/cache/rest/services/LACounty_Cache/LACounty_Parcel/FeatureServer/0).

**Street geometry and labels:** Los Angeles County Countywide Address Management System (CAMS), Address Street Lines. Labels are taken from the returned `FullName` attribute and positioned on the corresponding source lines. The provider describes this layer as a cartographic/geocoding resource, not a routing network. [Official catalog](https://www.arcgis.com/home/item.html?id=0a72e51eab7949678aff0670bf5d108b) · [Official geometry endpoint](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/eGIS_Addressing_ROAD_LINES/FeatureServer/0).

**Place-name cross-check:** the City’s planning map identifies the Alphabet Streets road names, including Fiske, Galloway, Hartzell, Albright, and Bestor. No street names were invented from the parcel pattern. [City planning source](https://planning.lacity.gov/ordinances/docs/ProprosedNeighborhood/Proposed%20Ordinance%20Maps%20DRAFT.pdf).

The source provenance is strong: official endpoints, retained responses, request parameters, source object IDs, and SHA-256 hashes. That does not make the drawing a boundary survey or evidence of current property conditions. The County describes its parcel data as informational and potentially unsuitable for engineering, surveying, or legal uses. The visual may resemble an architect’s plan; it should not claim to be an engineering drawing.

A coastline is intentionally absent. This is an inland close-up; drawing a nearby shoreline inside this frame would place it incorrectly.

## Terms and attribution

The County eGIS terms were read in the browser on September 27, 2026. They permit publication and adaptation under the County’s conditions, grant no ownership interest, prohibit implied County endorsement, and provide data without accuracy/completeness warranties. The street item’s `licenseInfo` field says `None`; that is not treated as a public-domain designation. The County-wide terms apply to its published mapping data. [County GIS terms](https://egis-lacounty.hub.arcgis.com/pages/terms-of-use).

Use this short visible credit when the drawing appears in the website or a composed brand image:

**Map: LA County Assessor · LA County CAMS**

Keep the full source references and terms link in adjacent documentation, accompanying post copy, or asset metadata. Recommended full citation:

> Los Angeles County Office of the Assessor; Los Angeles County Countywide Address Management System. Parcel boundaries and Address Street Lines [datasets]. County of Los Angeles Enterprise GIS. Accessed September 27, 2026. Source links and retained query metadata in `map/provenance.json`.

This is a County data-license basis, not a claim that the data is CC0 or public domain. It does not select a license for OpenPali’s software or new character artwork.

## Boundary between fact and illustration

The parcel and street paths are factual source geometry. The pelican, notebook, pencil movements, construction-detail inset, callout leaders, dimension ticks, and written margin notes are illustration. Keep the illustrative inset outside the actual parcel frame and label it **Illustrative detail**. Avoid fabricated dimension values, building footprints drawn onto specific lots, construction phases appearing on real parcels, or a progress/status color system.

The animation can look at a source, compare notes, or draw a margin callout. It should not redraw the neighborhood or make a building appear to be reconstructed. The notebook can remain delightful without converting character movement into a factual claim.

## Files and reproducibility

All geography artifacts are under [`assets/brand/field-notes-2d/map/`](../../assets/brand/field-notes-2d/map/):

- `alphabet-streets.svg`: white-paper context plan with heading, north arrow and source caption.
- `alphabet-streets-linework.svg`: transparent context plan for composition.
- `close/`: the recommended 61-parcel versions of the same files.
- `geometry.json` and `close/geometry.json`: SVG paths, geographic extent, projection transform, verified label positions, bird stops, and reserved margin.
- `parcels.geojson` and `streets.geojson` in each variant: full source WGS84 coordinates. These retain geometry outside the displayed clip where a feature crosses its edge. `display_extent_wgs84` records the camera window and is not represented as the full data bounding box.
- `provenance.json` in each variant: source URLs, terms notes, limits, and input hashes.
- `source/`: official metadata, original query responses and query URLs/parameters. No address or status records were acquired for the parcel drawing.
- `build_map.py`: standard-library-only generator.
- `preview.png` and `close/preview.png`: browser renders inspected before handoff.

Rebuild from the retained official responses:

```sh
python3 assets/brand/field-notes-2d/map/build_map.py
python3 assets/brand/field-notes-2d/map/build_map.py --close
```

The generator projects WGS84 coordinates to Web Mercator, applies one uniform affine transform, clips at the geographic display window, and rounds SVG positions to 0.01 units. It does not simplify vertices or invent lot edges. Original coordinates remain in the GeoJSON and raw responses. Shared edges may appear in neighboring parcel paths; they use one neutral stroke treatment.

Both browser renders were visually inspected. The closer crop was chosen after the wider drawing proved too dense for the proposed hero size.
