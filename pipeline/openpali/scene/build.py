"""Compile the building scene: quantized mesh batches, a per-structure table
with baked ground registration, and the terrain tiles they are registered to.

    python -m openpali.scene.build [--offline] [--plan]

``--plan`` lists what a build would fetch that is not already in the raw
cache, and fetches nothing beyond the small index documents needed to know.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from . import sources
from .sources import OUT, RAW, ROOT, SCENE_LAYER, fetch, mercator, strings
from .terrain import BAKE_ZOOMS, Terrain

SCHEMA = 'openpali-scene-v2'
VERTEX_BYTES = 16
#: scene frame: mercator-aligned metres about this point (x east, y south, z up)
ORIGIN = (-118.56, 34.06)
SCALE = 1 / (40075016.68557849 * np.cos(np.radians(ORIGIN[1])))
#: vertices this close to a structure's lowest point count as its base
FOOTING_BAND_M = 0.5
ATTRIBUTES = ('APN', 'BLD_ID', 'DAMAGE', 'SITUSADDRESS')
DRACO = RAW / 'tools' / 'node_modules' / 'draco3d'
DECODER = Path(__file__).with_name('decode_i3s.cjs')


def log(message: str) -> None:
    print(message, flush=True)


def oct_encode(normals: np.ndarray) -> np.ndarray:
    """Unit normals → octahedral int8 pairs (matches web/src/components/scene/format.ts)."""
    n = normals / np.maximum(np.abs(normals).sum(axis=1, keepdims=True), 1e-12)
    xy = n[:, :2].copy()
    below = n[:, 2] < 0
    folded = (1 - np.abs(xy[:, ::-1])) * np.where(xy >= 0, 1.0, -1.0)
    xy[below] = folded[below]
    return np.round(xy * 127).astype(np.int8)


def quantize(local: np.ndarray, normals: np.ndarray, uv: np.ndarray, ids: np.ndarray):
    """Float vertices → the 16-byte GPU layout plus its grid."""
    low = local.min(axis=0)
    extent = np.maximum(local.max(axis=0) - low, 1e-3)
    out = np.zeros(len(local), dtype=np.dtype([
        ('pos', '<u2', 3), ('oct', 'i1', 2), ('id', '<u2'), ('uv', '<u2', 2), ('pad', '<u2')]))
    assert out.dtype.itemsize == VERTEX_BYTES
    out['pos'] = np.round((local - low) / extent * 65535)
    out['oct'] = oct_encode(normals)
    out['id'] = ids
    out['uv'] = np.round(np.clip(uv, 0, 1) * 65535)
    return out, {'min': low.tolist(), 'extent': extent.tolist()}


def leaves(records: dict, offline: bool) -> tuple[dict, list[dict]]:
    info = json.loads(fetch(SCENE_LAYER + '?f=pjson', records, offline=offline))
    per_page = info['nodePages']['nodesPerPage']
    nodes: list[dict] = []
    page = 0
    while True:
        batch = json.loads(fetch(f'{SCENE_LAYER}/nodepages/{page}?f=json', records, offline=offline))['nodes']
        nodes.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return info, [n for n in nodes if n.get('mesh') and not n.get('children')]


def node_urls(info: dict, node: dict) -> tuple[str, dict[str, str]]:
    geometry = node['mesh']['geometry']
    buffers = info['geometryDefinitions'][geometry['definition']]['geometryBuffers']
    draco = next(i for i, b in enumerate(buffers)
                 if b.get('compressedAttributes', {}).get('encoding') == 'draco')
    keys = {entry['name']: entry['key'] for entry in info['attributeStorageInfo']}
    resource = node['mesh']['attribute']['resource']
    return (f'{SCENE_LAYER}/nodes/{geometry["resource"]}/geometries/{draco}',
            {name: f'{SCENE_LAYER}/nodes/{resource}/attributes/{keys[name]}/0' for name in ATTRIBUTES})


def decode(info: dict, node: dict, to_navd88, offline: bool):
    """One leaf → positions (lon, lat, NAVD88 m), triangles, per-vertex feature index."""
    records: dict = {}
    geometry_url, attribute_urls = node_urls(info, node)
    raw = fetch(geometry_url, records, offline=offline)
    decoded = RAW / 'decoded' / f'{hashlib.sha256(raw).hexdigest()}.json'
    if not decoded.exists():
        decoded.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['node', str(DECODER), str(sources.cache_path(geometry_url)), str(decoded), str(DRACO)],
                       check=True)
    mesh = json.loads(decoded.read_text())
    position = next(a for a in mesh['attributes'] if a['type'] == 0)
    feature = next(a for a in mesh['attributes'] if a.get('semantic') == 'feature-index')
    p = np.asarray(position['values'], dtype=np.float64).reshape(-1, 3)
    p[:, :2] *= position['scale']
    p += node['obb']['center']
    triangles = np.asarray(mesh['indices'], dtype=np.uint32).reshape(-1, 3)
    ids = np.asarray(feature['values'], dtype=np.int64)
    if not np.array_equal(ids.astype(float), feature['values']) or not np.all(ids[triangles] == ids[triangles[:, :1]]):
        raise ValueError(f'node {node["index"]}: a triangle spans two structures')
    attributes = {name: strings(fetch(url, records, offline=offline)) for name, url in attribute_urls.items()}
    count = len(feature['featureIds'])
    if ids.min() < 0 or ids.max() >= count or any(len(a) != count for a in attributes.values()):
        raise ValueError(f'node {node["index"]}: attributes do not match feature indices')
    p[:, 2] = to_navd88(p[:, 0], p[:, 1], p[:, 2])
    return node, p, triangles, ids, attributes, feature['featureIds'], records


def publish(scene: Path) -> None:
    """Make ``scene`` the current one by replacing the ``current.json`` pointer.

    Scene directories are immutable and named by their content, so the pointer
    is the only thing that changes, and it changes atomically: a server that
    mounts ``data/out/scene`` keeps serving the previous scene until the
    rename, and an interrupted build leaves the previous scene published."""
    pointer = OUT / 'current.json'
    staging = OUT / '.current.json'
    staging.write_text(json.dumps({'scene_id': scene.name}) + '\n')
    os.replace(staging, pointer)


def parcel_points() -> np.ndarray:
    """Centroids of the current release's fire-destroyed parcels (the scored lots)."""
    pointer = ROOT / 'data/out/evidence/current.json'
    if not pointer.exists():
        return np.zeros((0, 2))
    release = json.loads(pointer.read_text())['release_id']
    parcels = json.loads((ROOT / 'data/out/evidence' / release / 'parcels.geojson').read_text())
    points = []
    for feature in parcels['features']:
        if feature['properties'].get('damage') != 'destroyed' or not feature.get('geometry'):
            continue
        geometry = feature['geometry']
        ring = geometry['coordinates'][0] if geometry['type'] == 'Polygon' else geometry['coordinates'][0][0]
        points.append(np.mean(np.asarray(ring)[:, :2], axis=0))
    return np.asarray(points)


