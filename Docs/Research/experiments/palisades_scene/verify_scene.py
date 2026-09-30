"""Verify a compiled scene and check its APN relationships independently.

Usage: pipeline/.venv/bin/python .../verify_scene.py --scene data/out/scene-prototype/index.html --out /tmp/parcel-check.json
Checks parcel containment against the actual portable release. Reports outliers;
centroid containment is a relationship diagnostic, not surveyed accuracy.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pyproj
from shapely.geometry import Point, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'pipeline'))
from core.spatial.geodesy import ecef_to_wgs84, enu_rotation, wgs84_to_ecef


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    text = args.scene.read_text()
    scene = json.loads(text.split('const DATA=', 1)[1].split(';\nconst canvas=', 1)[0])
    structures = scene['structures']
    assert len({s['id'] for s in structures}) == len(structures), 'Structure identities collide'
    assert all(s['physical_condition'] == 'unknown' and s['geometry_role'] == 'historical_reference' for s in structures), 'Historical geometry asserts a physical condition'
    assert all(len(s['apn']) == 10 and s['apn'].isdigit() for s in structures), 'Invalid APN'
    raw = base64.b64decode(scene['buildings'])
    assert hashlib.sha256(raw).hexdigest() == scene['geometry_sha256'], 'Geometry hash mismatch'
    packets = {name: np.frombuffer(base64.b64decode(scene[name]), '<f4').reshape(-1, 3, 10) for name in ['buildings', 'ground']}
    for packet in packets.values():
        assert np.all(np.isfinite(packet)), 'Non-finite render data'
        assert np.all(packet[:, :, 6] == packet[:, :1, 6]), 'A render triangle mixes feature identities'
    assert set(packets['buildings'][:, 0, 6].astype(int)) == {s['gpu_index'] for s in structures}, 'Render IDs do not match structure table'
    assert np.all(packets['ground'][:, :, 6] == 0), 'Terrain acquired a building ID'
    release = json.loads((ROOT / 'data/out/evidence/current.json').read_text())['release_id']
    parcelpath = ROOT / 'data/out/evidence' / release / 'parcels.geojson'
    parcels = json.loads(parcelpath.read_text())
    project = pyproj.Transformer.from_crs(4326, 26911, always_xy=True).transform
    by_apn = {f['properties']['apn']: transform(project, shape(f['geometry'])) for f in parcels['features']}
    origin = scene['origin_lon_lat_h']
    rotation, ecef = enu_rotation(*origin[:2]), wgs84_to_ecef(*origin)
    matched, missing = [], []
    for s in structures:
        if s['apn'] not in by_apn:
            missing.append(s['apn'])
            continue
        lon, lat, _ = ecef_to_wgs84(np.array(s['center_enu']) @ rotation + ecef)
        point = Point(*project(float(lon), float(lat)))
        matched.append({'id': s['id'], 'apn': s['apn'], 'distance_m': by_apn[s['apn']].distance(point)})
    result = {
        'protocol_checks_passed': True, 'parcels_release': release,
        'parcels_path': str(parcelpath.relative_to(ROOT)),
        'parcels_sha256': hashlib.sha256(parcelpath.read_bytes()).hexdigest(),
        'structures_matched': len(matched), 'missing_apns': sorted(set(missing)),
        'centroid_inside_or_on_parcel': sum(r['distance_m'] == 0 for r in matched),
        'centroid_max_distance_m': max((r['distance_m'] for r in matched), default=None),
        'nonzero': sorted([r for r in matched if r['distance_m'] > 0], key=lambda r: -r['distance_m']),
        'interpretation': 'Mesh-average positions checked against release parcel polygons. Outliers require investigation of source association, geometry extent, and parcel versions; this is not surveyed registration accuracy.',
    }
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
