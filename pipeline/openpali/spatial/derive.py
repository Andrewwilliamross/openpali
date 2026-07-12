"""Derive renderer-ready products from the raw USGS DEM tiles (SPATIAL-001).

    raw GeoTIFF bytes (hash-verified from the object store)
      -> mosaic assembly + seam-continuity quality check
      -> vertical/horizontal datum normalization
         (EPSG:6340 + NAVD88(GEOID18) -> WGS84 ellipsoidal -> ECEF, via the
          grid-based transform in core.spatial.geodesy; guarded, never scalar)
      -> parcel attribution (county parcel polygons rasterized onto the DEM grid)
      -> surfel batch -> hierarchical splat tileset (core.spatial.splat_tiler)
      -> terrarium terrain PNG pyramid
      -> content-addressed upload + versioned asset registration with lineage

Times are kept distinct throughout: ``t_epoch``/acquisition_* carry the 2025
flight date (observation time); ``processed_at`` carries this derivation run;
retrieval time lives on the acquisition run. The tileset origin/geometry is
ellipsoidal-ECEF exactly like every other renderer asset.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.spatial.geodesy import (
    ecef_to_enu,
    navd88_geoid18_to_wgs84,
    wgs84_to_ecef,
)
from core.spatial.schema import GaussianBatch
from core.spatial.splat_tiler import tile_batch
from openpali.spatial.aoi import OBSERVATION_KIND, VINTAGE_SLOT, load_aoi
from openpali.spatial.registry import (
    add_relation,
    mark_ready,
    register_asset_version,
    version_id_from_hashes,
)
from openpali.spatial.usgs import (
    AOI_SUBJECT_ID,
    AOI_SUBJECT_TYPE,
    USGS_SOURCE_ID,
    raw_tile_assets,
)
from openpali.storage.objects import ObjectStore, RAW_BUCKET, SPATIAL_BUCKET

# v2: picking entries carry per-parcel lon/lat centers (renderer pick contract)
PROCESS_VERSION = "usgs-derive-v2"
SURFEL_ASSET_ID = "usgs-surfel-aoi"
TERRAIN_ASSET_ID = "usgs-terrain-aoi"
SURFEL_STRIDE = 3  # 0.5 m px * 3 = 1.5 m surfel spacing
TERRAIN_ZOOMS = tuple(range(13, 19))
PIXEL_M = 0.5
_SH_DC = 0.2820948


# ---------------------------------------------------------------------------
# mosaic
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Mosaic:
    height_m: np.ndarray  # (H, W) float32 NAVD88 orthometric; NaN where nodata
    utm_bounds: tuple[float, float, float, float]  # minE, minN, maxE, maxN
    raw_assets: list[dict]
    seam_quality: dict
    nodata_fraction: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.height_m.shape


def load_mosaic(session: Session, store: ObjectStore) -> Mosaic:
    """Assemble the AOI mosaic from hash-verified raw tile bytes."""

    from rasterio.io import MemoryFile

    aoi = load_aoi()
    assets = raw_tile_assets(session)
    if len(assets) != len(aoi.tiles):
        raise ValueError(
            f"expected {len(aoi.tiles)} registered raw DEM assets, found {len(assets)}; "
            "run spatial acquisition first"
        )
    min_e, min_n, max_e, max_n = aoi.utm_bounds
    width = round((max_e - min_e) / PIXEL_M)
    height = round((max_n - min_n) / PIXEL_M)
    mosaic = np.full((height, width), np.nan, dtype=np.float32)

    for asset in assets:
        key = asset["object_uri"].split("/", 3)[3]
        body = store.get_verified(RAW_BUCKET, key, asset["sha256"])
        with MemoryFile(body) as mem, mem.open() as src:
            data = src.read(1).astype(np.float32)
            nodata = src.nodata
            if nodata is not None:
                data[data == nodata] = np.nan
            tb = asset["transform"]["utm_bounds"]
            # cross-check: rasterio's parsed geotransform must equal the .tfw
            # georeference recorded at acquisition (residual == alignment truth)
            geo = asset["transform"]["georeference"]
            t = src.transform
            if abs(t.a - geo["pixel_size_x"]) > 1e-9 or abs(
                t.c - (geo["upper_left_center_x"] - geo["pixel_size_x"] / 2)
            ) > 0.01:
                raise ValueError(
                    f"{asset['asset_id']}: embedded geotransform disagrees with "
                    f"the acquired .tfw world file"
                )
        col0 = round((tb[0] - min_e) / PIXEL_M)
        row0 = round((max_n - tb[3]) / PIXEL_M)
        mosaic[row0:row0 + data.shape[0], col0:col0 + data.shape[1]] = data

    # seam continuity: elevation step across internal tile boundaries must look
    # like ordinary terrain gradient, not a datum/misplacement jump
    seams: list[float] = []
    for asset in assets:
        tb = asset["transform"]["utm_bounds"]
        col = round((tb[0] - min_e) / PIXEL_M)
        row = round((max_n - tb[3]) / PIXEL_M)
        if col > 0:
            step = np.nanmedian(np.abs(mosaic[:, col] - mosaic[:, col - 1]))
            seams.append(float(step))
        if row > 0:
            step = np.nanmedian(np.abs(mosaic[row, :] - mosaic[row - 1, :]))
            seams.append(float(step))
    interior = float(np.nanmedian(np.abs(np.diff(mosaic, axis=1))))
    seam_quality = {
        "median_seam_step_m": max(seams) if seams else 0.0,
        "median_interior_step_m": interior,
        "seams_checked": len(seams),
    }
    if seams and max(seams) > max(10 * interior, 1.0):
        raise ValueError(f"tile seam discontinuity: {seam_quality}")

    nodata_fraction = float(np.isnan(mosaic).mean())
    return Mosaic(
        height_m=mosaic,
        utm_bounds=(min_e, min_n, max_e, max_n),
        raw_assets=assets,
        seam_quality=seam_quality,
        nodata_fraction=nodata_fraction,
    )


# ---------------------------------------------------------------------------
# parcel attribution
# ---------------------------------------------------------------------------


def _parcel_grid(session: Session, mosaic: Mosaic) -> tuple[np.ndarray, list[str], dict]:
    """Rasterize current county parcel polygons onto the DEM grid.

    Returns (index grid int32 with -1 = no parcel, apn list, reconciliation).
    """

    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    aoi = load_aoi()
    ring = ", ".join(f"{lon} {lat}" for lon, lat in aoi.wgs84_polygon)
    rows = session.execute(
        text(
            "SELECT pv.apn, ST_AsGeoJSON(ST_Transform(pv.geometry, 6340)) AS geom, "
            "       pv.damage_class "
            "FROM civic.parcel_version pv "
            "WHERE pv.observed_to IS NULL AND pv.geometry IS NOT NULL "
            "  AND ST_Intersects(pv.geometry, "
            "        ST_GeomFromText(:aoi, 4326)) "
            "ORDER BY pv.apn"
        ),
        {"aoi": f"POLYGON(({ring}))"},
    ).all()
    apns = [r.apn for r in rows]
    destroyed = sum(
        1 for r in rows if (r.damage_class or "").startswith("Destroyed")
    )
    min_e, _, _, max_n = mosaic.utm_bounds
    transform = from_origin(min_e, max_n, PIXEL_M, PIXEL_M)
    shapes = [
        (json.loads(r.geom), i) for i, r in enumerate(rows) if r.geom
    ]
    grid = rasterize(
        shapes,
        out_shape=mosaic.shape,
        transform=transform,
        fill=-1,
        dtype="int32",
    ) if shapes else np.full(mosaic.shape, -1, dtype=np.int32)

    covered = len(np.unique(grid[grid >= 0]))
    reconciliation = {
        "parcels_intersecting_aoi": len(rows),
        "destroyed_parcels_in_aoi": destroyed,
        "aoi_frozen_destroyed_expected": aoi.destroyed_parcels_inside,
        "parcels_with_dem_coverage": covered,
        "coverage_fraction": round(covered / len(rows), 4) if rows else 0.0,
    }
    return grid, apns, reconciliation


# ---------------------------------------------------------------------------
# surfel derivation
# ---------------------------------------------------------------------------


def build_surfel_batch(
    mosaic: Mosaic,
    parcel_grid: np.ndarray,
    apns: list[str],
    *,
    stride: int = SURFEL_STRIDE,
    flight_epoch: float | None = None,
) -> GaussianBatch:
    h = mosaic.height_m.astype(np.float64)
    min_e, _, _, max_n = mosaic.utm_bounds

    # terrain normals in ENU from the DEM gradient (row index runs south)
    dz_de = np.gradient(h, PIXEL_M, axis=1)
    dz_dn = -np.gradient(h, PIXEL_M, axis=0)

    rr, cc = np.meshgrid(
        np.arange(stride // 2, h.shape[0], stride),
        np.arange(stride // 2, h.shape[1], stride),
        indexing="ij",
    )
    rr, cc = rr.ravel(), cc.ravel()
    elev = h[rr, cc]
    valid = np.isfinite(elev)
    rr, cc, elev = rr[valid], cc[valid], elev[valid]

    easting = min_e + (cc + 0.5) * PIXEL_M
    northing = max_n - (rr + 0.5) * PIXEL_M

    lon, lat, h_ell = navd88_geoid18_to_wgs84(easting, northing, elev)
    xyz = wgs84_to_ecef(lon, lat, h_ell)

    n_vec = np.stack(
        [-dz_de[rr, cc], -dz_dn[rr, cc], np.ones_like(elev)], axis=1
    )
    n_vec /= np.linalg.norm(n_vec, axis=1, keepdims=True)

    # quaternion rotating local +Z onto the surface normal (ENU frame)
    quat = np.stack(
        [1.0 + n_vec[:, 2], -n_vec[:, 1], n_vec[:, 0], np.zeros(len(n_vec))],
        axis=1,
    )
    quat /= np.linalg.norm(quat, axis=1, keepdims=True)

    # hillshade (az 315 deg, alt 45 deg) on neutral grey — the layer's meaning
    # ("post-fire bare earth") is carried by legend + metadata, not false color
    light = np.array([-0.5, 0.5, math.sqrt(0.5)])
    shade = np.clip(n_vec @ light, 0.0, 1.0)
    grey = 0.30 + 0.55 * shade
    rgb = np.stack([grey, grey, grey], axis=1)
    sh = ((rgb - 0.5) / _SH_DC).astype(np.float32)[:, None, :]

    spacing = stride * PIXEL_M
    scale = np.full((len(xyz), 3), spacing / 2.0, dtype=np.float32)
    scale[:, 2] = 0.05  # thin surfel; tiler enforces its thickness floor

    idx = parcel_grid[rr, cc]
    apn_arr = np.array([apns[i] if i >= 0 else "" for i in idx], dtype="<U10")

    if flight_epoch is None:
        flight_epoch = datetime(2025, 1, 21, tzinfo=timezone.utc).timestamp()
    return GaussianBatch(
        xyz_ecef=xyz,
        t_epoch=np.full(len(xyz), flight_epoch, dtype=np.float64),
        scale=scale,
        rot=quat.astype(np.float32),
        alpha=np.full(len(xyz), 0.95, dtype=np.float32),
        sh=sh,
        apn=apn_arr,
        kind="splats",
        source=USGS_SOURCE_ID,
    )


# ---------------------------------------------------------------------------
# terrain (terrarium PNG pyramid)
# ---------------------------------------------------------------------------

_R = 6378137.0


def _merc(lon: float, lat: float) -> tuple[float, float]:
    x = math.radians(lon) * _R
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * _R
    return x, y


def _tile_bounds_merc(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    world = 2 * math.pi * _R
    size = world / (1 << z)
    minx = -world / 2 + x * size
    maxy = world / 2 - y * size
    return minx, maxy - size, minx + size, maxy


def _tiles_for_bbox(z: int, west: float, south: float, east: float, north: float):
    world = 2 * math.pi * _R
    size = world / (1 << z)
    x0, y0 = _merc(west, north)
    x1, y1 = _merc(east, south)
    tx0 = int((x0 + world / 2) // size)
    tx1 = int((x1 + world / 2) // size)
    ty0 = int((world / 2 - y0) // size)
    ty1 = int((world / 2 - y1) // size)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            yield tx, ty


def _terrarium_encode(elev: np.ndarray) -> np.ndarray:
    v = np.clip(elev + 32768.0, 0.0, 65535.996)
    r = np.floor(v / 256.0)
    g = np.floor(v) % 256
    b = np.floor((v - np.floor(v)) * 256.0)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def build_terrain_tiles(mosaic: Mosaic, out_dir: Path, *,
                        zooms: tuple[int, ...] = TERRAIN_ZOOMS) -> dict:
    """Reproject the mosaic into a terrarium-encoded raster-dem pyramid."""

    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject
    from PIL import Image

    aoi = load_aoi()
    lons = [p[0] for p in aoi.wgs84_polygon]
    lats = [p[1] for p in aoi.wgs84_polygon]
    west, east, south, north = min(lons), max(lons), min(lats), max(lats)

    min_e, _, _, max_n = mosaic.utm_bounds
    src_transform = from_origin(min_e, max_n, PIXEL_M, PIXEL_M)
    src = mosaic.height_m
    finite = src[np.isfinite(src)]
    fill_value = float(np.median(finite))

    n_tiles = 0
    filled_total = 0.0
    for z in zooms:
        for tx, ty in _tiles_for_bbox(z, west, south, east, north):
            minx, miny, maxx, maxy = _tile_bounds_merc(z, tx, ty)
            dst = np.full((256, 256), np.nan, dtype=np.float32)
            dst_transform = from_origin(minx, maxy, (maxx - minx) / 256, (maxy - miny) / 256)
            reproject(
                source=src,
                destination=dst,
                src_transform=src_transform,
                src_crs="EPSG:6340",
                dst_transform=dst_transform,
                dst_crs="EPSG:3857",
                src_nodata=np.nan,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
            nan_frac = float(np.isnan(dst).mean())
            if nan_frac == 1.0:
                continue
            filled_total += nan_frac
            dst = np.where(np.isnan(dst), fill_value, dst)
            png = Image.fromarray(_terrarium_encode(dst))
            tile_path = out_dir / str(z) / str(tx) / f"{ty}.png"
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            buf = io.BytesIO()
            png.save(buf, "PNG")
            tile_path.write_bytes(buf.getvalue())
            n_tiles += 1

    return {
        "tiles": n_tiles,
        "zooms": list(zooms),
        "encoding": "terrarium",
        "vertical_datum_note": "heights remain NAVD88(GEOID18) orthometric",
        "edge_fill_value_m": fill_value,
        "mean_filled_fraction": round(filled_total / max(n_tiles, 1), 4),
    }


# ---------------------------------------------------------------------------
# orchestration: derive + upload + register
# ---------------------------------------------------------------------------


def _upload_dir(store: ObjectStore, local_dir: Path, prefix: str) -> tuple[int, int, str]:
    """Upload every file under local_dir; returns (files, bytes, combined sha)."""

    store.ensure_bucket(SPATIAL_BUCKET)
    shas: list[str] = []
    n_files = 0
    n_bytes = 0
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        body = path.read_bytes()
        sha = hashlib.sha256(body).hexdigest()
        rel = path.relative_to(local_dir).as_posix()
        media = "image/png" if rel.endswith(".png") else (
            "application/json" if rel.endswith(".json") else "application/octet-stream"
        )
        store.put_content(SPATIAL_BUCKET, f"{prefix}/{rel}", body, sha256=sha, media_type=media)
        shas.append(f"{rel}:{sha}")
        n_files += 1
        n_bytes += len(body)
    combined = hashlib.sha256("\n".join(shas).encode()).hexdigest()
    return n_files, n_bytes, combined


def derive_usgs_products(session: Session, store: ObjectStore) -> dict:
    """Full derivation for the AOI. Idempotent by content-derived version."""

    mosaic = load_mosaic(session, store)
    parcel_grid, apns, reconciliation = _parcel_grid(session, mosaic)

    raw_shas = sorted(a["sha256"] for a in mosaic.raw_assets)
    version_id = version_id_from_hashes(
        *raw_shas, PROCESS_VERSION, f"stride={SURFEL_STRIDE}",
        f"zooms={TERRAIN_ZOOMS[0]}-{TERRAIN_ZOOMS[-1]}",
    )
    acquisition_start = mosaic.raw_assets[0]["acquisition_start"]
    acquisition_end = mosaic.raw_assets[0]["acquisition_end"]
    processed_at = datetime.now(timezone.utc)
    aoi = load_aoi()

    batch = build_surfel_batch(mosaic, parcel_grid, apns)

    results: dict = {
        "version_id": version_id,
        "surfels": len(batch),
        "reconciliation": reconciliation,
        "seam_quality": mosaic.seam_quality,
    }

    transform_doc = {
        "pipeline": [
            "tfw georeference (EPSG:6340, 0.5 m)",
            "NAVD88(GEOID18) -> WGS84 ellipsoidal via us_noaa_g2018u0 grid "
            "(guarded: LA undulation band check)",
            "WGS84 -> ECEF; tileset root = ENU frame at batch centroid",
        ],
        "process_version": PROCESS_VERSION,
    }
    common = dict(
        subject_type=AOI_SUBJECT_TYPE,
        subject_id=AOI_SUBJECT_ID,
        vintage_slot=VINTAGE_SLOT,
        source_id=USGS_SOURCE_ID,
        observation_kind=OBSERVATION_KIND,
        rights_state="public_domain",
        horizontal_crs="EPSG:4979 (ECEF store; source EPSG:6340)",
        vertical_datum="WGS84 ellipsoidal (source NAVD88 GEOID18)",
        units="meters",
        transform=transform_doc,
        acquisition_start=acquisition_start,
        acquisition_end=acquisition_end,
        processed_at=processed_at,
        extent_wkt=aoi.extent_wkt,
        resolution_m=SURFEL_STRIDE * PIXEL_M,
    )

    # ---- surfel tileset ------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="usgs-surfel-") as tmp:
        tmp_path = Path(tmp)
        tiling = tile_batch(batch, tmp_path, leaf_max=14000, max_depth=9)

        # picking index (per-APN ENU bounding prism in the tileset frame)
        lon0, lat0 = tiling.origin_lonlat
        origin_ecef = wgs84_to_ecef(
            np.array(lon0), np.array(lat0), np.array(tiling.origin_alt_m)
        )
        enu = ecef_to_enu(batch.xyz_ecef, origin_ecef, lon0, lat0)
        from core.spatial.geodesy import ecef_to_wgs84

        picking: dict[str, dict] = {}
        order = np.argsort(batch.apn, kind="stable")
        sorted_apn = batch.apn[order]
        boundaries = np.flatnonzero(sorted_apn[1:] != sorted_apn[:-1]) + 1
        for g in np.split(order, boundaries):
            apn = str(batch.apn[g[0]])
            if not apn:
                continue
            pts = enu[g]
            lo, hi = pts.min(axis=0), pts.max(axis=0)
            clon, clat, _ = ecef_to_wgs84(batch.xyz_ecef[g].mean(axis=0)[None, :])
            picking[apn] = {
                "bbox": [round(float(v), 2) for v in (*lo, *hi)],
                "lon": round(float(clon[0]), 6),
                "lat": round(float(clat[0]), 6),
                "n": int(len(g)),
            }
        (tmp_path / "picking.json").write_text(json.dumps(picking))

        # geoid offset at the tileset origin (renderer datum contract:
        # AMSL = ellipsoidal - geoid_offset; ~ -36 m at the Palisades)
        min_e, min_n, max_e, max_n = mosaic.utm_bounds
        _, _, h_ell0 = navd88_geoid18_to_wgs84(
            np.array([(min_e + max_e) / 2]), np.array([(min_n + max_n) / 2]),
            np.array([0.0]),
        )
        geoid_offset_m = round(float(h_ell0[0]), 3)

        asset_manifest = {
            "asset_id": SURFEL_ASSET_ID,
            "version_id": version_id,
            "tileset": "tileset.json",
            "picking": "picking.json",
            "origin": {"lon": lon0, "lat": lat0, "alt_ellipsoidal_m": tiling.origin_alt_m},
            "geoid_offset_m": geoid_offset_m,
            "observation_kind": OBSERVATION_KIND,
            "acquired": aoi.acquisition_date,
            "vintage_slot": VINTAGE_SLOT,
            "source": USGS_SOURCE_ID,
            "rights_state": "public_domain",
            "splats": len(batch),
            "parcels": len(picking),
            "nodes": tiling.n_nodes,
            "levels": tiling.levels,
        }
        (tmp_path / "manifest.json").write_text(json.dumps(asset_manifest, indent=1))

        prefix = f"assets/{SURFEL_ASSET_ID}/{version_id}"
        n_files, n_bytes, combined = _upload_dir(store, tmp_path, prefix)

    register_asset_version(
        session,
        asset_id=SURFEL_ASSET_ID,
        version_id=version_id,
        asset_kind="surfel_tiles",
        registration_residual_m=mosaic.seam_quality["median_seam_step_m"],
        coverage={
            "tiles": tiling.n_nodes,
            "parcels_with_geometry": len(picking),
            **reconciliation,
        },
        quality={
            "content_units": len(batch),
            "seam": mosaic.seam_quality,
            "nodata_fraction": mosaic.nodata_fraction,
            "bytes": n_bytes,
            "files": n_files,
        },
        lineage=[
            {"kind": "derived_from", "asset_id": a["asset_id"], "version_id": a["version_id"]}
            for a in mosaic.raw_assets
        ],
        object_uri=f"s3://{SPATIAL_BUCKET}/{prefix}/manifest.json",
        object_sha256=combined,
        format_version="3dtiles-splat-v1",
        **common,
    )
    for a in mosaic.raw_assets:
        add_relation(
            session,
            from_asset=(SURFEL_ASSET_ID, version_id),
            to_asset=(a["asset_id"], a["version_id"]),
            relation="derived_from",
            detail={"process_version": PROCESS_VERSION},
        )
    mark_ready(session, SURFEL_ASSET_ID, version_id)
    results["surfel_asset"] = {"files": n_files, "bytes": n_bytes, "prefix": prefix}

    # ---- terrain pyramid -----------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="usgs-terrain-") as tmp:
        tmp_path = Path(tmp)
        terrain_stats = build_terrain_tiles(mosaic, tmp_path)
        terrain_manifest = {
            "asset_id": TERRAIN_ASSET_ID,
            "version_id": version_id,
            "tile_url_template": "{z}/{x}/{y}.png",
            **terrain_stats,
            "observation_kind": OBSERVATION_KIND,
            "acquired": aoi.acquisition_date,
            "vintage_slot": VINTAGE_SLOT,
        }
        (tmp_path / "manifest.json").write_text(json.dumps(terrain_manifest, indent=1))
        prefix = f"assets/{TERRAIN_ASSET_ID}/{version_id}"
        n_files, n_bytes, combined = _upload_dir(store, tmp_path, prefix)

    register_asset_version(
        session,
        asset_id=TERRAIN_ASSET_ID,
        version_id=version_id,
        asset_kind="terrain_rgb",
        registration_residual_m=mosaic.seam_quality["median_seam_step_m"],
        coverage={"tiles": terrain_stats["tiles"], **reconciliation},
        quality={
            "content_units": terrain_stats["tiles"],
            "encoding": "terrarium",
            "vertical_datum_note": terrain_stats["vertical_datum_note"],
            "mean_filled_fraction": terrain_stats["mean_filled_fraction"],
            "bytes": n_bytes,
        },
        lineage=[
            {"kind": "derived_from", "asset_id": a["asset_id"], "version_id": a["version_id"]}
            for a in mosaic.raw_assets
        ],
        object_uri=f"s3://{SPATIAL_BUCKET}/{prefix}/manifest.json",
        object_sha256=combined,
        format_version="terrarium-png",
        **{**common, "vertical_datum": "NAVD88 (GEOID18) orthometric",
           "resolution_m": PIXEL_M},
    )
    for a in mosaic.raw_assets:
        add_relation(
            session,
            from_asset=(TERRAIN_ASSET_ID, version_id),
            to_asset=(a["asset_id"], a["version_id"]),
            relation="derived_from",
            detail={"process_version": PROCESS_VERSION},
        )
    mark_ready(session, TERRAIN_ASSET_ID, version_id)
    results["terrain_asset"] = {"files": n_files, "bytes": n_bytes, "prefix": prefix,
                                **terrain_stats}
    session.flush()
    return results
