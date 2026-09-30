"""Compile county I3S roof meshes into addressable, bounded regional GPU batches.

Retains county damage fields, never maps permit stages to physical shapes.
Uses the adjacent Draco adapter and explicit EGM96/GEOID18 height grids.
Geometry loads by node visibility; camera and raster terrain use MapLibre.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
import subprocess
import hashlib
import numpy as np
import pyproj
from build_scene import fetch, strings, grid_transformers, ROOT, SCENE
from prepare_map import BOUNDS

OUT = ROOT / 'data/out/scene-prototype/buildings'
CACHE = ROOT / 'data/raw/scene-prototype'
ORIGIN = [-118.534, 34.055]
SCALE = 1 / (40075016.68557849 * np.cos(np.radians(ORIGIN[1])))


def mercator(lon, lat):
    return (lon + 180) / 360, (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draco-module', type=Path, required=True)
    parser.add_argument('--grids', type=Path, required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    info = json.loads(fetch(SCENE + '/layers/0?f=pjson', CACHE, records))
    nodes = []
    for page in range(4):
        ns = json.loads(fetch(f'{SCENE}/layers/0/nodepages/{page}?f=json', CACHE, records))['nodes']
        nodes.extend(ns)
        if len(ns) < info['nodePages']['nodesPerPage']:
            break
    w, s, e, n = BOUNDS
    leaves = [x for x in nodes if x.get('mesh') and not x.get('children') and
              w - .006 < x['obb']['center'][0] < e + .006 and s - .006 < x['obb']['center'][1] < n + .006]
    keys = {x['name']: x['key'] for x in info['attributeStorageInfo']}
    egm, geo18, grids = grid_transformers(args.grids.resolve())

    def decode(node):
        local_records = {}
        geom = node['mesh']['geometry']
        compressed = next(i for i, b in enumerate(info['geometryDefinitions'][geom['definition']]['geometryBuffers'])
                          if b.get('compressedAttributes', {}).get('encoding') == 'draco')
        drc = OUT / f'{node["index"]}.drc'
        decoded = OUT / f'{node["index"]}.json'
        drc.write_bytes(fetch(f'{SCENE}/layers/0/nodes/{geom["resource"]}/geometries/{compressed}', CACHE, local_records))
        if not decoded.exists():
            subprocess.run(['node', str(Path(__file__).with_name('decode_i3s.cjs')), str(drc), str(decoded), str(args.draco_module.resolve())], check=True)
        j = json.loads(decoded.read_text())
        position = next(a for a in j['attributes'] if a['type'] == 0)
        feature = next(a for a in j['attributes'] if a.get('semantic') == 'feature-index')
        p = np.asarray(position['values']).reshape(-1, 3)
        p[:, :2] *= position['scale']
        p += node['obb']['center']
        idx = np.asarray(j['indices'], dtype=np.uint32).reshape(-1, 3)
        ids = np.asarray(feature['values'], dtype=np.int64)
        if not np.array_equal(ids.astype(float), feature['values']) or not np.all(ids[idx] == ids[idx[:, :1]]):
            raise ValueError('Geometry crosses feature identities')
        resource = node['mesh']['attribute']['resource']
        attrs = {name: strings(fetch(f'{SCENE}/layers/0/nodes/{resource}/attributes/{keys[name]}/0', CACHE, local_records))
                 for name in ['APN', 'BLD_ID', 'DAMAGE', 'SITUSADDRESS']}
        count = len(feature['featureIds'])
        if ids.min() < 0 or ids.max() >= count or any(len(a) != count for a in attrs.values()):
            raise ValueError('I3S attributes do not match feature indices')
        # Convert EGM96 orthometric height to NAVD88/GEOID18, matching the
        # high-resolution pilot terrain. Horizontal accuracy is not inferred.
        _, _, ellipsoid = egm.transform(p[:, 0], p[:, 1], p[:, 2], errcheck=True)
        _, _, n18 = geo18.transform(p[:, 0], p[:, 1], np.zeros(len(p)), errcheck=True)
        p[:, 2] = np.asarray(ellipsoid) - np.asarray(n18)
        return node, p, idx, ids, attrs, feature['featureIds'], local_records

    origin = mercator(*ORIGIN)
    manifest_nodes, structures, seen = [], [], set()
    with ThreadPoolExecutor(max_workers=4) as executor:
        for node, p, idx, ids, attrs, feature_ids, local_records in executor.map(decode, sorted(leaves, key=lambda n: n['index'])):
            records.update(local_records)
            mapping = np.zeros(len(feature_ids), dtype=np.uint32)
            for f in sorted(set(ids)):
                center = p[ids == f].mean(axis=0)
                if not (w <= center[0] <= e and s <= center[1] <= n):
                    continue
                stable = str(feature_ids[f])
                if stable in seen:
                    continue
                seen.add(stable)
                dense = len(structures) + 1
                mapping[f] = dense
                structures.append({'gpu_id': dense, 'source_feature_id': feature_ids[f], 'building_id': attrs['BLD_ID'][f],
                                   'apn': ''.join(c for c in attrs['APN'][f] if c.isdigit()), 'damage': attrs['DAMAGE'][f],
                                   'address': attrs['SITUSADDRESS'][f], 'center': center[:2].tolist(), 'geometry_vintage': '2023'})
            keep = mapping[ids[idx[:, 0]]] > 0
            triangles = idx[keep]
            if not len(triangles):
                continue
            used, compact = np.unique(triangles, return_inverse=True)
            indices = compact.reshape(-1, 3).astype('<u4')
            p, ids = p[used], ids[used]
            mx, my = mercator(p[:, 0], p[:, 1])
            local = np.column_stack([(mx - origin[0]) / SCALE, (my - origin[1]) / SCALE, p[:, 2]])
            normals = np.zeros_like(local)
            t = local[indices]
            cross = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            for corner in range(3):
                np.add.at(normals, indices[:, corner], cross)
            normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-12)[:, None]
            z = 18
            while True:
                x0, x1 = int(np.floor(mx.min() * 2 ** z)), int(np.floor(mx.max() * 2 ** z))
                y0, y1 = int(np.floor(my.min() * 2 ** z)), int(np.floor(my.max() * 2 ** z))
                width, height = x1 - x0 + 1, y1 - y0 + 1
                if width * height <= 64 and max(width, height) <= 12:
                    break
                z -= 1
            uv = np.column_stack([(mx * 2 ** z - x0) / width, (my * 2 ** z - y0) / height])
            rows = np.column_stack([local, normals, uv, mapping[ids]]).astype('<f4')
            if not np.isfinite(rows).all():
                raise ValueError('Non-finite GPU vertex')
            vertex = rows.tobytes()
            index = indices.tobytes()
            (OUT / f'{node["index"]}.vertices.bin').write_bytes(vertex)
            (OUT / f'{node["index"]}.indices.bin').write_bytes(index)
            manifest_nodes.append({'id': node['index'], 'vertex_count': len(rows), 'index_count': indices.size,
                                   'bounds': [float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())],
                                   'vertex_bytes': len(vertex), 'index_bytes': len(index),
                                   'vertex_sha256': hashlib.sha256(vertex).hexdigest(), 'index_sha256': hashlib.sha256(index).hexdigest(),
                                   'atlas': {'z': z, 'x': x0, 'y': y0, 'width': width, 'height': height}})
            print(f'Node {node["index"]}: {len(rows):,} vertices, {indices.size // 3:,} triangles', flush=True)
    manifest = {'schema': 'openpali-regional-mesh-v1', 'origin': ORIGIN, 'mercator_origin': origin,
                'mercator_metre_scale': SCALE, 'height_frame': 'NAVD88 / GEOID18', 'nodes': manifest_nodes,
                'structures': structures, 'source_records': records, 'grids': grids, 'bounds': BOUNDS,
                'new_physical_conditions_produced': False, 'new_framing_geometry_produced': False}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, separators=(',', ':')))
    print(json.dumps({'nodes': len(manifest_nodes), 'structures': len(structures), 'gpu_bytes': sum(n['vertex_bytes'] + n['index_bytes'] for n in manifest_nodes)}), flush=True)


if __name__ == '__main__':
    main()
