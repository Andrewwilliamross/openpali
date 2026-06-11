"""LARIAC 3D building extraction — the geometric baseline prior per parcel.

Primary path (verified live, June 2026): direct I3S 1.10 extraction from LA
County eGIS's `Palisades_3D_Buildings` SceneServer. The layer's *uncompressed*
geometry buffer (index 0) needs no Draco decoder and the layer carries
AIN / APN / HEIGHT / DINS-damage attributes natively, so per-parcel extraction
requires no spatial join at all.

I3S specifics this client relies on (all curl-verified):
- store wkid 4326, vcsWkid 5773 (EGM96): vertex positions are Float32 offsets
  from the node's `obb.center`, x/y in **degrees**, z in **metres orthometric**.
- geometry buffer 0 layout (gzip-wrapped):  UInt32 vertexCount, UInt32
  featureCount, then per-attribute arrays position(f32×3) → normal(f32×3) →
  uv0(f32×2) → color(u8×4), then featureIds (u64×fc), faceRanges (u32×2×fc).
  Vertices are a triangle soup: faceRange [t0, t1] ⇒ vertices [3·t0, 3·(t1+1)).
- attribute buffers (`nodes/<R>/attributes/<key>/0`, gzip-wrapped):
  strings: UInt32 count, UInt32 totalBytes, UInt32 lengths[count], bytes;
  numerics: UInt32 count, padding to value alignment, values[count].
- tiles.arcgis.com serves gzip bodies regardless of Accept-Encoding for the
  binary resources — sniff the 1f 8b magic and decompress manually.

Fallback path: extruded LARIAC footprints (polygons + HEIGHT/ELEV) from
`WildFire_Palisades_DINS_Plus_BuildingOutlines_VIEW`, which also carries APN.

Heights: EGM96 orthometric → ellipsoidal via a constant local geoid
undulation (the EGM96 geoid sits ≈35.6 m below the WGS84 ellipsoid across the
Palisades; sub-metre variation over the fire footprint is irrelevant at our
registration tolerances).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

from palisades.apn import normalize_apn
from palisades.http import RAW_DIR, USER_AGENT

from .geodesy import wgs84_to_ecef
from .schema import GaussianBatch
from .surfels import surfels_from_vertices

SCENE_LAYER = (
    "https://tiles.arcgis.com/tiles/RmCCgQtiZLDCtblq/arcgis/rest/services/"
    "Palisades_3D_Buildings/SceneServer/layers/0"
)
FOOTPRINT_LAYER = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
    "WildFire_Palisades_DINS_Plus_BuildingOutlines_VIEW/FeatureServer/0"
)

GEOID_OFFSET_LA_M = -35.6  # EGM96 undulation at ~34.04N, -118.53E
_FT_TO_M = 0.3048

_NUMERIC_FMT = {
    "Int16": ("<i2", 2), "Int32": ("<i4", 4), "Int64": ("<i8", 8),
    "UInt16": ("<u2", 2), "UInt32": ("<u4", 4), "UInt64": ("<u8", 8),
    "Float32": ("<f4", 4), "Float64": ("<f8", 8), "Oid32": ("<i4", 4),
}


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:24]
    return RAW_DIR / "scene" / f"{digest}.bin"


def _get_bytes(client: httpx.Client, url: str, *, ttl_forever: bool = True) -> bytes:
    """Cached binary GET with transparent gunzip (scene assets are immutable)."""
    path = _cache_path(url)
    if path.exists() and ttl_forever:
        return path.read_bytes()
    resp = client.get(url)
    resp.raise_for_status()
    data = resp.content
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


@dataclass
class NodeMesh:
    """One leaf node's decoded geometry + per-feature attribute alignment."""

    positions_lonlat_h: np.ndarray  # (vc, 3) lon°, lat°, h_m (ellipsoidal)
    feature_ids: np.ndarray  # (fc,) uint64
    face_ranges: np.ndarray  # (fc, 2) uint32 triangle ranges
    apns: list[str]  # (fc,) normalized APNs, index-aligned

    def vertices_for_feature(self, i: int) -> np.ndarray:
        t0, t1 = self.face_ranges[i]
        return self.positions_lonlat_h[3 * int(t0): 3 * (int(t1) + 1)]