def plan(offline: bool) -> int:
    """Report what is and is not yet in the raw cache."""
    records: dict = {}
    info, nodes = leaves(records, offline)
    need_nodes = 0
    for node in nodes:
        geometry_url, attribute_urls = node_urls(info, node)
        if not all(sources.cache_path(u).exists() for u in [geometry_url, *attribute_urls.values()]):
            need_nodes += 1
    grids = [n for n in sources.GRIDS if not sources.cache_path(f'{sources.PROJ_CDN}/{n}', '.tif').exists()]
    terrain = Terrain(records, offline=True)
    points = parcel_points()
    tiles = terrain.usgs_tiles_for(points[:, 0], points[:, 1]) if len(points) else set()
    cached = {t for t in tiles if sources.cache_path(terrain.usgs_url(t), '.tif').exists()}
    known_absent = {t for t in tiles if sources.cache_path(terrain.usgs_url(t), '.tif').with_suffix('.absent').exists()}
    log(json.dumps({
        'scene_leaf_nodes': len(nodes), 'scene_nodes_to_fetch': need_nodes,
        'geoid_grids_to_fetch': grids, 'draco3d_installed': DRACO.exists(),
        'lidar_tiles_for_scored_parcels': len(tiles), 'lidar_tiles_cached': len(cached),
        'lidar_tiles_known_unpublished': len(known_absent),
        'lidar_tiles_to_try': len(tiles) - len(cached) - len(known_absent),
        'lidar_bytes_each': 9_443_436,
    }, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='fail instead of fetching anything')
    parser.add_argument('--plan', action='store_true', help='list what a build would fetch, then stop')
    parser.add_argument('--skip-terrain-tiles', action='store_true',
                        help='register structures but do not bake terrain tiles')
    args = parser.parse_args(argv)
    if args.plan:
        return plan(args.offline)
    if not DRACO.exists():
        log(f'draco3d 1.5.7 is required at {DRACO}\n'
            f'  npm install --prefix {RAW / "tools"} --no-save --ignore-scripts draco3d@1.5.7')
        return 2

    records: dict = {}
    info, nodes = leaves(records, args.offline)
    grids = sources.grid_paths(records, offline=args.offline)
    to_navd88 = sources.egm96_to_navd88(grids)
    log(f'scene layer: {len(nodes)} leaf nodes')

    ox, oy = mercator(*ORIGIN)
    staging = OUT / '.staging'
    if staging.exists():
        shutil.rmtree(staging)
    (staging / 'buildings').mkdir(parents=True)

    manifest_nodes: list[dict] = []
    structures: list[dict] = []
    lowest: list[float] = []
    highest: list[float] = []
    footings: list[np.ndarray] = []  # per structure: lon/lat of the vertices at its base
    seen: set[str] = set()
    with ThreadPoolExecutor(max_workers=4) as pool:
        ordered = sorted(nodes, key=lambda n: n['index'])
        for node, p, triangles, ids, attributes, feature_ids, node_records in pool.map(
                lambda n: decode(info, n, to_navd88, args.offline), ordered):
            records.update(node_records)
            mapping = np.zeros(len(feature_ids), dtype=np.uint32)
            for f in sorted(set(ids.tolist())):
                source_id = str(feature_ids[f])
                if source_id in seen:  # the same structure published in two nodes
                    continue
                seen.add(source_id)
                member = p[ids == f]
                dense = len(structures) + 1
                mapping[f] = dense
                structures.append({
                    'gpu_id': dense,
                    'apn': ''.join(c for c in attributes['APN'][f] if c.isdigit()),
                    'damage': attributes['DAMAGE'][f],
                    'center': [round(float(member[:, 0].mean()), 7), round(float(member[:, 1].mean()), 7)],
                    'source_feature_id': feature_ids[f],
                    'building_id': attributes['BLD_ID'][f],
                    'address': attributes['SITUSADDRESS'][f],
                })
                lowest.append(float(member[:, 2].min()))
                highest.append(float(member[:, 2].max()))
                footings.append(member[member[:, 2] <= member[:, 2].min() + FOOTING_BAND_M][:, :2])
            kept = triangles[mapping[ids[triangles[:, 0]]] > 0]
            if not len(kept):
                continue
            used, compact = np.unique(kept, return_inverse=True)
            indices = compact.reshape(-1, 3).astype('<u4')
            p, vertex_ids = p[used], mapping[ids[used]]
            mx, my = mercator(p[:, 0], p[:, 1])
            local = np.column_stack([(mx - ox) / SCALE, (my - oy) / SCALE, p[:, 2]])
            normals = np.zeros_like(local)
            corners = local[indices]
            cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
            for corner in range(3):
                np.add.at(normals, indices[:, corner], cross)
            normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-12)[:, None]
            # aerial atlas: the smallest tile rectangle (≤ 64 tiles) covering the batch
            z = 18
            while True:
                x0, x1 = int(np.floor(mx.min() * 2 ** z)), int(np.floor(mx.max() * 2 ** z))
                y0, y1 = int(np.floor(my.min() * 2 ** z)), int(np.floor(my.max() * 2 ** z))
                width, height = x1 - x0 + 1, y1 - y0 + 1
                if width * height <= 64 and max(width, height) <= 12:
                    break
                z -= 1
            uv = np.column_stack([(mx * 2 ** z - x0) / width, (my * 2 ** z - y0) / height])
            if vertex_ids.max() > 65535:
                raise ValueError('more than 65,535 structures: widen the id attribute')
            vertices, grid = quantize(local, normals, uv, vertex_ids)
            # no batch approaches 65,536 vertices, and indices are half the payload
            index_type = 'u16' if len(vertices) <= 65536 else 'u32'
            vertex_bytes = vertices.tobytes()
            index_bytes = indices.astype('<u2' if index_type == 'u16' else '<u4').tobytes()
            (staging / 'buildings' / f'{node["index"]}.vertices.bin').write_bytes(vertex_bytes)
            (staging / 'buildings' / f'{node["index"]}.indices.bin').write_bytes(index_bytes)
            manifest_nodes.append({
                'id': node['index'], 'vertex_count': len(vertices), 'index_count': int(indices.size),
                'bounds': [float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())],
                'vertex_bytes': len(vertex_bytes), 'index_bytes': len(index_bytes), 'index_type': index_type,
                'vertex_sha256': hashlib.sha256(vertex_bytes).hexdigest(),
                'index_sha256': hashlib.sha256(index_bytes).hexdigest(),
                'atlas': {'z': z, 'x': x0, 'y': y0, 'width': width, 'height': height},
                'grid': grid,
            })
    log(f'compiled {len(structures):,} structures in {len(manifest_nodes)} batches')

    # ---- ground registration, measured against the surface the map will draw ----
    terrain = Terrain(records, offline=args.offline)
    centers = np.asarray([s['center'] for s in structures])
    # Lidar is acquired where rebuild is tracked: the tiles holding scored
    # (fire-destroyed) parcels. Standing structures beyond them are registered
    # to the regional terrain, which is also what the map draws there.
    parcels = parcel_points()
    points = parcels if len(parcels) else centers
    wanted = terrain.usgs_tiles_for(points[:, 0], points[:, 1])
    log(f'terrain: {len(wanted)} lidar tiles cover the scored parcels')
    terrain.acquire(wanted, log)
    ground, weight = terrain.sample(centers[:, 0], centers[:, 1])
    # The county model gives each structure a flat base. Seat that base on the
    # LOWEST ground under its footprint: on a slope the uphill side is then cut
    # into the hillside, as a real foundation is, and no corner floats.
    owners = np.concatenate([np.full(len(f), i) for i, f in enumerate(footings)])
    footing_points = np.vstack(footings)
    footing_ground, _ = terrain.sample(footing_points[:, 0], footing_points[:, 1])
    seat = np.full(len(structures), np.inf)
    np.minimum.at(seat, owners, footing_ground)
    for structure, base, top, elevation, w, seat_m in zip(structures, lowest, highest, ground, weight, seat):
        structure['base_m'] = round(base, 3)
        structure['height_m'] = round(top - base, 3)
        structure['ground_delta_m'] = round(float(seat_m) - base, 3)
        # terrain at the structure's centre when this was baked: the client
        # compares the terrain it draws against this, not against the base
        structure['ground_m'] = round(float(elevation), 3)
        structure['ground_source'] = 'usgs_2025_lidar' if w >= 1 else 'usgs_mapzen_blend' if w > 0 else 'mapzen'

    # ---- terrain tiles: only those the lidar changes; the rest stay Mapzen ----
    terrain_index: dict[str, list[list[int]]] = {}
    terrain_bytes = 0
    terrain_digest = hashlib.sha256()  # over every baked tile, in index order
    if not args.skip_terrain_tiles:
        for z in BAKE_ZOOMS:
            baked = []
            candidates = terrain.tiles_touching(z)
            for count, (x, y) in enumerate(candidates, 1):
                png = terrain.bake(z, x, y)
                if png is None:
                    continue
                path = staging / 'terrain' / str(z) / str(x) / f'{y}.png'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(png)
                terrain_bytes += len(png)
                terrain_digest.update(f'{z}/{x}/{y}:'.encode() + hashlib.sha256(png).digest())
                baked.append([x, y])
                if count % 100 == 0:
                    log(f'  terrain z{z}: {count}/{len(candidates)}')
            terrain_index[str(z)] = baked
            log(f'terrain z{z}: {len(baked)} tiles')

    manifest = {
        'schema': SCHEMA,
        'origin': list(ORIGIN),
        'mercator_origin': [float(ox), float(oy)],
        'mercator_metre_scale': float(SCALE),
        'height_frame': 'NAVD88 / GEOID18',
        'buffers': 'buildings',
        'nodes': manifest_nodes,
        'structures': [{k: s[k] for k in ('gpu_id', 'apn', 'damage', 'center', 'base_m',
                                           'height_m', 'ground_delta_m', 'ground_m')} for s in structures],
        'terrain': {
            'tiles': 'terrain/{z}/{x}/{y}.png', 'encoding': 'terrarium',
            'minzoom': min(BAKE_ZOOMS), 'maxzoom': max(BAKE_ZOOMS), 'index': terrain_index,
            # the scene id is a hash of this manifest, so it must cover tile bytes
            'sha256': terrain_digest.hexdigest(), 'bytes': terrain_bytes,
            'fallback': sources.MAPZEN + '/{z}/{x}/{y}.png', 'fallback_maxzoom': 15,
        } if terrain_index else None,
        'geometry_vintage': '2023',
        'new_physical_conditions_produced': False,
    }
    body = json.dumps(manifest, sort_keys=True, separators=(',', ':'))
    scene_id = 'scene-' + hashlib.sha256(body.encode()).hexdigest()[:24]
    manifest['scene_id'] = scene_id
    (staging / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':')))
    (staging / 'provenance.json').write_text(json.dumps({
        'scene_id': scene_id, 'structures': structures, 'source_records': records,
        'lidar_tiles': {'acquired': sorted(sources.usgs_tile_name(*t) for t in terrain.available),
                        'not_published': sorted(sources.usgs_tile_name(*t) for t in terrain.missing)},
    }, sort_keys=True, separators=(',', ':')))

    final = OUT / scene_id
    if final.exists():
        # the id is the content: an identical scene is already in place, and
        # a published directory is never rewritten under a running server
        shutil.rmtree(staging)
    else:
        staging.rename(final)
    publish(final)
    lidar = sum(1 for s in structures if s['ground_source'] == 'usgs_2025_lidar')
    log(json.dumps({
        'scene_id': scene_id, 'structures': len(structures), 'batches': len(manifest_nodes),
        'geometry_bytes': sum(n['vertex_bytes'] + n['index_bytes'] for n in manifest_nodes),
        'structures_registered_to_lidar': lidar, 'terrain_tiles': sum(len(v) for v in terrain_index.values()),
        'terrain_bytes': terrain_bytes, 'path': str(final.relative_to(ROOT)),
    }, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
