"""Integrity checks for a built scene. Exits non-zero on the first failure.

    python -m openpali.scene.verify [scene-dir]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from .build import SCHEMA, VERTEX_BYTES
from .sources import OUT, ROOT
from .terrain import decode_terrarium

VERTEX = np.dtype([('pos', '<u2', 3), ('oct', 'i1', 2), ('id', '<u2'), ('uv', '<u2', 2), ('pad', '<u2')])


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f'FAIL: {message}')


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    scene = Path(argv[0]) if argv else OUT / json.loads((OUT / 'current.json').read_text())['scene_id']
    manifest = json.loads((scene / 'manifest.json').read_text())
    check(manifest['schema'] == SCHEMA, f'schema is {manifest["schema"]}')
    check(manifest['new_physical_conditions_produced'] is False, 'scene must not claim physical conditions')

    structures = manifest['structures']
    ids = [s['gpu_id'] for s in structures]
    check(ids == list(range(1, len(ids) + 1)), 'structure ids are not dense from 1')
    check(len(ids) < 65536, 'structure ids exceed the 16-bit vertex attribute')
    for key in ('base_m', 'height_m', 'ground_delta_m', 'ground_m'):
        values = np.asarray([s[key] for s in structures], dtype=np.float64)
        check(bool(np.isfinite(values).all()), f'non-finite {key}')
    check(all(s['height_m'] >= 0 for s in structures), 'negative structure height')

    drawn: set[int] = set()
    triangles = 0
    for node in manifest['nodes']:
        vertex_bytes = (scene / manifest['buffers'] / f'{node["id"]}.vertices.bin').read_bytes()
        index_bytes = (scene / manifest['buffers'] / f'{node["id"]}.indices.bin').read_bytes()
        check(hashlib.sha256(vertex_bytes).hexdigest() == node['vertex_sha256'], f'node {node["id"]} vertex hash')
        check(hashlib.sha256(index_bytes).hexdigest() == node['index_sha256'], f'node {node["id"]} index hash')
        check(len(vertex_bytes) == node['vertex_count'] * VERTEX_BYTES, f'node {node["id"]} vertex length')
        vertices = np.frombuffer(vertex_bytes, dtype=VERTEX)
        indices = np.frombuffer(index_bytes, dtype='<u2' if node['index_type'] == 'u16' else '<u4').reshape(-1, 3)
        check(indices.size == node['index_count'], f'node {node["id"]} index count')
        check(int(indices.max()) < len(vertices), f'node {node["id"]} index out of range')
        owners = vertices['id'][indices]
        check(bool((owners == owners[:, :1]).all()), f'node {node["id"]} has a triangle spanning two structures')
        check(int(vertices['id'].min()) >= 1 and int(vertices['id'].max()) <= len(ids), f'node {node["id"]} id out of range')
        grid = node['grid']
        check(all(e > 0 and np.isfinite(e) for e in grid['extent']), f'node {node["id"]} grid extent')
        # each structure's lowest dequantized vertex must agree with its table entry
        z = grid['min'][2] + vertices['pos'][:, 2].astype(np.float64) / 65535 * grid['extent'][2]
        for structure_id in np.unique(vertices['id'])[:50]:
            base = structures[int(structure_id) - 1]['base_m']
            check(abs(float(z[vertices['id'] == structure_id].min()) - base) <= grid['extent'][2] / 65535 + 2e-3,
                  f'structure {int(structure_id)} base differs from its geometry')
        drawn.update(np.unique(vertices['id']).tolist())
        triangles += len(indices)
    check(drawn == set(ids), f'{len(set(ids) - drawn)} structures have no geometry')

    terrain = manifest.get('terrain')
    tiles = 0
    if terrain:
        digest = hashlib.sha256()
        for z, entries in terrain['index'].items():
            for x, y in entries:
                path = scene / 'terrain' / z / str(x) / f'{y}.png'
                check(path.exists(), f'terrain tile {z}/{x}/{y} is indexed but absent')
                digest.update(f'{z}/{x}/{y}:'.encode() + hashlib.sha256(path.read_bytes()).digest())
                tiles += 1
        check(digest.hexdigest() == terrain['sha256'], 'terrain tiles differ from the manifest hash')
        z, (x, y) = next((z, entries[len(entries) // 2]) for z, entries in terrain['index'].items() if entries)
        height = decode_terrarium((scene / 'terrain' / z / str(x) / f'{y}.png').read_bytes())
        check(height.shape == (256, 256) and bool(np.isfinite(height).all()), 'terrain tile does not decode')
        check(-100 < float(height.min()) and float(height.max()) < 1200, 'terrain heights outside the Santa Monica Mountains')

    deltas = np.asarray([s['ground_delta_m'] for s in structures])
    print(json.dumps({
        'scene': str(scene.relative_to(ROOT)), 'structures': len(ids), 'batches': len(manifest['nodes']),
        'triangles': triangles, 'terrain_tiles': tiles,
        'ground_delta_m': {'median': round(float(np.median(deltas)), 2),
                           'p05': round(float(np.percentile(deltas, 5)), 2),
                           'p95': round(float(np.percentile(deltas, 95)), 2)},
        'result': 'PASS',
    }, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