class SceneClient:
    """I3S client for the Palisades 3D buildings layer."""

    def __init__(self, layer_url: str = SCENE_LAYER) -> None:
        self.layer_url = layer_url.rstrip("/")
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
            timeout=httpx.Timeout(120.0, connect=20.0),
            follow_redirects=True,
        )
        self._layer_info: dict | None = None
        self._attr_keys: dict[str, str] | None = None

    # ---- layer metadata ----

    def layer_info(self) -> dict:
        if self._layer_info is None:
            raw = _get_bytes(self._client, f"{self.layer_url}?f=json")
            self._layer_info = json.loads(raw)
        return self._layer_info

    def attribute_keys(self) -> dict[str, str]:
        """field name → attribute resource key (e.g. 'APN' → 'f_7')."""
        if self._attr_keys is None:
            info = self.layer_info()
            self._attr_keys = {a["name"]: a["key"] for a in info["attributeStorageInfo"]}
        return self._attr_keys

    # ---- node traversal ----

    def _nodepage(self, page: int) -> dict:
        raw = _get_bytes(self._client, f"{self.layer_url}/nodepages/{page}?f=json")
        return json.loads(raw)

    def iter_leaf_nodes(self) -> list[dict]:
        """All leaf nodes (no children) that carry mesh geometry."""
        info = self.layer_info()
        per_page = info["nodePages"]["nodesPerPage"]
        leaves: list[dict] = []
        page = 0
        seen = 0
        total: int | None = None
        while total is None or seen < total:
            try:
                np_json = self._nodepage(page)
            except httpx.HTTPStatusError:
                break  # ran off the end (total not always advertised)
            nodes = np_json.get("nodes", [])
            if not nodes:
                break
            for node in nodes:
                seen += 1
                if not node.get("children") and node.get("mesh"):
                    leaves.append(node)
            if len(nodes) < per_page:
                break
            page += 1
        return leaves

    # ---- binary decoding ----

    def _node_geometry(self, resource: int
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Decode buffer 0: positions, normals, vertex colors, featureIds, faceRanges.

        Verified layout: header(8) · position f32×3 · normal f32×3 · uv0 f32×2 ·
        color u8×4 (per-vertex blocks), then featureId u64 and faceRange u32×2
        (per-feature blocks).
        """
        buf = _get_bytes(self._client, f"{self.layer_url}/nodes/{resource}/geometries/0")
        vc, fc = struct.unpack_from("<II", buf, 0)
        expected = 8 + vc * 36 + fc * 16
        if len(buf) < expected:
            raise ValueError(
                f"geometry buffer node {resource}: {len(buf)} bytes < expected {expected}")
        off = 8
        positions = np.frombuffer(buf, dtype="<f4", count=vc * 3, offset=off).reshape(vc, 3)
        off += vc * 12
        normals = np.frombuffer(buf, dtype="<f4", count=vc * 3, offset=off).reshape(vc, 3)
        off += vc * 12 + vc * 8  # skip uv0
        colors = np.frombuffer(buf, dtype="u1", count=vc * 4, offset=off).reshape(vc, 4)
        feat_off = 8 + vc * 36
        feature_ids = np.frombuffer(buf, dtype="<u8", count=fc, offset=feat_off)
        fr_off = feat_off + fc * 8
        face_ranges = np.frombuffer(buf, dtype="<u4", count=fc * 2, offset=fr_off).reshape(fc, 2)
        return (positions.astype(np.float64), normals.astype(np.float64),
                colors, feature_ids, face_ranges)

    def _node_string_attribute(self, resource: int, key: str) -> list[str]:
        buf = _get_bytes(self._client, f"{self.layer_url}/nodes/{resource}/attributes/{key}/0")
        count, total_bytes = struct.unpack_from("<II", buf, 0)
        lengths = np.frombuffer(buf, dtype="<u4", count=count, offset=8)
        blob = buf[8 + 4 * count: 8 + 4 * count + total_bytes]
        out: list[str] = []
        pos = 0
        for ln in lengths:
            s = blob[pos: pos + int(ln)]
            out.append(s.rstrip(b"\x00").decode("utf-8", "replace"))
            pos += int(ln)
        return out

    def node_mesh(self, node: dict) -> NodeMesh:
        """Decode one leaf node into world-space vertices + APN alignment."""
        resource = node["mesh"]["geometry"]["resource"]
        positions, _normals, _colors, feature_ids, face_ranges = self._node_geometry(resource)
        center = np.asarray(node["obb"]["center"], dtype=np.float64)  # lon, lat, z
        world = positions + center  # f32 offsets about the OBB centre
        world[:, 2] += GEOID_OFFSET_LA_M  # EGM96 orthometric → WGS84 ellipsoidal
        apn_key = self.attribute_keys()["APN"]
        apns_raw = self._node_string_attribute(resource, apn_key)
        apns = [normalize_apn(a) or "" for a in apns_raw]
        if len(apns) != len(feature_ids):
            raise ValueError(
                f"node {resource}: attribute count {len(apns)} != features {len(feature_ids)}")
        return NodeMesh(world, feature_ids, face_ranges, apns)

    # ---- the public extraction API ----

    def build_apn_index(self, cache_path: Path | None = None) -> dict[str, list[int]]:
        """One-time scan: APN → list of leaf-node geometry resources containing it.

        Cached to disk — the scene layer is a static post-fire snapshot, so the
        index never goes stale until the layer's store version changes.
        """
        cache = cache_path or (RAW_DIR / "scene" / "apn_node_index.json")
        store_version = str(self.layer_info().get("store", {}).get("version", ""))
        if cache.exists():
            data = json.loads(cache.read_text())
            if data.get("_store_version") == store_version:
                return {k: v for k, v in data.items() if not k.startswith("_")}
        index: dict[str, list[int]] = {}
        for node in self.iter_leaf_nodes():
            resource = node["mesh"]["geometry"]["resource"]
            apn_key = self.attribute_keys()["APN"]
            try:
                apns = self._node_string_attribute(resource, apn_key)
            except (httpx.HTTPError, ValueError, struct.error):
                continue  # node without attributes — skip, never abort the scan
            for a in apns:
                norm = normalize_apn(a)
                if norm:
                    index.setdefault(norm, [])
                    if resource not in index[norm]:
                        index[norm].append(resource)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"_store_version": store_version, **index}))
        return index

    def extract_parcel_prior(self, apn: str, node_resources: list[int],
                             *, t_epoch: float) -> GaussianBatch | None:
        """Extract `apn`'s mesh as oriented, coloured SURFEL splats.

        Triangle-soup vertices are deduplicated (cm grid), then each surviving
        vertex becomes a disk-shaped Gaussian: oriented by its surface normal,
        sized by the local vertex spacing, coloured by the LARIAC vertex colour
        (DC spherical-harmonics band). Render-ready for the web splat layer.
        """
        target = normalize_apn(apn)
        v_chunks: list[np.ndarray] = []
        n_chunks: list[np.ndarray] = []
        c_chunks: list[np.ndarray] = []
        for resource in node_resources:
            positions, normals, colors, feature_ids, face_ranges = self._node_geometry(resource)
            apn_key = self.attribute_keys()["APN"]
            apns = [normalize_apn(a) or "" for a in self._node_string_attribute(resource, apn_key)]
            center = self._node_obb_center(resource)
            world = positions + center
            world[:, 2] += GEOID_OFFSET_LA_M
            for i, a in enumerate(apns):
                if a != target:
                    continue
                t0, t1 = face_ranges[i]
                sl = slice(3 * int(t0), 3 * (int(t1) + 1))
                v_chunks.append(world[sl])
                n_chunks.append(normals[sl])
                c_chunks.append(colors[sl])
        if not v_chunks:
            return None
        verts = np.concatenate(v_chunks)
        norms = np.concatenate(n_chunks)
        cols = np.concatenate(c_chunks)

        # frame guard: surfel orientation assumes ENU UNIT normals. A frame or
        # layout drift upstream (the I3S spec also allows earth-centred and
        # vertex-reference frames) would silently survive the downstream
        # renormalisation — catch the unit-norm violation here instead.
        nrm = np.linalg.norm(norms, axis=1)
        med = float(np.median(nrm)) if len(nrm) else 1.0
        if not (0.95 < med < 1.05):
            raise ValueError(
                f"I3S normals are not unit vectors (median |n|={med:.4f}) — "
                "normalReferenceFrame may have changed; refusing to orient surfels")

        # dedupe the triangle soup on a ~1 cm grid (keeps one normal/colour each)
        key = np.round(verts / np.array([1e-7, 1e-7, 0.01])).astype(np.int64)  # deg,deg,m
        _, keep_idx = np.unique(key, axis=0, return_index=True)
        verts, norms, cols = verts[keep_idx], norms[keep_idx], cols[keep_idx]

        xyz = wgs84_to_ecef(verts[:, 0], verts[:, 1], verts[:, 2])
        return surfels_from_vertices(xyz, norms, cols, t_epoch=t_epoch,
                                     apn=target, source="lariac_scene")

    _obb_cache: dict[int, np.ndarray] | None = None

    def _node_obb_center(self, resource: int) -> np.ndarray:
        """Geometry-resource → OBB centre, built once from the nodepage walk."""
        if self._obb_cache is None:
            self._obb_cache = {}
            for node in self.iter_leaf_nodes():
                r = node["mesh"]["geometry"]["resource"]
                self._obb_cache[r] = np.asarray(node["obb"]["center"], dtype=np.float64)
        if resource not in self._obb_cache:
            raise KeyError(f"unknown geometry resource {resource}")
        return self._obb_cache[resource]


# ---------------------------------------------------------------------------
# fallback: extruded LARIAC footprints
# ---------------------------------------------------------------------------


def extract_footprint_prior(apn: str, *, t_epoch: float,
                            density_m: float = 1.5) -> GaussianBatch | None:
    """Extrude the parcel's LARIAC footprint(s) into a wall+roof point prior.

    Used when a parcel has no scene-layer coverage. HEIGHT/ELEV arrive in feet
    (LARIAC publication units) and are converted explicitly.
    """
    from shapely.geometry import shape

    from palisades.arcgis import query_layer

    feats = query_layer(
        FOOTPRINT_LAYER, f"APN='{normalize_apn(apn)}'",
        out_fields="APN,BLD_ID,HEIGHT,ELEV", return_geometry=True,
        out_sr=4326, f="geojson", ttl_hours=24 * 30,
    )
    pts: list[np.ndarray] = []
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
            ring = np.asarray(p.exterior.coords)
            # densify ring edges to ~density_m spacing (degrees ≈ m / 111e3)
            step = density_m / 111_000.0
            dense: list[np.ndarray] = []
            for a, b in zip(ring[:-1], ring[1:]):
                seg = np.linalg.norm(b - a)
                n = max(int(seg / step), 1)
                t = np.linspace(0, 1, n, endpoint=False)[:, None]
                dense.append(a + t * (b - a))
            ring_d = np.concatenate(dense)
            for frac in (0.0, 0.5, 1.0):  # base, mid-wall, eave
                level = np.column_stack([
                    ring_d, np.full(len(ring_d), elev_m + frac * height_m)])
                pts.append(level)
    if not pts:
        return None
    verts = np.concatenate(pts)
    xyz = wgs84_to_ecef(verts[:, 0], verts[:, 1], verts[:, 2])
    return GaussianBatch.from_points(
        xyz, t_epoch, normalize_apn(apn) or apn,
        kind="mesh_vertices", source="lariac_footprint_extrusion")
