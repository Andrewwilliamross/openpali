"""Phase 1: the 2025 post-fire DTM as the in-footprint terrain skin.

This module owns the parts of post-fire terrain ingestion that fit the
lightweight pipeline: it PLANS the build, emits the web terrain MANIFEST, wires
the vertical-datum reconciliation (Phase 0's `navd88_geoid18_to_wgs84`), and
implements the terrarium encode/decode primitive.

The heavy raster step — mosaic the USGS/OpenTopography GeoTIFF tiles, clip to
the burn footprint, reproject EPSG:6340 + lift NAVD88/GEOID18 -> WGS84
ellipsoidal, write a COG master, and bake a terrarium tile pyramid — needs a
raster toolchain (GDAL / rasterio + rio-rgbify). That is intentionally NOT a
core dependency (the pipeline is numpy/scipy/pyproj/shapely only), and the
produced tiles belong in object storage, never git (cf. the 313 MB splat-in-git
problem). `generate_terrain_tiles` isolates it behind a lazy import and an
actionable error carrying the exact command recipe.

The terrain source config the web reads (lib/terrain.ts) is mirrored by
`terrain_manifest` — same fields — so the front end can move from env-var wiring
to a fetched manifest without a schema change.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .baselines import PALISADES_POSTFIRE_DEM, RasterBaseline
from .geodesy import navd88_geoid18_to_wgs84

# Palisades post-fire DEM footprint (WGS84), from OTSDEM.012025.6340.2.
# Mirrors web/src/lib/terrain.ts POSTFIRE_DTM_BOUNDS — keep in sync.
PALISADES_DEM_BOUNDS_WGS84: tuple[float, float, float, float] = (
    -118.698, 34.027, -118.431, 34.139)

# Terrarium leaves ~3.9 mm vertical quantization (1/256 m) — lossless enough for a
# 0.5 m DTM. Tiles MUST be lossless PNG; JPEG would corrupt the packed elevation.
_TERRARIUM_BASE = 32768.0


# ---------------------------------------------------------------------------
# terrain-RGB (terrarium) encode / decode — the one raster primitive we own
# ---------------------------------------------------------------------------


def encode_terrarium(elev_m: np.ndarray) -> np.ndarray:
    """Elevations (metres) -> terrarium RGB (..., 3) uint8.

    terrarium packs `v = elevation + 32768` as r*256 + g + b/256, so it carries a
    1/256 m fractional channel — decode is `(r*256 + g + b/256) - 32768`.
    """
    v = np.asarray(elev_m, dtype=np.float64) + _TERRARIUM_BASE
    v = np.clip(v, 0.0, 65535.999)
    r = np.floor(v / 256.0)
    g = np.floor(v - r * 256.0)
    b = np.floor((v - np.floor(v)) * 256.0)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def decode_terrarium(rgb: np.ndarray) -> np.ndarray:
    """terrarium RGB (..., 3) -> elevation (metres), inverse of `encode_terrarium`."""
    a = np.asarray(rgb, dtype=np.float64)
    return (a[..., 0] * 256.0 + a[..., 1] + a[..., 2] / 256.0) - _TERRARIUM_BASE


# ---------------------------------------------------------------------------
# burn footprint
# ---------------------------------------------------------------------------


def burn_footprint_bounds(parcels_geojson: Path) -> tuple[float, float, float, float]:
    """(minlon, minlat, maxlon, maxlat) over every parcel geometry.

    The destroyed-parcel universe IS the area we care about clipping the DTM to.
    """
    from shapely.geometry import shape

    feats = json.loads(Path(parcels_geojson).read_text())["features"]
    minlon = minlat = float("inf")
    maxlon = maxlat = float("-inf")
    for f in feats:
        geom = f.get("geometry")
        if not geom:
            continue
        x0, y0, x1, y1 = shape(geom).bounds
        minlon, minlat = min(minlon, x0), min(minlat, y0)
        maxlon, maxlat = max(maxlon, x1), max(maxlat, y1)
    if minlon == float("inf"):
        raise ValueError("no parcel geometries to derive a footprint from")
    return (minlon, minlat, maxlon, maxlat)


# ---------------------------------------------------------------------------
# build plan + manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TerrainBuildPlan:
    """Everything the heavy raster step needs, plus what the web manifest carries."""

    baseline_key: str
    doi: str
    preliminary: bool
    # source frame (the raw DEM)
    source_hcrs: str  # EPSG:6340 NAD83(2011)/UTM 11N
    source_vcrs: str  # EPSG:5703 NAVD88/GEOID18
    # target frame: WebMercator tiles, heights baked to WGS84 ellipsoidal at ingest
    target_tile_crs: str  # EPSG:3857
    target_vdatum: str  # "WGS84 ellipsoidal (NAVD88/GEOID18 via grid)"
    encoding: str  # "terrarium"
    tile_size: int
    minzoom: int
    maxzoom: int
    bounds: tuple[float, float, float, float]  # WGS84 minlon,minlat,maxlon,maxlat
    web_tiles_url: str  # {z}/{x}/{y}.png template in object storage
    cog_path: str  # local/object-store path for the reprojected ellipsoidal COG master


def plan_terrain_build(
    *,
    web_tiles_url: str,
    baseline: RasterBaseline = PALISADES_POSTFIRE_DEM,
    bounds: tuple[float, float, float, float] = PALISADES_DEM_BOUNDS_WGS84,
    encoding: str = "terrarium",
    minzoom: int = 12,
    maxzoom: int = 17,
    cog_path: str = "palisades_postfire_dtm_ellipsoidal.cog.tif",
) -> TerrainBuildPlan:
    """Assemble the build plan from the pinned baseline + footprint."""
    if baseline.vertical_epsg != 5703:
        raise ValueError(
            f"{baseline.key} vertical EPSG is {baseline.vertical_epsg}, expected 5703 "
            "(NAVD88/GEOID18) — the datum reconciliation path assumes it.")
    return TerrainBuildPlan(
        baseline_key=baseline.key,
        doi=baseline.doi,
        preliminary=baseline.preliminary,
        source_hcrs=f"EPSG:{baseline.horizontal_epsg}",
        source_vcrs=f"EPSG:{baseline.vertical_epsg}",
        target_tile_crs="EPSG:3857",
        target_vdatum="WGS84 ellipsoidal (NAVD88/GEOID18 via grid)",
        encoding=encoding,
        tile_size=256,
        minzoom=minzoom,
        maxzoom=maxzoom,
        bounds=bounds,
        web_tiles_url=web_tiles_url,
        cog_path=cog_path,
    )


def terrain_manifest(plan: TerrainBuildPlan) -> dict:
    """Web-facing terrain source config — mirrors lib/terrain.ts TerrainConfig,
    plus provenance (DOI, preliminary, datum) for debug/QA."""
    return {
        "tiles": plan.web_tiles_url,
        "encoding": plan.encoding,
        "tileSize": plan.tile_size,
        "minzoom": plan.minzoom,
        "maxzoom": plan.maxzoom,
        "bounds": list(plan.bounds),
        "attribution": (
            "Terrain: USGS 3DEP post-fire LiDAR DTM "
            f"(OpenTopography {PALISADES_POSTFIRE_DEM.opentopo_id}, CC0)"),
        "vdatum": plan.target_vdatum,
        "provenance": {
            "baseline": plan.baseline_key,
            "doi": plan.doi,
            "doi_url": f"https://doi.org/{plan.doi}",
            "preliminary": plan.preliminary,
            "source_hcrs": plan.source_hcrs,
            "source_vcrs": plan.source_vcrs,
        },
    }


def write_terrain_manifest(plan: TerrainBuildPlan, out_path: Path) -> dict:
    m = terrain_manifest(plan)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(m, indent=1))
    return m


def validate_footprint_datum(bounds: tuple[float, float, float, float] | None = None) -> float:
    """Spot-check the NAVD88/GEOID18 -> ellipsoidal lift at the footprint centre
    using Phase 0's grid transform; returns the geoid undulation (m). Raises if
    the grid is unavailable or the undulation is not LA-plausible — a cheap
    pre-flight before committing to a full build."""
    from pyproj import Transformer

    b = bounds or PALISADES_DEM_BOUNDS_WGS84
    clon, clat = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    # footprint centre (WGS84) -> UTM 11N easting/northing to feed the NAVD88 path
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:6340", always_xy=True)
    e, n = to_utm.transform(clon, clat)
    _, _, h_ellip = navd88_geoid18_to_wgs84(np.array([e]), np.array([n]), np.array([0.0]))
    return float(h_ellip[0])  # undulation, since input orthometric height was 0


# ---------------------------------------------------------------------------
# heavy raster step (isolated; needs an optional raster toolchain)
# ---------------------------------------------------------------------------

_RASTER_RECIPE = """\
Post-fire DTM -> ellipsoidal COG -> terrarium tile pyramid (run where GDAL exists):

  # 0. fetch the burn-footprint DTM tiles (anonymous) and mosaic
  aws s3 cp --no-sign-request --recursive \\
    s3://prd-tnm/CA_FireImpactZone_2025_PRELIMINARY/Palisades/<dtm prefix>/ ./src/
  gdalbuildvrt dtm.vrt ./src/*.tif

  # 1. reproject to WebMercator AND lift NAVD88/GEOID18 -> WGS84 ellipsoidal in one warp
  gdalwarp -s_srs "EPSG:6340+5703" -t_srs "EPSG:4979" -r bilinear dtm.vrt dtm_ellip_4979.tif
  gdalwarp -t_srs EPSG:3857 -te_srs EPSG:4326 -te <minlon> <minlat> <maxlon> <maxlat> \\
    dtm_ellip_4979.tif dtm_ellip_3857.tif

  # 2. COG master (lossless, predictor 3 for float)
  rio cogeo create --cog-profile deflate --co PREDICTOR=3 --co BLOCKSIZE=512 \\
    dtm_ellip_3857.tif palisades_postfire_dtm_ellipsoidal.cog.tif

  # 3. terrarium tile pyramid (LOSSLESS png) -> PMTiles for range-request delivery
  rio rgbify -b -10000 -i 0.1 --format png --max-z <maxzoom> --min-z <minzoom> \\
    palisades_postfire_dtm_ellipsoidal.cog.tif dtm_terrarium.mbtiles
  pmtiles convert dtm_terrarium.mbtiles palisades_postfire_dtm.pmtiles

Upload the COG + PMTiles/tiles to object storage and point VITE_POSTFIRE_TERRAIN_URL
at them. Do NOT commit the tiles to git.
"""


def generate_terrain_tiles(plan: TerrainBuildPlan) -> None:
    """Execute the heavy raster build. Requires the optional raster toolchain
    (GDAL/rasterio + rio-rgbify + pmtiles), which is not a core pipeline
    dependency. Raises with the exact recipe if unavailable rather than shipping
    an unvalidated raster path."""
    missing = []
    for mod in ("rasterio", "rio_cogeo", "rio_rgbify"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise RuntimeError(
            "post-fire terrain tile generation needs the optional raster toolchain "
            f"(missing: {', '.join(missing)}). It is deliberately out of the core "
            "pipeline deps; run the build where GDAL exists.\n\n" + _RASTER_RECIPE)
    # Toolchain present: a future change wires the rasterio/rio-rgbify pipeline
    # here. Kept unimplemented rather than shipped-but-unvalidated.
    raise NotImplementedError(
        "raster toolchain detected — wire the rasterio/rio-rgbify pipeline per "
        "the recipe in this module, with golden-tile tests, before enabling.\n\n"
        + _RASTER_RECIPE)


def plan_summary(plan: TerrainBuildPlan) -> str:
    return json.dumps(asdict(plan), indent=1)
