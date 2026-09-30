"""Prepare the regional visual experiment, preserving the earlier geometry probe.

Run with pipeline/.venv/bin/python. No application files or dependencies change.
County source metadata specifies capture ranges, rather than publication dates.
"""
from pathlib import Path
import json
import shutil
import urllib.request
import ssl
import certifi
import hashlib
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'data/out/scene-prototype'
CACHE = ROOT / 'data/raw/palisades-map'
COUNTY = 'https://rpgis.isd.lacounty.gov/Geocortex/Essentials/REST/sites/GISNET_Public/map/mapservices/'
BOUNDS = [-118.585, 34.024, -118.493, 34.103]


def fetch(url, name):
    path = CACHE / name
    if not path.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (OpenPali local visual research)'})
        with urllib.request.urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=40) as r:
            data = r.read()
        if data.lstrip().startswith(b'{') and 'error' in json.loads(data):
            raise ValueError(f'Error response: {url}')
        path.write_bytes(data)
    return path.read_bytes()


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    CACHE.mkdir(exist_ok=True, parents=True)
    if not (OUT / 'geometry-probe.html').exists() and (OUT / 'index.html').exists():
        shutil.copyfile(OUT / 'index.html', OUT / 'geometry-probe.html')
    for name in ['maplibre-gl.js', 'maplibre-gl.css', 'LICENSE.txt']:
        src = ROOT / 'web/node_modules/maplibre-gl' / ('dist/' + name if name != 'LICENSE.txt' else name)
        if src.exists():
            shutil.copyfile(src, OUT / name)
    shutil.copyfile(Path(__file__).with_name('building_layer.js'), OUT / 'building_layer.js')
    sources = []
    for key, service in [('july2026', '81'), ('october2025', '78'), ('january2025', '74'), ('summer2024', '80')]:
        raw = fetch(COUNTY + service + '?f=json', f'{key}-metadata.json')
        j = json.loads(raw)
        layer = j['layers'][0]
        sources.append({'id': key, 'title': j['displayName'], 'capture': layer['description'],
                        'layer': layer['name'], 'metadata_url': COUNTY + service + '?f=json',
                        'metadata_sha256': hashlib.sha256(raw).hexdigest()})
    style = json.loads(fetch('https://www.arcgis.com/sharing/rest/content/items/158bf6940d0446e59ac468c3da7d48d6/resources/styles/root.json', 'county-labels.json'))
    labels = []
    for layer in style['layers']:
        if layer['type'] == 'symbol' and layer['id'].startswith('Streets/label/') and 'text-field' in layer.get('layout', {}) and 'icon-image' not in layer.get('layout', {}) and 'Address' not in layer['id']:
            layer['layout']['text-pitch-alignment'] = 'viewport'
            layer['layout']['text-rotation-alignment'] = 'map'
            layer['paint'] = {'text-color': '#ffffff', 'text-halo-color': '#15252b', 'text-halo-width': 1.5, 'text-halo-blur': 0.8}
            labels.append(layer)
    source = style['sources']['esri']
    source.pop('url', None)  # Explicit ArcGIS tile URL is already in the source.
    source['bounds'] = BOUNDS
    (OUT / 'labels.json').write_text(json.dumps({'source': source, 'glyphs': style['glyphs'], 'layers': labels}))
    release = json.loads((ROOT / 'data/out/evidence/current.json').read_text())
    parcels = json.loads((ROOT / 'data/out/evidence' / release['release_id'] / 'parcels.geojson').read_text())
    keep = []
    for f in parcels['features']:
        geom = f.get('geometry')
        if not geom:
            continue
        coords = geom['coordinates']
        polygons = coords if geom['type'] == 'MultiPolygon' else [coords]
        points = [xy for p in polygons for ring in p for xy in ring]
        if any(BOUNDS[0] <= p[0] <= BOUNDS[2] and BOUNDS[1] <= p[1] <= BOUNDS[3] for p in points):
            f['properties']['center'] = [sum(p[i] for p in points) / len(points) for i in [0, 1]]
            keep.append(f)
    (OUT / 'parcels.json').write_text(json.dumps({'type': 'FeatureCollection', 'features': keep}, separators=(',', ':')))
    (OUT / 'imagery.json').write_text(json.dumps({'sources': sources, 'bounds': BOUNDS,
        'parcel_release': release['release_id'], 'parcel_count': len(keep)}, indent=2))
    aoi = json.loads((ROOT / 'pipeline/openpali/spatial/palisades_aoi.geojson').read_text())
    (CACHE / 'dem').mkdir(exist_ok=True)
    def dem(tile):
        name = tile['name'] + '.tif'
        url = aoi['source']['staged_base'] + '/' + name
        raw = fetch(url, 'dem/' + name)
        if raw[:4] not in [b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+']:
            raise ValueError('Expected USGS TIFF terrain data')
        return {'name': name, 'url': url, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    with ThreadPoolExecutor(max_workers=4) as executor:
        terrain_sources = list(executor.map(dem, aoi['tiles']))
    (CACHE / 'dem/sources.json').write_text(json.dumps(terrain_sources, indent=2))
    shutil.copyfile(Path(__file__).with_name('regional_preview.html'), OUT / 'index.html')
    print(json.dumps({'parcels': len(keep), 'label_layers': len(labels), 'imagery': sources}, indent=2))


if __name__ == '__main__':
    main()
