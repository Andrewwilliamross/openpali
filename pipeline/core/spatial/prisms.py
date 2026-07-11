"""Renderable placeholder geometry for parcels without LARIAC 3D coverage.

ROADMAP D2: every one of the 5,877 destroyed parcels renders in 3D, honestly
labeled — a resident whose lot is invisible reads it as "my home doesn't
count". Two placeholder classes below the real LARIAC surfel models:

- **footprint extrusion** — the parcel's LARIAC building footprint(s)
  extruded by their published HEIGHT/ELEV into wall+roof prisms, then
  surfel-sampled. For lots the scene layer never modelled (the "184").
- **parcel prism** — the county parcel polygon extruded to a single-story
  massing default, ground elevation interpolated from already-reconstructed
  neighbours. For lots with no LARIAC footprint at all (the "717").

Placeholders are deliberately coarse (wider surfel spacing, capped counts):
the geometry is a *presence marker*, not a model. coverage.json and the UI
badge carry the semantic label so they can never masquerade as observations.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import shape
from shapely.ops import triangulate

from palisades.apn import normalize_apn
from palisades.arcgis import query_layer

from .geodesy import ecef_to_enu, ecef_to_wgs84, wgs84_to_ecef, enu_rotation
from .scene_client import FOOTPRINT_LAYER, GEOID_OFFSET_LA_M
from .schema import GaussianBatch
from .surfels import sample_faces_stratified

_FT_TO_M = 0.3048

PLACEHOLDER_SPACING_M = 1.8  # coarser than real surfels — these are markers
PLACEHOLDER_MAX_SURFELS = 1600
PARCEL_PRISM_HEIGHT_M = 4.5  # single-story massing default
# neutral grey; the web export's score tint replaces hue anyway, and grey
# keeps the luminance modulation flat (no fake architectural shading)
_PLACEHOLDER_RGBA = (185, 185, 190, 255)


# ---------------------------------------------------------------------------
# polygon → prism triangle soup (lon/lat/z → ECEF)
# ---------------------------------------------------------------------------


def polygon_prism_tris(poly, base_z: float, height: float) -> np.ndarray:
    """A shapely Polygon → (T, 3, 3) prism triangles in (lon°, lat°, z m).

    Walls from every ring (exterior + holes), two triangles per edge; a roof
    cap from Delaunay triangulation filtered to triangles inside the polygon
    (handles concave parcels; slivers outside the hull are discarded). No
    floor — it is never visible.
    """
    tris: list[np.ndarray] = []
    rings = [poly.exterior, *poly.interiors]
    z0, z1 = base_z, base_z + height
    for ring in rings:
        coords = np.asarray(ring.coords)
        for a, b in zip(coords[:-1], coords[1:]):
            if not np.any(a[:2] != b[:2]):
                continue
            a0 = np.array([a[0], a[1], z0])
            b0 = np.array([b[0], b[1], z0])
            a1 = np.array([a[0], a[1], z1])
            b1 = np.array([b[0], b[1], z1])
            tris.append(np.stack([a0, b0, b1]))
            tris.append(np.stack([a0, b1, a1]))
    cleaned = poly.buffer(0)
    for t in triangulate(cleaned):
        if not t.representative_point().within(cleaned):
            continue
        (x0, y0), (x1, y1), (x2, y2) = list(t.exterior.coords)[:3]
        tris.append(np.array([[x0, y0, z1], [x1, y1, z1], [x2, y2, z1]]))
    if not tris:
        return np.zeros((0, 3, 3))
    return np.stack(tris)


def _tris_to_ecef(tris_lonlat: np.ndarray) -> np.ndarray:
    flat = tris_lonlat.reshape(-1, 3)
    ecef = wgs84_to_ecef(flat[:, 0], flat[:, 1], flat[:, 2])
    return np.asarray(ecef, dtype=np.float64).reshape(-1, 3, 3)


def _sample_prism(tris_lonlat: np.ndarray, apn: str, source: str,
                  t_epoch: float) -> GaussianBatch | None:
    if len(tris_lonlat) == 0:
        return None
    lon0 = float(tris_lonlat[:, :, 0].mean())
    lat0 = float(tris_lonlat[:, :, 1].mean())
    tris_ecef = _tris_to_ecef(tris_lonlat)
    cols = np.tile(np.array(_PLACEHOLDER_RGBA, dtype=np.float64),
                   (len(tris_ecef), 3, 1))
    return sample_faces_stratified(
        tris_ecef, cols, enu_rotation(lon0, lat0),
        t_epoch=t_epoch, apn=normalize_apn(apn) or apn, source=source,
        spacing_m=PLACEHOLDER_SPACING_M, max_surfels=PLACEHOLDER_MAX_SURFELS)


# ---------------------------------------------------------------------------
# placeholder builders
# ---------------------------------------------------------------------------


def footprint_prism_batch(apn: str, *, t_epoch: float) -> GaussianBatch | None:
    """LARIAC footprint polygons extruded into renderable prism splats.

    Same source data as scene_client.extract_footprint_prior (cached 30 days)
    but emitted as kind='splats' so the web pipeline can stream it.
    """
    feats = query_layer(
        FOOTPRINT_LAYER, f"APN='{normalize_apn(apn)}'",
        out_fields="APN,BLD_ID,HEIGHT,ELEV", return_geometry=True,
        out_sr=4326, f="geojson", ttl_hours=24 * 30,
    )
    tris: list[np.ndarray] = []
    for f in feats:
        props = f.get("properties") or {}
        geom = f.get("geometry")
        if not geom or props.get("HEIGHT") in (None, 0):
            continue
        poly = shape(geom)
        elev_m = float(props.get("ELEV") or 0.0) * _FT_TO_M + GEOID_OFFSET_LA_M
        height_m = float(props["HEIGHT"]) * _FT_TO_M
        polys = poly.geoms if poly.geom_type == "MultiPolygon" else [poly]
        for p in polys:
            t = polygon_prism_tris(p, elev_m, height_m)
            if len(t):
                tris.append(t)
    if not tris:
        return None
    return _sample_prism(np.concatenate(tris), apn,
                         "lariac_footprint_extrusion", t_epoch)


def parcel_prism_batch(apn: str, parcel_geometry: dict, ground_z: float, *,
                       t_epoch: float) -> GaussianBatch | None:
    """County parcel polygon extruded to a default single-story massing."""
    if not parcel_geometry:
        return None
    poly = shape(parcel_geometry)
    polys = poly.geoms if poly.geom_type == "MultiPolygon" else [poly]
    tris: list[np.ndarray] = []
    for p in polys:
        t = polygon_prism_tris(p, ground_z, PARCEL_PRISM_HEIGHT_M)
        if len(t):
            tris.append(t)
    if not tris:
        return None
    return _sample_prism(np.concatenate(tris), apn, "parcel_prism", t_epoch)


# ---------------------------------------------------------------------------
# ground elevation from reconstructed neighbours
# ---------------------------------------------------------------------------


class GroundZSampler:
    """Ellipsoidal ground height from the store's existing reconstruction.

    Parcel-prism lots have no LARIAC footprint and therefore no published
    ELEV; their neighbours' splats carry true ellipsoidal heights, so the
    p15 height of the nearest reconstructed points is a robust ground proxy
    (low percentile rejects roofs/eaves; the fire area's lot pitch is dense
    enough that 250 m always finds neighbours).
    """

    def __init__(self, xyz_ecef: np.ndarray, *, subsample: int = 13,
                 k: int = 48, max_radius_m: float = 250.0) -> None:
        pts = np.asarray(xyz_ecef, dtype=np.float64)[::subsample]
        if len(pts) == 0:
            raise ValueError("GroundZSampler needs a non-empty store")
        centroid = pts.mean(axis=0)
        lon, lat, _ = ecef_to_wgs84(centroid[None, :])
        self._lon0, self._lat0 = float(lon[0]), float(lat[0])
        self._origin = centroid
        # plan distances in a single ENU frame (fine at metre scale for
        # neighbour search); heights as TRUE ellipsoidal h per point — using
        # the shared frame's ENU z would pick up ~d²/2R curvature error
        # (~11 m at the fire area's 12 km extent)
        enu = ecef_to_enu(pts, centroid, self._lon0, self._lat0)
        _, _, h = ecef_to_wgs84(pts)
        self._h = np.asarray(h, dtype=np.float64)
        self._tree = cKDTree(enu[:, :2])
        self._k = k
        self._max_r = max_radius_m
        self._h0 = float(np.median(self._h))

    def ground_z(self, lon: float, lat: float) -> float | None:
        """Ellipsoidal ground height at lon/lat, or None when out of range.

        Two rungs: dense local neighbours first (250 m), then a widened
        1.2 km ring for isolated canyon/bluff lots — LARIAC coverage gaps
        cluster spatially, so the lots that need prisms most are exactly the
        ones with no near neighbours. Residual slope error at the wide rung
        is bounded by the renderer's per-node terrain clamp (≤600 m nodes
        re-anchor content to the DEM).
        """
        p = wgs84_to_ecef(np.array([lon]), np.array([lat]), np.array([self._h0]))
        q = ecef_to_enu(np.asarray(p, dtype=np.float64).reshape(1, 3),
                        self._origin, self._lon0, self._lat0)[0, :2]
        for k, max_r in ((self._k, self._max_r), (24, 1200.0)):
            dist, idx = self._tree.query(q, k=k, distance_upper_bound=max_r)
            valid = np.isfinite(dist)
            if valid.sum() >= 6:
                # p15 of neighbour heights: rejects roofs/eaves, keeps ground
                return float(np.percentile(self._h[idx[valid]], 15))
        return None
