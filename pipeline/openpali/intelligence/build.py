"""Build a deterministic evidence release from verified acquisition manifests.

No network requests, fabricated observations, or production pointer changes.
Run: PYTHONPATH=pipeline python -m openpali.intelligence.build
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform
from shapely.strtree import STRtree

from openpali.discovery.clearance import approved_pdf_url
from openpali.identity.ids import property_id_from_apn
from openpali.intelligence.market import screen_transfer, market_support
from openpali.intelligence.permits import permit_stage, timing_summary

POLICY = 'evidence-v1'
RESEARCH = 'Docs/Research/2026-09-24-'


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(body):
    return hashlib.sha256(body).hexdigest()


def checked(root: Path, path: str, sha: str | None = None):
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('input path leaves repository')
    body = target.read_bytes()
    if sha and digest(body) != sha:
        raise ValueError(f'input hash mismatch: {path}')
    return body


def read_manifest(root, name, inputs):
    path = RESEARCH + name + '.json'
    body = checked(root, path)
    inputs.append({'path': path, 'sha256': digest(body)})
    return json.loads(body)


def source_ref(source_id, url, observed_at, sha, *, captured_at=None):
    return dict(source_id=source_id, url=url, observed_at=observed_at,
                captured_at=captured_at, sha256=sha)


def apn_id(value):
    value = re.sub(r'[^0-9]', '', str(value))
    if len(value) != 10:
        raise ValueError('invalid parcel identifier')
    return value


def property_row(apn, address=''):
    return dict(apn=apn, property_id=property_id_from_apn(apn), address=address,
                cohorts=[], damage='unknown', stage='unknown', geometry=None,
                parcel={}, cleanup=None, assessor=None, permits=[], permit_records=[], inspection_requests=[], visuals=[],
                utilities=[], evidence=[], market_events=[], listings=[], neighborhood={}, tasks=[])


def cleanup_stage(row):
    # Exact source values. A PDF link/withdrawal/private participation is not completion.
    progress = row.get('REBUILD_PROGRESS')
    stage = {'Construction Completed':'construction_complete', 'Rebuild In Construction':'construction',
             'Building Permits Issued':'permit','Building Plans Approved':'design'}.get(progress)
    if stage:
        return stage
    if row.get('BUILD_PLAN_APPROVED') == 'Building Plans Approved':
        return 'design'
    if progress == 'Rebuild Applications Received':
        return 'application'
    if row.get('ROE_STATUS') == 'Final Sign Off - Complete' or row.get('DEBRIS_REMOVAL_EPICLA') == 'Finaled':
        return 'cleanup'
    return 'unknown'


def add_task(p, kind, reason, sources, priority=1):
    p['tasks'].append(dict(task_id=digest(encoded([p['apn'], kind]))[:24],
                           apn=p['apn'], kind=kind, reason=reason,
                           next_sources=sources, priority=priority, status='open'))


def spatial_features(properties):
    """Metric geometry distances; damaged-neighbor exposure, never inferred vacancy."""
    project = Transformer.from_crs(4326, 26911, always_xy=True).transform
    rows = [p for p in properties.values() if p['geometry']]
    geoms = [transform(project, shape(p['geometry'])) for p in rows]
    tree = STRtree(geoms)
    for i, p in enumerate(rows):
        features = {}
        for radius in (100, 250, 500):
            indices = [int(j) for j in tree.query(geoms[i], predicate='dwithin', distance=radius) if int(j) != i]
            destroyed = [rows[j] for j in indices if rows[j]['damage'] == 'destroyed']
            features[str(radius)] = dict(parcel_count=len(indices), destroyed_count=len(destroyed),
                destruction_share=len(destroyed) / len(indices) if indices else None,
                construction_evidence_count=sum(q['stage'] == 'construction' for q in destroyed),
                unknown_damage_count=sum(rows[j]['damage'] == 'unknown' for j in indices))
        p['neighborhood'] = dict(method='EPSG:26911 parcel-edge distance; self excluded',
            measures=features, vacancy_share=None,
            limitation='Destruction is historical. Current vacancy and standing-home status require observations; cohort edges may omit neighbors.')
        if p['apn'] in ('4412013017', '4412006025', '4416020028'):
            p['parcel']['geometry_area_sqft'] = round(geoms[i].area * 10.7639104)


def build(root: Path, out: Path):
    inputs, properties, sources, unmatched = [], {}, [], []
    universe = read_manifest(root, 'parcel-universe', inputs)
    if universe['status'] != 'complete':
        raise ValueError('parcel acquisition incomplete')
    geo = json.loads(checked(root, universe['path'], universe['sha256']))
    uref = source_ref('county_parcels', universe['source'], universe['completed_at'], universe['sha256'])
    for f in geo['features']:
        a = f['properties']; apn = apn_id(a['AIN'])
        if apn in properties or not shape(f['geometry']).is_valid:
            raise ValueError('duplicate identity or invalid geometry')
        p = property_row(apn, a.get('SitusFullAddress') or '')
        p.update(geometry=f['geometry'], parcel=a, cohorts=['zip_90272'])
        p['evidence'].append(uref); properties[apn] = p
    if len(properties) != universe['features']:
        raise ValueError('parcel count mismatch')
    sources.append(dict(**uref, count=len(properties), shape='parcel polygons + assessment attributes',
                        limitation='ZIP cohort, not an exact Palisades boundary. Assessments are not market values.'))

    clearance = read_manifest(root, 'clearance-inventory', inputs)
    raw_index = checked(root, clearance['index_path'], clearance['index_sha256'])
    rows = [json.loads(line) for line in raw_index.splitlines() if line]
    if len(rows) != clearance['unique_apns'] or len({apn_id(r['APN']) for r in rows}) != len(rows):
        raise ValueError('clearance identity/count mismatch')
    cref = source_ref('county_cleanup', clearance['source'], clearance['completed_at'], clearance['index_sha256'])
    profiles = {d.get('url'): d for d in clearance.get('documents', [])}
    for row in rows:
        apn = apn_id(row['APN'])
        p = properties.setdefault(apn, property_row(apn, row.get('SITUSFULLADDRESS') or ''))
        p['cohorts'].append('destroyed_palisades_fire')
        p['damage'] = 'destroyed'; p['stage'] = cleanup_stage(row)
        p['cleanup'] = dict(row, document_url=row['FSO_URL'] if approved_pdf_url(row.get('FSO_URL')) else None,
                            document_semantics='Unreviewed packet; link presence does not establish completion.')
        p['evidence'].append(cref)
        if p['stage'] == 'unknown':
            add_task(p, 'cleanup_verification', 'Current cleanup outcome unresolved in acquired records',
                     ['County EPIC-LA', 'USACE/private sign-off packet', 'dated site photographs'], 3)
    sources.append(dict(**cref, count=len(rows), shape='cleanup/status rows and PDF links',
                        limitation='Destroyed cohort only. A withdrawal packet can share the sign-off URL field.'))

    lookup = read_manifest(root, 'parcel-lookup', inputs)
    extra = json.loads(checked(root, lookup['path'], lookup['sha256']))
    lref = source_ref('county_parcel_lookup', lookup['source'], lookup['completed_at'], lookup['sha256'])
    for feature in extra['features']:
        attrs = feature['properties']; apn = apn_id(attrs['AIN'])
        geom = shape(feature['geometry'])
        if not geom.is_valid or geom.is_empty or geom.area <= 0:
            raise ValueError('invalid lookup geometry')
        p = properties.setdefault(apn, property_row(apn, attrs.get('SitusFullAddress') or ''))
        p['geometry'] = feature['geometry']; p['parcel'] = attrs
        p['cohorts'].append('exact_ain_lookup')
        p['evidence'].append(lref)
    sources.append(dict(**lref, count=len(extra['features']), shape='exact AIN parcel polygons',
                        limitation=f"{len(lookup['unresolved'])} AINs unresolved; parcel lineage review required."))

    assessor_reports = [read_manifest(root, name, inputs) for name in ('assessor-portal', 'assessor-standing-sample')]
    recipe = root / 'Docs/Research/evidence-extra-inputs.json'
    if recipe.exists():
        for path in json.loads(recipe.read_bytes()):
            body = checked(root, path)
            inputs.append(dict(path=path, sha256=digest(body)))
            assessor_reports.append(json.loads(body))
    for report in sorted(assessor_reports, key=lambda r:r['completed_at']):
        for sample in report['parcels']:
            if sample['status'] != 'complete':
                continue
            record = json.loads(checked(root, sample['path'], sample['sha256']))
            apn = apn_id(record['ain'])
            if apn not in properties:
                unmatched.append(dict(apn=apn, source='assessor_portal', path=sample['path'],
                    sha256=sample['sha256'], reason='AIN absent from acquired property universe; resolve parcel history before linking',
                    profile=record['profile']))
                continue
            p = properties[apn]; payload = record['payloads']
            p['assessor'] = dict(detail=payload['parceldetail']['Parcel'],
                assessments=payload['parcel_assessmenthistory']['Parcel_AssessmentHistory'],
                transfers=payload['parcel_ownershiphistory']['Parcel_OwnershipHistory'],
                changes=payload['parcel_parcelchange']['Parcel_ChangeHistory'], profile=record['profile'])
            ref = source_ref('assessor_portal', report['source']+'parceldetail?ain='+apn,
                             report['completed_at'], sample['sha256'])
            p['evidence'].append(ref)
            p['market_events'] = [dict(screen_transfer(r), evidence=ref) for r in p['assessor']['transfers']]
    sources.append(dict(source_id='assessor_portal', count=sum(bool(p['assessor']) for p in properties.values()),
        shape='assessment, transfer and parcel-history JSON', url='https://portal.assessor.lacounty.gov/',
        limitation='Sample coverage. Transfer-tax-derived prices require screening; 2027 preparation is not the 2026 current roll.'))

    listings = read_manifest(root, 'listing-observations', inputs)
    for listing in listings['observations']:
        if listing['apn'] not in properties:
            raise ValueError('listing APN must be resolved before joining')
        properties[listing['apn']]['listings'].append(dict(listing,
            observed_at=listings['observed_date'], capture_method=listings['capture_method']))
    sources.append(dict(source_id='listing_samples', count=len(listings['observations']),
        url='https://www.redfin.com/CA/Pacific-Palisades/758-Radcliffe-Ave-90272/home/6841381',
        shape='browser-verified listing facts and events', limitation='Two transcribed research samples; not a continuous listing feed or closed-sale labels.'))

    permit_inventory = read_manifest(root, 'permit-inventory', inputs)
    if permit_inventory['status'] != 'complete':
        raise ValueError('incomplete permit inventory')
    permit_links = {}
    permit_timing = {}
    ranks = {stage:i for i,stage in enumerate(['unknown','cleanup','application','design','permit','construction','construction_complete','occupancy'])}
    for table in permit_inventory['tables']:
        records = json.loads(checked(root, table['path'], table['sha256']))
        ref = source_ref(table['source_id'],table['source'],table['observed_at'],table['sha256'])
        linked = 0
        if table['source_id'] == 'ladbs_permits':
            permit_timing = timing_summary(records, table['observed_at'])
        for record in records:
            if table['source_id'] == 'ladbs_permits':
                try: apn = apn_id(record.get('APN'))
                except ValueError: continue
                if apn not in properties: continue
                p = properties[apn]; p['permit_records'].append(record)
                permit_links.setdefault(record['PERMIT'],set()).add(apn)
                # Explicit residential use protects against advancing a house
                # from completion of its ADU, garage or accessory structure.
                stage = permit_stage(record, table['observed_at'])
                if ranks[stage] > ranks[p['stage']]: p['stage'] = stage
            else:
                apns = permit_links.get(record.get('PERMIT'),set())
                if len(apns) != 1: continue
                p = properties[next(iter(apns))]
                # Requests retained verbatim. Scheduled does not mean performed.
                p['inspection_requests'].append(record)
            if ref not in p['evidence']: p['evidence'].append(ref)
            linked += 1
        sources.append(dict(**ref,count=len(records),linked_records=linked,
            shape='permit milestone rows' if table['source_id']=='ladbs_permits' else 'scheduled inspection requests',
            limitation='Primary-home color changes require explicit residential use; accessory permits remain evidence.' if table['source_id']=='ladbs_permits' else 'Requests are not inspection outcomes. PCIS carries the sampled actual outcomes.'))

    pcis = read_manifest(root, 'pcis-browser', inputs)
    dom = json.loads(checked(root, pcis['path'], pcis['sha256']))
    details = dict(dom['detail']); permit = details['Application / Permit']
    # Source detail contains the address; resolve only an exact house/street match.
    heading = next(s['heading'] for s in dom['sections'] if s['heading'].startswith('Certificate Information'))
    matches = [p for p in properties.values() if re.search(r'\b1201\b', p['address']) and 'VILLA WOODS' in p['address']]
    if '1201 N VILLA WOODS DR' not in heading or len(matches) != 1:
        raise ValueError('PCIS address link is ambiguous; review required')
    ref = source_ref('ladbs_pcis', pcis['source_url'], pcis['archived_at'], pcis['sha256'])
    matches[0]['permits'].append(dict(permit=permit, details=details,
        sections=dom['sections'], evidence=ref, link_method='unique exact house and street in ZIP cohort'))
    matches[0]['evidence'].append(ref)
    sources.append(dict(**ref, count=1, shape='permit status, clearance, professional and inspection tables',
                        limitation='One browser-acquired permit. Approval of one inspection is not whole-project completion.'))

    probes = read_manifest(root, 'context-probes', inputs)
    sewer = next(p for p in probes if p['name'] == 'sewer_near_677')
    properties['4412013017']['utilities'].append(dict(kind='sewer', radius_m=50,
        features=sewer['body']['features'], evidence=source_ref('la_sewer',sewer['url'],sewer['retrieved_at'],sewer['sha256']),
        limitation='Nearby public sewer segments. Does not prove this parcel is connected; pipe-size units unverified.'))
    materials = next((p for p in probes if p['name'] == 'materials'), None)
    visual = read_manifest(root, 'visual-baseline', inputs); crop = visual['parcel_crop']
    assets = {}
    for key, hashkey, name in [('preview_path','preview_sha256','lidar-preview.png'),('crop_path','crop_sha256','lidar-context.laz')]:
        assets[name] = checked(root, crop[key], crop[hashkey])
    properties[crop['ain']]['visuals'].append(dict(kind='classified_lidar', captured_at=crop['acquisition_date'],
        measurements=read_manifest(root, 'lidar-measurements', inputs),
        observed_at=visual['retrieved_at'], points=crop['points_in_crop'], crs=crop['horizontal_crs'],
        vertical_reference=crop['vertical_reference'], preview='lidar-preview.png', asset='lidar-context.laz',
        evidence=source_ref('usgs_lidar', visual['report_url'], visual['retrieved_at'], crop['crop_sha256'], captured_at=crop['acquisition_date']),
        limitation=crop['interpretation']))
    sources.append(dict(source_id='usgs_lidar', count=1, url=visual['catalog_url'], shape='3D classified points + QA image',
                        captured_at=crop['acquisition_date'], limitation='One processed parcel sample; historical, not current framing labels.'))
    sources.append(dict(source_id='la_sewer', count=len(sewer['body']['features']), url=sewer['url'], shape='pipe lines and engineering attributes', limitation='One 50 m sample; no water pressure, electricity or gas telemetry.'))
    spatial_features(properties)
    for p in properties.values():
        if not p['assessor']:
            add_task(p, 'property_history', 'Transfer and assessment history not yet acquired', ['Assessor public JSON'], 1)
        if not p['geometry']:
            add_task(p, 'parcel_geometry', 'Outside acquired ZIP geometry cohort', ['Assessor parcel lineage', 'historical assessor map sheet', 'County parcel GIS by APN'], 2)
        add_task(p, 'current_visual', 'Current physical site condition not established', ['recent aerial', 'street-level photo', 'authorized site capture'], 2)
        p['market_support'] = market_support(p['market_events'])
    counts = dict(properties=len(properties), mapped=sum(bool(p['geometry']) for p in properties.values()),
                  destroyed=sum(p['damage']=='destroyed' for p in properties.values()),
                  pdf_links=sum(bool(p['cleanup'] and p['cleanup']['document_url']) for p in properties.values()),
                  assessor_histories=sum(bool(p['assessor']) for p in properties.values()),
                  inspection_permits=sum(len(p['permits']) for p in properties.values()),
                  linked_permits=sum(len(p['permit_records']) for p in properties.values()),
                  inspection_requests=sum(len(p['inspection_requests']) for p in properties.values()),
                  acquisition_tasks=sum(len(p['tasks']) for p in properties.values()))
    payload = dict(schema_version=POLICY, inputs=inputs, counts=counts, sources=sources,
        coverage=dict(cohort='ZIP 90272 union Palisades Fire destroyed parcels',
            limitation='Not a complete neighborhood boundary. No damage record means unknown, not undamaged. Missing geometries remain searchable.'),
        properties=properties, materials=materials, permit_timing=permit_timing, unmatched_evidence=unmatched)
    release_id = 'evidence-' + digest(encoded(payload))[:24]
    payload['release_id'] = release_id
    dest = out / release_id; dest.mkdir(parents=True, exist_ok=True)
    outputs = {'release.json': encoded(payload), **assets}
    features = [dict(type='Feature', id=p['apn'], geometry=p['geometry'], properties={k:p[k] for k in ('apn','address','stage','damage')}) for p in properties.values() if p['geometry']]
    outputs['parcels.geojson'] = encoded(dict(type='FeatureCollection', features=features))
    for name, body in outputs.items():
        path = dest / name
        if path.exists() and path.read_bytes() != body:
            raise ValueError('immutable release collision')
        path.write_bytes(body)
    manifest = dict(release_id=release_id, schema_version=POLICY, counts=counts,
                    artifacts={name:dict(sha256=digest(body), bytes=len(body)) for name,body in outputs.items()})
    (dest/'manifest.json').write_bytes(encoded(manifest))
    out.mkdir(parents=True, exist_ok=True)
    tmp = out/'current.tmp'; tmp.write_bytes(encoded(manifest)); tmp.replace(out/'current.json')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--out',type=Path,default=Path('data/out/evidence'))
    args=parser.parse_args(); print(json.dumps(build(args.root.resolve(),args.out),indent=2))

if __name__=='__main__': main()
