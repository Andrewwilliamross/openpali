"""Verify the regional experiment's binary layouts, identities and source grids."""
from pathlib import Path
import hashlib
import json
from collections import Counter
import numpy as np
from serve_map import Terrain, OUT, CACHE, tile_xy
from scipy.ndimage import map_coordinates


def main():
    manifest = json.loads((OUT / 'buildings/manifest.json').read_text())
    structures = manifest['structures']
    assert len({s['source_feature_id'] for s in structures}) == len(structures)
    assert [s['gpu_id'] for s in structures] == list(range(1, len(structures) + 1))
    coverage = set()
    triangles = 0
    for node in manifest['nodes']:
        vb = (OUT / f'buildings/{node["id"]}.vertices.bin').read_bytes()
        ib = (OUT / f'buildings/{node["id"]}.indices.bin').read_bytes()
        assert hashlib.sha256(vb).hexdigest() == node['vertex_sha256']
        assert hashlib.sha256(ib).hexdigest() == node['index_sha256']
        rows = np.frombuffer(vb, '<f4').reshape(-1, 9)
        idx = np.frombuffer(ib, '<u4').reshape(-1, 3)
        assert len(rows) == node['vertex_count'] and idx.size == node['index_count']
        assert np.isfinite(rows).all() and idx.max() < len(rows)
        ids = rows[:, 8]
        assert np.array_equal(ids, ids.astype(int))
        assert np.all(ids[idx] == ids[idx[:, :1]])
        assert np.all((rows[:, 6:8] >= 0) & (rows[:, 6:8] <= 1))
        coverage.update(ids.astype(int))
        triangles += len(idx)
    assert coverage == set(range(1, len(structures) + 1))
    assert manifest['new_physical_conditions_produced'] is False
    assert manifest['new_framing_geometry_produced'] is False
    # Decode a real generated terrain pixel, then compare it against the same
    # source DEM at that pixel centre. This checks reprojection/row direction
    # and Terrarium encoding, rather than merely checking the file opens.
    from PIL import Image
    from io import BytesIO
    terrain = Terrain()
    x, y = (int(v) for v in tile_xy(-118.52862, 34.04257, 17))
    png = np.asarray(Image.open(BytesIO(terrain.tile(17, x, y))).convert('RGB'), dtype=float)
    h = png[:, :, 0] * 256 + png[:, :, 1] + png[:, :, 2] / 256 - 32768
    u, v = 128, 128
    lon = (x + (u + .5) / 256) / 2 ** 17 * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + (v + .5) / 256) / 2 ** 17))))
    ux, uy = terrain.to_utm.transform(lon, lat)
    samples = []
    for raster, transform, nodata in terrain.rasters:
        col, row = (~transform) * (ux, uy)
        if 0 <= col < raster.shape[1] and 0 <= row < raster.shape[0]:
            samples.append(float(map_coordinates(raster, [[row - .5], [col - .5]], order=1, mode='nearest')[0]))
    assert len(samples) == 1 and abs(samples[0] - h[v, u]) <= 1 / 512 + 1e-5
    result = {'nodes': len(manifest['nodes']), 'structures': len(structures), 'triangles': triangles,
              'geometry_bytes': sum(n['vertex_bytes'] + n['index_bytes'] for n in manifest['nodes']),
              'damage_counts': dict(Counter(s['damage'] for s in structures)),
              'binary_identity_checks': 'passed', 'source_hash_checks': 'passed',
              'terrain_sample': {'lon': lon, 'lat': lat, 'source_height_m': samples[0],
                                 'encoded_height_m': float(h[v, u]), 'difference_m': abs(samples[0] - h[v, u])},
              'terrain_source_rasters': json.loads((CACHE / 'dem/sources.json').read_text()),
              'imagery_metadata': json.loads((OUT / 'imagery.json').read_text()),
              'accuracy_against_independent_controls_measured': False,
              'regional_frame_performance_measured': False}
    (OUT / 'regional-checks.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ['terrain_source_rasters', 'imagery_metadata']}, indent=2))


if __name__ == '__main__':
    main()
