"""Versioned catalog of authoritative raster baselines for the spatial core.

A *baseline* is an external elevation/imagery product pinned by a stable
identifier so ingestion is reproducible and a later authoritative re-release can
supersede a provisional one without ambiguity. Keeping the provenance here — not
inline at the call site — means the (CRS, vertical datum, license, supersession)
facts live in exactly one place and can be asserted in tests.

The first entry is the 2025 post-fire LiDAR DEM. Its facts were verified against
three OpenTopography primaries (raster product page, otCatalog JSON API, and the
DOI landing page), cross-checked against USGS 3DEP and NOAA InPort item 77762.
The two most consequential, non-obvious facts:

- **Vertical datum is NAVD88 / GEOID18 (EPSG:5703), not EGM96 and not
  ellipsoidal.** It must be lifted to WGS84 ellipsoidal once at ingestion via
  ``geodesy.navd88_geoid18_to_wgs84`` (grid-based) — never the scalar EGM96
  offset used for the LARIAC meshes (the two differ ≈ 0.6 m here).
- **Flown 2025-01-21, before USACE Phase-2 debris removal (2025-02-11).** The DSM
  therefore captures rubble/ash/standing chimneys in place, so DSM−DTM (nDSM)
  over a destroyed parcel is DEBRIS height, not structure. This is the canonical
  immediate-post-burn t0 — a feature for damage/volume work, a trap for any
  "cleared lot" assumption.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RasterBaseline:
    """One pinned external raster product."""

    key: str
    title: str
    opentopo_id: str
    doi: str
    products: tuple[str, ...]  # e.g. ("DTM", "DSM")
    horizontal_epsg: int  # 6340 = NAD83(2011) / UTM 11N (metres)
    vertical_epsg: int  # 5703 = NAVD88 height (GEOID18)
    resolution_m: float
    acquired: str  # ISO acquisition date
    preliminary: bool  # True until USGS publishes the 3DEP-QA'd edition
    license: str
    s3_uris: tuple[str, ...]
    notes: str = ""

    @property
    def doi_url(self) -> str:
        return f"https://doi.org/{self.doi}"


# Verified 2026-06 against OpenTopography + USGS 3DEP + NOAA InPort.
# Palisades = ...6340.2 (DOI G9DR2SPG). Three easily-confused neighbours to NEVER
# substitute for this raw post-fire DEM:
#   - Eaton-fire sibling:      OTSDEM.012025.6340.1   (DOI 10.5069/G9JH3JD6)
#   - 2016↔2025 differencing:  OTDS.022025.32611.1    (DOI 10.5069/G95B00PW, EPSG:32611, 1 m)
#   - pre-fire reference:      USGS_LPC_CA_LosAngeles_2016
PALISADES_POSTFIRE_DEM = RasterBaseline(
    key="palisades_postfire_dem_2025",
    title="Preliminary Post-Fire DEM/DSM — Palisades Fire, CA (Jan 2025)",
    opentopo_id="OTSDEM.012025.6340.2",
    doi="10.5069/G9DR2SPG",
    products=("DTM", "DSM"),
    horizontal_epsg=6340,  # NAD83(2011) / UTM Zone 11N, metres
    vertical_epsg=5703,  # NAVD88 height, GEOID18
    resolution_m=0.5,
    acquired="2025-01-21",
    preliminary=True,  # NOT USGS-QA'd ("preliminary"); a 3DEP edition will supersede
    license="CC0-1.0",
    s3_uris=(
        # USGS The National Map — anonymous; per-tile 0_file_download_links.txt manifests
        "s3://prd-tnm/CA_FireImpactZone_2025_PRELIMINARY/Palisades/",
        # OpenTopography SDSC store (endpoint https://opentopography.s3.sdsc.edu)
        "s3://raster/CA25_Palisades/",
    ),
    notes=(
        "Vertical datum NAVD88/GEOID18 (EPSG:5703) — convert to WGS84 ellipsoidal "
        "once at ingestion via geodesy.navd88_geoid18_to_wgs84 (grid-based, NOT the "
        "EGM96 −35.6 m constant). Flown 2025-01-21, BEFORE USACE Phase-2 debris "
        "removal: the DSM captures rubble in place, so nDSM over a burned parcel is "
        "debris height, not structure. Not native COG (plain tiled GeoTIFF) — re-tile "
        "with `rio cogeo`. Preliminary/provisional: gate headline numbers behind a "
        "'preliminary, pre-cleanup' label and re-ingest when the 3DEP edition lands."
    ),
)

# Registry keyed by stable `key`, for the ingestion step to look up by name.
BASELINES: dict[str, RasterBaseline] = {PALISADES_POSTFIRE_DEM.key: PALISADES_POSTFIRE_DEM}
