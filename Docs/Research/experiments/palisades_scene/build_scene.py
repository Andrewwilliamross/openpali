"""Compile a dated, independently addressable Palisades scene experiment.

Requires the repository Python environment, Node, draco3d 1.5.7 and two
explicit PROJ grids. Run --help. Downloads ONE building node, not Los Angeles.
The resulting preview makes display choices, never physical-condition claims.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import ssl
import struct
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import certifi
import laspy
import numpy as np
import pyproj
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'pipeline'))
from core.spatial.geodesy import enu_rotation, wgs84_to_ecef

SCENE = ('https://tiles.arcgis.com/tiles/RmCCgQtiZLDCtblq/arcgis/rest/services/'
         'Palisades_3D_Buildings/SceneServer')
ITEM = 'https://www.arcgis.com/sharing/rest/content/items/d4018709bc26465daf33abe15b25d1e9?f=json'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, cache: Path, records: dict) -> bytes:
    path = cache / (digest(url.encode()) + '.bin')
    if path.exists():
        raw = path.read_bytes()
    else:
        request = urllib.request.Request(url, headers={'User-Agent': 'OpenPali-scene-research/1'})
        with urllib.request.urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=30) as response:
            raw = response.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        # ArcGIS may return an error body with HTTP 200. Do not cache it as geometry.
        if raw.lstrip().startswith(b'{'):
            # A binary I3S string attribute with featureCount=123 also starts
            # with '{'. A leading byte alone does not identify JSON.
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                payload = None
            if isinstance(payload, dict) and 'error' in payload:
                raise ValueError(f'{url}: {payload["error"]}')
        path.write_bytes(raw)
    records[url] = {'sha256': digest(raw), 'bytes': len(raw), 'path': str(path.relative_to(ROOT))}
    return raw


def strings(raw: bytes) -> list[str]:
    count, size = struct.unpack_from('<II', raw)
    lengths = np.frombuffer(raw, '<u4', count=count, offset=8)
    if len(raw) != 8 + count * 4 + size or int(lengths.sum()) != size:
        raise ValueError('Invalid I3S string buffer length')
    blob, offset, result = raw[8 + count * 4:], 0, []
    for length in lengths:
        result.append(blob[offset:offset + int(length)].rstrip(b'\0').decode('utf-8'))
        offset += int(length)
    return result


def grid_transformers(grids: Path):
    # Explicit grids prevent silent vertical passthrough. No network grid lookup.
    egm, geo18 = grids / 'us_nga_egm96_15.tif', grids / 'us_noaa_g2018u0.tif'
    for path in [egm, geo18]:
        if not path.is_file():
            raise ValueError(f'Missing required vertical grid: {path}')
    # +multiplier=1 matches the inverse-height operations selected by PROJ's
    # EPSG database for these grids. vgridshift defaults to -1, so be explicit.
    def vertical(path):
        return pyproj.Transformer.from_pipeline(
            '+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad '
            f'+step +proj=vgridshift +grids={path} +multiplier=1 '
            '+step +proj=unitconvert +xy_in=rad +xy_out=deg')
    return vertical(egm), vertical(geo18), {
        p.name: {'bytes': p.stat().st_size, 'sha256': digest(p.read_bytes())} for p in [egm, geo18]
    }


def packet(triangles: np.ndarray, ids: np.ndarray) -> str:
    """Triangle soup retains source triangles and permits derivative wireframes.

    GPU rows: position 3f, flat normal 3f, integer feature index as f, barycentric 3f.
    Soup expansion is only an encoding; it adds no surface samples or geometry.
    """
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths, 1e-12)[:, None]
    rows = np.concatenate([
        triangles.reshape(-1, 3), np.repeat(normals, 3, axis=0),
        np.repeat(ids, 3)[:, None], np.tile(np.eye(3), (len(triangles), 1)),
    ], axis=1).astype('<f4')
    return base64.b64encode(rows.tobytes()).decode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draco-module', required=True, type=Path)
    parser.add_argument('--grids', required=True, type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'data/out/scene-prototype')
    args = parser.parse_args()
    cache = ROOT / 'data/raw/scene-prototype'
    cache.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    sources = {}
    layer_url = SCENE + '/layers/0'
    info = json.loads(fetch(layer_url + '?f=pjson', cache, sources))
    item = json.loads(fetch(ITEM, cache, sources))
    nodes = []
    # Bounded metadata scan; stop at the short final node page.
    for page in range(4):
        batch = json.loads(fetch(f'{layer_url}/nodepages/{page}?f=json', cache, sources))['nodes']
        nodes.extend(batch)
        if len(batch) < info['nodePages']['nodesPerPage']:
            break
    else:
        raise ValueError('Metadata scan exceeded four pages; revise the explicit experiment bound')
    target = np.array([-118.52862, 34.04257])
    leaves = [n for n in nodes if n.get('mesh') and not n.get('children')]
    node = min(leaves, key=lambda n: np.linalg.norm((np.array(n['obb']['center'][:2]) - target) * [0.83, 1]))
    resource = node['mesh']['geometry']['resource']
    definition = info['geometryDefinitions'][node['mesh']['geometry']['definition']]
    buffers = definition['geometryBuffers']
    compressed = next(i for i, b in enumerate(buffers) if b.get('compressedAttributes', {}).get('encoding') == 'draco')
    raw = fetch(f'{layer_url}/nodes/{resource}/geometries/{compressed}', cache, sources)
    drc = args.out / 'source-node.drc'
    drc.write_bytes(raw)
    decoded_path = args.out / 'decoded-node.json'
    subprocess.run(['node', str(Path(__file__).with_name('decode_i3s.cjs')), str(drc), str(decoded_path), str(args.draco_module.resolve())], check=True)
    decoded = json.loads(decoded_path.read_text())
    positions = next(a for a in decoded['attributes'] if a['type'] == 0)
    features = next(a for a in decoded['attributes'] if a.get('semantic') == 'feature-index')
    p = np.array(positions['values']).reshape(-1, 3)
    p[:, :2] *= positions['scale']
    p += node['obb']['center']
    indices = np.array(decoded['indices'], dtype=np.int64).reshape(-1, 3)
    feature_index = np.array(features['values'], dtype=np.int64)
    if not np.array_equal(feature_index.astype(float), np.array(features['values'])):
        raise ValueError('Non-integral feature indices')
    if len(feature_index) != len(p) or indices.min() < 0 or indices.max() >= len(p):
        raise ValueError('Invalid vertex/feature alignment')
    triangle_features = feature_index[indices]
    if not np.all(triangle_features == triangle_features[:, :1]):
        raise ValueError('A source triangle crosses feature identity')
    keys = {a['name']: a['key'] for a in info['attributeStorageInfo']}
    # Attribute resource may differ from geometry resource according to I3S.
    attr_resource = node['mesh']['attribute']['resource']
    attributes = {name: strings(fetch(f'{layer_url}/nodes/{attr_resource}/attributes/{keys[name]}/0', cache, sources)) for name in ['APN', 'BLD_ID']}
    count = len(attributes['APN'])
    if any(len(a) != count for a in attributes.values()) or feature_index.min() < 0 or feature_index.max() >= count:
        raise ValueError('Invalid attribute/feature alignment')
    if len(features['featureIds']) != count or len(set(features['featureIds'])) != count:
        raise ValueError('Missing or repeated source feature IDs')
    egm, geo18, grid_metadata = grid_transformers(args.grids.resolve())
    lon, lat, h = egm.transform(p[:, 0], p[:, 1], p[:, 2], errcheck=True)
    h = np.array(h)
    if not np.all((-40 < h - p[:, 2]) & (h - p[:, 2] < -30)):
        raise ValueError('EGM96 vertical conversion outside LA range')
    origin_h = float(np.median(h))
    origin = wgs84_to_ecef(target[0], target[1], origin_h)
    rotation = enu_rotation(*target)
    local = (wgs84_to_ecef(lon, lat, h) - origin) @ rotation.T
    to_utm = pyproj.Transformer.from_crs(4326, 6340, always_xy=True)
    bx, by = to_utm.transform(p[:, 0], p[:, 1])
    tile = ROOT / 'data/raw/visual-baseline/sample-tile.laz'
    with laspy.open(tile) as reader:
        bounds = [*reader.header.mins[:2], *reader.header.maxs[:2]]
        # Keep complete buildings inside the available ground tile; no arbitrary roof cut.
        retained = [f for f in sorted(set(feature_index)) if np.all(
            (bx[feature_index == f] > bounds[0] + 3) & (bx[feature_index == f] < bounds[2] - 3) &
            (by[feature_index == f] > bounds[1] + 3) & (by[feature_index == f] < bounds[3] - 3))]
        if not retained:
            raise ValueError('No complete buildings inside the archived terrain tile')
        retained_vertices = np.isin(feature_index, retained)
        roi = [float(bx[retained_vertices].min() - 15), float(by[retained_vertices].min() - 15),
               float(bx[retained_vertices].max() + 15), float(by[retained_vertices].max() + 15)]
        roi = [max(roi[0], bounds[0]), max(roi[1], bounds[1]), min(roi[2], bounds[2]), min(roi[3], bounds[3])]
        ground_chunks, scanned = [], 0
        for chunk in reader.chunk_iterator(1_000_000):
            scanned += len(chunk)
            x, y, z = np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)
            mask = ((chunk.classification == 2) & (x >= roi[0]) & (x <= roi[2]) & (y >= roi[1]) & (y <= roi[3]))
            if mask.any():
                ground_chunks.append(np.column_stack([x[mask], y[mask], z[mask]]))
    ground = np.vstack(ground_chunks)
    # 2m classified-ground grid. Median supported cells; nearest fill <= 3m.
    # Unsupported cells produce holes, rather than invented terrain across gaps.
    step = 2.0
    xaxis = np.arange(roi[0] + step / 2, roi[2], step)
    yaxis = np.arange(roi[1] + step / 2, roi[3], step)
    nx, ny = len(xaxis), len(yaxis)
    cellx = np.floor((ground[:, 0] - roi[0]) / step).astype(int)
    celly = np.floor((ground[:, 1] - roi[1]) / step).astype(int)
    inside = (cellx < nx) & (celly < ny)
    ground, cellx, celly = ground[inside], cellx[inside], celly[inside]
    cells = celly * nx + cellx
    order = np.argsort(cells, kind='stable')
    unique, starts = np.unique(cells[order], return_index=True)
    ends = np.r_[starts[1:], len(order)]
    heights = np.full(nx * ny, np.nan)
    for cell, a, b in zip(unique, starts, ends):
        heights[cell] = np.median(ground[order[a:b], 2])
    xx, yy = np.meshgrid(xaxis, yaxis)
    xy = np.column_stack([xx.ravel(), yy.ravel()])
    supported = np.isfinite(heights)
    distances, neighbors = cKDTree(xy[supported]).query(xy)
    heights[~supported] = heights[supported][neighbors[~supported]]
    valid = distances <= 3.0
    glon, glat = pyproj.Transformer.from_crs(6340, 4326, always_xy=True).transform(xy[:, 0], xy[:, 1])
    _, _, gh = geo18.transform(glon, glat, heights, errcheck=True)
    gh = np.array(gh)
    if not np.all((-40 < gh - heights) & (gh - heights < -30)):
        raise ValueError('GEOID18 vertical conversion outside LA range')
    gpos = (wgs84_to_ecef(glon, glat, gh) - origin) @ rotation.T
    k = np.arange(nx * ny).reshape(ny, nx)[:-1, :-1].ravel()
    ground_indices = np.vstack([np.stack([k, k + 1, k + nx], axis=1), np.stack([k + 1, k + nx + 1, k + nx], axis=1)])
    ground_indices = ground_indices[np.all(valid[ground_indices], axis=1)]
    structures, kept_triangles, kept_ids = [], [], []
    for dense_id, f in enumerate(retained, 1):
        triangles = local[indices[triangle_features[:, 0] == f]]
        kept_triangles.append(triangles)
        kept_ids.append(np.full(len(triangles), dense_id))
        apn = ''.join(c for c in attributes['APN'][f] if c.isdigit())
        structures.append({
            'id': f'd4018709bc26465daf33abe15b25d1e9:{features["featureIds"][f]}',
            'source_feature_id': features['featureIds'][f], 'building_id': attributes['BLD_ID'][f],
            'apn': apn, 'gpu_index': dense_id, 'physical_condition': 'unknown',
            'geometry_role': 'historical_reference', 'geometry_vintage': '2023',
            'center_enu': np.mean(triangles.reshape(-1, 3), axis=0).tolist(), 'triangles': len(triangles),
        })
    triangles = np.concatenate(kept_triangles)
    ids = np.concatenate(kept_ids)
    positions32 = triangles.astype(np.float32).astype(float)
    quant_error = np.linalg.norm(positions32 - triangles, axis=2)
    payload = {
        'schema': 'palisades-scene-experiment-v1',
        'title': 'Alphabet Streets · dated scene experiment',
        'building_vintage': '2023', 'ground_vintage': '2025-01-21',
        'origin_lon_lat_h': [*target, origin_h], 'structures': structures,
        'bounds_enu': [np.minimum(triangles.min(axis=(0, 1)), gpos.min(axis=0)).tolist(),
                       np.maximum(triangles.max(axis=(0, 1)), gpos.max(axis=0)).tolist()],
        'buildings': packet(triangles, ids),
        'ground': packet(gpos[ground_indices], np.zeros(len(ground_indices))),
    }
    packed_buildings = base64.b64decode(payload['buildings'])
    packed_ground = base64.b64decode(payload['ground'])
    payload['geometry_sha256'] = digest(packed_buildings)
    template = Path(__file__).with_name('preview.html').read_text()
    encoded = json.dumps(payload, separators=(',', ':')).replace('<', '\\u003c')
    (args.out / 'index.html').write_text(template.replace('/*SCENE_DATA*/null', encoded))
    report = {
        'schema': 'palisades-scene-probe-v1', 'built_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'One building node, complete structures inside one archived LiDAR tile; not the full Palisades',
        'node_index': node['index'], 'node_resource': resource,
        'source_points': len(p), 'source_triangles': len(indices), 'source_features': count,
        'retained_structures': len(structures), 'retained_apns': len(set(s['apn'] for s in structures)),
        'building_triangles': len(triangles), 'building_buffer_bytes': len(packed_buildings),
        'ground_triangles': len(ground_indices), 'ground_buffer_bytes': len(packed_ground),
        'lidar_points_scanned': scanned, 'ground_points_in_roi': len(ground),
        'ground_grid_spacing_m': step, 'ground_fill_max_distance_m': 3,
        'roi_utm_bounds_m': roi,
        'ground_unsupported_cells': int((~valid).sum()),
        'building_float32_max_displacement_m': float(quant_error.max()),
        'building_geometry_sha256': payload['geometry_sha256'],
        'representation_patch_bytes_per_structure': 1,
        'egm96_undulation_range_m': [float((h - p[:, 2]).min()), float((h - p[:, 2]).max())],
        'geoid18_undulation_range_m': [float((gh - heights).min()), float((gh - heights).max())],
        'source_item_modified': item['modified'],
        'geometry_vintage_basis': 'County item description and snippet say 2023; publication/processing date is separate',
        'ground_vintage_basis': 'data/out/visual-baseline/report.json, USGS acquisition evidence',
        'horizontal_transform': 'PROJ EPSG:4326 <-> EPSG:6340 default operation; metre-level accuracy claim not independently checked',
        'vertical_transforms': 'Explicit EGM96 and GEOID18 grid shifts (+multiplier=1) to ellipsoid; horizontal datum accuracy remains separate',
        'grids': grid_metadata, 'source_downloads': sources,
        'lidar_source': {'path': str(tile.relative_to(ROOT)), 'bytes': tile.stat().st_size, 'sha256': digest(tile.read_bytes())},
        'claims': {'physical_conditions_produced': False, 'framing_geometry_produced': False,
                   'geometric_accuracy_measured_against_controls': False, 'frame_performance_measured': False},
        'assumptions': ['County feature-index attribute ordering matches node attribute buffers',
                        'LAS class 2 is used as dated terrain support',
                        'Grid median and <=3m fill approximate terrain; retained measurements remain archived'],
    }
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['retained_structures', 'building_triangles', 'ground_triangles', 'building_float32_max_displacement_m']}))


if __name__ == '__main__':
    main()
