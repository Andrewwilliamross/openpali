"""Export the spatial store to web-streamable assets.

Produces, under web/public/tiles/palisades/:

    tileset.json + L<n>/<x>_<y>_<z>.splat    the LOD pyramid (splat_tiler)
    picking.json                              APN → ENU bounding prism index,
                                              shared origin with the tileset —
                                              powers 3D click→parcel resolution
    manifest.json                             origin / datum / stats for the client

Vertical datum note: store heights are WGS84-ellipsoidal; MapLibre terrain DEMs
are orthometric (AMSL). The manifest carries the constant local geoid offset so
the client can clamp against `queryTerrainElevation` correctly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .geodesy import ecef_to_enu, ecef_to_wgs84, wgs84_to_ecef
from .scene_client import GEOID_OFFSET_LA_M
from .schema import GaussianBatch, SpatialStore
from .splat_tiler import tile_batch

WEB_TILES_DIR = Path(__file__).resolve().parents[3] / "web" / "public" / "tiles" / "palisades"


# the map's score→color ramp (mirror of web/src/lib/colors.ts SCORE_STOPS)
SCORE_STOPS = [
    (0, (0x99, 0x00, 0x0D)), (8, (0xCB, 0x18, 0x1D)), (15, (0xF0, 0x5E, 0x3D)),
    (30, (0xFD, 0x8D, 0x3C)), (40, (0xFD, 0xC2, 0x3C)), (50, (0xD0, 0xD9, 0x43)),
    (65, (0xA4, 0xCF, 0x3F)), (80, (0x66, 0xBB, 0x52)), (92, (0x3D, 0x9F, 0x47)),
    (100, (0x1B, 0x78, 0x37)),
]
_SH_DC = 0.2820948


def _score_rgb(score: float) -> np.ndarray:
    s = max(0.0, min(100.0, score))
    for i in range(len(SCORE_STOPS) - 1, -1, -1):
        stop, c = SCORE_STOPS[i]
        if s >= stop:
            if i == len(SCORE_STOPS) - 1:
                return np.array(c, dtype=np.float64) / 255.0
            nstop, nc = SCORE_STOPS[i + 1]
            t = (s - stop) / (nstop - stop)
            a = np.array(c, dtype=np.float64)
            b = np.array(nc, dtype=np.float64)
            return (a + (b - a) * t) / 255.0
    return np.array(SCORE_STOPS[0][1], dtype=np.float64) / 255.0


def _apply_score_tint(batch: GaussianBatch, parcels_geojson: Path) -> int:
    """Tint each parcel's splats by its rebuild score, modulated by the LARIAC
    vertex-colour luminance so roof/wall shading still reads in 3D. The scene
    layer's own vertex colours encode DINS damage (all destroyed = red), which
    is redundant with the parcel layer — the score gradient is the product."""
    if not parcels_geojson.exists():
        return 0
    feats = json.loads(parcels_geojson.read_text())["features"]
    scores = {
        f["properties"]["apn"]: float(s)
        for f in feats
        if (s := f["properties"].get("score")) is not None
    }

    batch.sh = batch.sh.copy()  # arrow-backed arrays are read-only

    rgb = np.clip(0.5 + batch.sh[:, 0, :].astype(np.float64) * _SH_DC, 0.0, 1.0)
    lum = (0.299 * rgb[:, 0] + 0.587 * rgb[:, 1] + 0.114 * rgb[:, 2])
    # luminance modulation band keeps geometric shading without washing the hue
    mod = 0.55 + 0.45 * lum

    tinted = 0
    untinted = 0
    grey = np.array([0.45, 0.45, 0.47])  # "no data" — distinct from score-0 red
    apns = batch.apn
    order = np.argsort(apns, kind="stable")
    sorted_apn = apns[order]
    boundaries = np.flatnonzero(sorted_apn[1:] != sorted_apn[:-1]) + 1
    for g in np.split(order, boundaries):
        apn = str(apns[g[0]])
        score = scores.get(apn)
        if score is None:
            # un-scored parcels must NOT keep the source's DINS-red vertex
            # colours (indistinguishable from score≈0) — neutral grey instead
            base = grey
            untinted += len(g)
        else:
            base = _score_rgb(score)
            tinted += len(g)
        out = base[None, :] * mod[g][:, None]
        batch.sh[g, 0, :] = ((out - 0.5) / _SH_DC).astype(np.float32)
    if untinted:
        print(f"  warning: {untinted} splats on parcels without a rebuild score (grey)")
    return tinted


def export_web_tiles(store_root: Path, out_dir: Path = WEB_TILES_DIR, *,
                     leaf_max: int = 14000, max_depth: int = 9) -> dict:
    store = SpatialStore(root=store_root)
    batch = store.read(kind="splats")
    if batch is None or len(batch) == 0:
        raise ValueError("store has no splat primitives to export")

    parcels_geojson = out_dir.parents[1] / "data" / "parcels.geojson"
    tinted = _apply_score_tint(batch, parcels_geojson)

    out_dir.mkdir(parents=True, exist_ok=True)
    result = tile_batch(batch, out_dir, leaf_max=leaf_max, max_depth=max_depth)

    # ---- picking index: per-APN ENU bounding prism in the tileset's frame ----
    lon0, lat0 = result.origin_lonlat
    origin_ecef = wgs84_to_ecef(np.array(lon0), np.array(lat0), np.array(result.origin_alt_m))
    enu = ecef_to_enu(batch.xyz_ecef, origin_ecef, lon0, lat0)

    apns = batch.apn
    order = np.argsort(apns, kind="stable")
    sorted_apn = apns[order]
    boundaries = np.flatnonzero(sorted_apn[1:] != sorted_apn[:-1]) + 1
    groups = np.split(order, boundaries)

    picking: dict[str, dict] = {}
    for g in groups:
        apn = str(apns[g[0]])
        pts = enu[g]
        lo = pts.min(axis=0)
        hi = pts.max(axis=0)
        lon, lat, _ = ecef_to_wgs84(batch.xyz_ecef[g].mean(axis=0)[None, :])
        picking[apn] = {
            "bbox": [round(float(v), 2) for v in (*lo, *hi)],
            "lon": round(float(lon[0]), 6),
            "lat": round(float(lat[0]), 6),
            "n": int(len(g)),
        }
    (out_dir / "picking.json").write_text(json.dumps(picking))

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tileset": "tileset.json",
        "picking": "picking.json",
        "origin": {"lon": lon0, "lat": lat0, "alt_ellipsoidal_m": result.origin_alt_m},
        # AMSL = ellipsoidal − geoid_offset  (offset is negative in LA)
        "geoid_offset_m": GEOID_OFFSET_LA_M,
        "splats": int(len(batch)),
        "splats_score_tinted": tinted,
        "parcels": len(picking),
        "nodes": result.n_nodes,
        "levels": result.levels,
        "bytes": result.total_bytes,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


if __name__ == "__main__":
    import sys

    from .runner import DEFAULT_STORE

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_STORE
    m = export_web_tiles(root)
    print(json.dumps(m, indent=1))
