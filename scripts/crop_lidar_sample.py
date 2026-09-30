"""Crop an acquired survey tile to a parcel plus a documented context buffer.

This produces measured points and a QA plot, not a recovery-stage prediction.
The CRS below is from the 2025 Palisades USGS project report.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

import laspy
import numpy as np
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import transform


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tile', type=Path, required=True)
    parser.add_argument('--parcels', type=Path, required=True)
    parser.add_argument('--ain', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    matches = [f for f in json.loads(args.parcels.read_text())['features']
               if f['properties']['AIN'] == args.ain]
    if len(matches) != 1:
        raise ValueError('parcel must match exactly once')
    project = Transformer.from_crs(4326, 6340, always_xy=True)
    parcel = transform(project.transform, shape(matches[0]['geometry']))
    clip = parcel.buffer(5)
    xmin, ymin, xmax, ymax = clip.bounds
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f'{args.ain}-20250121-context.laz'
    coords, classes, seen = [], Counter(), 0
    with laspy.open(args.tile) as reader:
        expected = reader.header.point_count
        with laspy.open(path, mode='w', header=reader.header) as writer:
            for points in reader.chunk_iterator(1_000_000):
                seen += len(points)
                x, y = np.asarray(points.x), np.asarray(points.y)
                bounding = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)
                candidates = points[bounding]
                selected = candidates[contains_xy(clip, np.asarray(candidates.x), np.asarray(candidates.y))]
                if len(selected):
                    writer.write_points(selected)
                    coords.append(np.column_stack([selected.x, selected.y, selected.z]))
                    classes.update(map(int, selected.classification))
    if seen != expected or not coords:
        raise ValueError('incomplete tile read or no points in parcel crop')
    xyz = np.concatenate(coords)
    report = {'ain': args.ain, 'acquisition_date': '2025-01-21',
              'capture_date_evidence': 'USGS Palisades C25 project report, section 1.4',
              'tile_path': str(args.tile), 'tile_points_read': seen,
              'horizontal_crs': 'EPSG:6340', 'vertical_reference': 'NAVD88 / GEOID18, meters',
              'parcel_source_path': str(args.parcels), 'context_buffer_meters': 5,
              'points_in_crop': len(xyz), 'source_classification_counts': dict(classes),
              'z_range_meters': [float(xyz[:, 2].min()), float(xyz[:, 2].max())],
              'crop_path': str(path), 'crop_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'interpretation': 'historical measured surface, not current condition or a structural inspection'}
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/openpali-mpl')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    origin = np.array([xmin, ymin, 0])
    local = xyz - origin
    fig = plt.figure(figsize=(12, 5.8), constrained_layout=True)
    ax = fig.add_subplot(121)
    sc = ax.scatter(local[:, 0], local[:, 1], c=xyz[:, 2], s=1, cmap='viridis', rasterized=True)
    polygons = [parcel] if parcel.geom_type == 'Polygon' else list(parcel.geoms)
    for polygon in polygons:
        xy = np.asarray(polygon.exterior.coords)
        ax.plot(xy[:, 0] - xmin, xy[:, 1] - ymin, color='#db5949', linewidth=1.4)
    ax.set(aspect='equal', xlabel='Easting from crop origin (m)', ylabel='Northing from crop origin (m)', title='Plan view · red line is parcel boundary')
    fig.colorbar(sc, ax=ax, label='Survey elevation (m, NAVD88)', shrink=.72)
    ax3 = fig.add_subplot(122, projection='3d')
    # Thin only the preview deterministically; the output LAZ retains every selected point.
    preview = local[::max(1, len(local)//40000)]
    ax3.scatter(preview[:, 0], preview[:, 1], preview[:, 2], c=preview[:, 2], s=.5, cmap='viridis', rasterized=True)
    ax3.set(xlabel='Easting (m)', ylabel='Northing (m)', zlabel='Elevation (m)', title='Measured surface · 5 m context buffer')
    ax3.view_init(elev=28, azim=-62)
    fig.suptitle(f'APN {args.ain} · USGS LiDAR acquired 21 Jan 2025\nHistorical baseline; no current rebuild stage inferred', fontsize=13)
    figure = args.output / f'{args.ain}-20250121-preview.png'
    fig.savefig(figure, dpi=180, bbox_inches='tight', pad_inches=.35)
    plt.close(fig)
    report['preview_path'] = str(figure)
    report_path = args.output / 'report.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
