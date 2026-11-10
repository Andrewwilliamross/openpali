"""Evidence boundary tests: interpretation, identity, integrity and draft isolation."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from openpali.api.app import create_app
from openpali.api.routers import evidence
from openpali.api.routers.releases import parse_bbox
from openpali.intelligence.build import cleanup_stage, encoded, digest, spatial_features, property_row
from openpali.intelligence.repository import EvidenceRepository
from openpali.intelligence.workspace import ProjectClaim, Workspace
from openpali.intelligence.market import screen_transfer
from openpali.ml.experiments import _ipcw_brier


def test_document_and_private_participation_do_not_prove_completion():
    assert cleanup_stage({'ROE_STATUS':'Opt-Out and Manage Cleanup Independently','FSO_URL':'packet.pdf'})=='unknown'
    assert cleanup_stage({'DEBRIS_REMOVAL_EPICLA':'Finaled'})=='cleanup'
    assert cleanup_stage({'REBUILD_PROGRESS':'Construction Completed'})=='construction_complete'
    assert cleanup_stage({'REBUILD_PROGRESS':'Some new agency value'})=='unknown'


@pytest.mark.parametrize('bbox',['nan,0,1,1','0,0,inf,1','1,1,0,0','-181,0,-180,1','0,90,1,91','0,0,5,5','1,2,3'])
def test_invalid_map_bounds_rejected(bbox):
    with pytest.raises(Exception): parse_bbox(bbox)


def test_all_censored_is_not_perfect_prediction():
    assert _ipcw_brier([{'duration_days':10,'event_issued':0}],180,lambda _:0.5)==(None,0,0)


def test_transfer_nominal_price_invalid_date_and_trust_are_review_only():
    result=screen_transfer({'DTTSalePrice':'9','RecordingDate':'02/45/1967','DocumentTypeDesc':'Trust transfer'})
    assert result['date'] is None
    assert result['screening']=='review_required'
    assert {'invalid_recording_date','missing_or_nominal_price','not_identified_as_sale'} <= set(result['reasons'])


def test_spatial_features_exclude_self_and_never_call_destruction_vacancy():
    p=property_row('4412013017');q=property_row('4412013018');q['damage']='destroyed'
    for row,x in [(p,-118.53),(q,-118.5299)]:
        row['geometry']={'type':'Polygon','coordinates':[[[x,34.04],[x+.00005,34.04],[x+.00005,34.04005],[x,34.04005],[x,34.04]]]}
    spatial_features({p['apn']:p,q['apn']:q})
    assert p['neighborhood']['measures']['100']['parcel_count']==1
    assert p['neighborhood']['measures']['100']['destroyed_count']==1
    assert p['neighborhood']['vacancy_share'] is None


def fixture_release(tmp_path):
    rid='evidence-'+'a'*24; path=tmp_path/rid;path.mkdir()
    p=property_row('4412013017','677 VIA DE LA PAZ');p['tasks']=[dict(task_id='task1',kind='visual',apn=p['apn'],priority=1)]
    body=encoded(dict(release_id=rid,properties={p['apn']:p},coverage={},sources=[],unmatched_evidence=[]))
    (path/'release.json').write_bytes(body)
    manifest=dict(release_id=rid,counts={'properties':1},artifacts={'release.json':{'sha256':digest(body)}})
    (path/'manifest.json').write_bytes(encoded(manifest));(tmp_path/'current.json').write_bytes(encoded(manifest))
    return rid


def test_artifact_hash_and_path_integrity(tmp_path):
    rid=fixture_release(tmp_path);repo=EvidenceRepository(tmp_path)
    assert repo.release(rid)['release_id']==rid
    with pytest.raises(ValueError): repo.release('../../somewhere')
    (tmp_path/rid/'release.json').write_bytes(b'{}')
    with pytest.raises(ValueError): repo.artifact(rid,'release.json')


def test_claim_dates_reject_fabricated_scope():
    with pytest.raises(ValidationError):
        ProjectClaim(apn='4412013017',organization='Sample Co',role='framing',scope='Frame a new home',evidence_url='https://example.com',ended_at='2025-04-01')


def test_api_local_drafts_persist_without_changing_release(tmp_path,monkeypatch):
    rid=fixture_release(tmp_path);repo=EvidenceRepository(tmp_path);ops=Workspace(tmp_path/'workspace.sqlite')
    monkeypatch.setattr(evidence,'repository',lambda:repo);monkeypatch.setattr(evidence,'workspace',lambda:ops)
    client=TestClient(create_app());url=f'/v1/evidence/releases/{rid}/claims'
    claim=dict(apn='4412013017',organization='Test framing',role='framing',scope='Framing scope under review',evidence_url='https://example.com/evidence')
    assert client.post(url,json=claim).status_code==403
    monkeypatch.setenv('OPENPALI_LOCAL_WORKSPACE','1')
    headers={'X-OpenPali-Workspace':'local-draft','Origin':'https://attacker.example'}
    assert client.post(url,json=claim,headers=headers).status_code==403
    headers['Origin']='http://127.0.0.1:5173'
    response=client.post(url,json=claim,headers=headers)
    assert response.status_code==201
    assert response.json()['payload']['verification']=='unverified'
    assert len(Workspace(tmp_path/'workspace.sqlite').list('claim','4412013017'))==1
    assert repo.release(rid)['properties']['4412013017']['stage']=='unknown'
    r=client.get(f'/v1/evidence/releases/{rid}/artifacts/release.json');assert r.status_code==200
    assert client.get(f'/v1/evidence/releases/{rid}/artifacts/release.json',headers={'If-None-Match':r.headers['etag']}).status_code==304


def test_accessory_permits_and_impossible_dates_never_advance_house():
    from openpali.intelligence.permits import permit_stage
    row=dict(PERMIT_TYPE='Bldg-New',PALISADES_WF_REBUILD='Rebuild',ZONE_USE_DESC='Accessory Dwelling Unit',COFO_DATE=1785110400000)
    assert permit_stage(row,'2026-09-25T00:00:00+00:00')=='unknown'
    row['ZONE_USE_DESC']='Dwelling - Single Family'
    assert permit_stage(row,'2026-09-25T00:00:00+00:00')=='occupancy'
    row['COFO_DATE']=99999999999999
    assert permit_stage(row,'2026-09-25T00:00:00+00:00')=='unknown'


def test_map_artifacts_are_rounded_scored_and_indexed():
    from openpali.intelligence.build import map_artifacts, rounded
    burned=property_row('4412013017','677 VIA DE LA PAZ');burned.update(damage='destroyed',stage='permit',
        geometry=dict(type='Polygon',coordinates=[[[-118.5266123456789,34.0440123456789],[-118.5264,34.0440],[-118.5264,34.0442],[-118.5266,34.0442],[-118.5266123456789,34.0440123456789]]]))
    standing=property_row('4412013018','1 EXAMPLE ST');standing.update(geometry=dict(type='Polygon',
        coordinates=[[[-118.5270,34.0440],[-118.5268,34.0440],[-118.5268,34.0442],[-118.5270,34.0442],[-118.5270,34.0440]]]))
    unmapped=property_row('4412013019','2 EXAMPLE ST')
    out=map_artifacts({p['apn']:p for p in (burned,standing,unmapped)})
    features=json.loads(out['parcels.geojson'])['features']
    assert [f['id'] for f in features]==['4412013017','4412013018']  # no geometry, no feature
    assert features[0]['geometry']['coordinates'][0][0]==[-118.526612,34.044012]
    assert features[0]['properties']['score']==40 and 'weight' not in features[0]['properties']
    assert 'score' not in features[1]['properties']  # unassessed is not a score of zero
    index=json.loads(out['parcel-index.json'])
    rows={r[0]:dict(zip(index['fields'],r)) for r in index['rows']}
    assert rows['4412013019']['lon'] is None and rows['4412013019']['address']=='2 EXAMPLE ST'  # still searchable
    assert -118.5267<rows['4412013017']['lon']<-118.5263 and rows['4412013017']['score']==40
    assert rows['4412013018']['score'] is None
    # rounding never collapses a ring below four positions
    sliver=[[0.0000001,0.0],[0.0000002,0.0],[0.0000003,0.0000001],[0.0000001,0.0]]
    assert len(rounded([sliver])[0])==4
    assert rounded([[[1.0,2.0],[1.00000001,2.0],[1.5,2.0],[1.5,2.5],[1.0,2.0]]])[0]==[[1.0,2.0],[1.5,2.0],[1.5,2.5],[1.0,2.0]]


def test_artifact_route_serves_the_precompressed_sibling(tmp_path,monkeypatch):
    import gzip
    rid=fixture_release(tmp_path);path=tmp_path/rid
    body=encoded(dict(fields=['apn'],rows=[['4412013017']]*400));packed=gzip.compress(body,9,mtime=0)
    (path/'parcel-index.json').write_bytes(body);(path/'parcel-index.json.gz').write_bytes(packed)
    manifest=json.loads((path/'manifest.json').read_bytes())
    manifest['artifacts']['parcel-index.json']=dict(sha256=digest(body),bytes=len(body),gzip=dict(sha256=digest(packed),bytes=len(packed)))
    (path/'manifest.json').write_bytes(encoded(manifest))
    monkeypatch.setenv('OPENPALI_EVIDENCE_ROOT',str(tmp_path));evidence.repository.cache_clear()
    client=TestClient(create_app());url=f'/v1/evidence/releases/{rid}/artifacts/parcel-index.json'
    plain=client.get(url,headers={'Accept-Encoding':'identity'})
    assert plain.status_code==200 and plain.content==body and 'content-encoding' not in plain.headers
    zipped=client.get(url,headers={'Accept-Encoding':'gzip'})
    assert zipped.headers['content-encoding']=='gzip' and zipped.content==body  # client decodes
    assert zipped.headers['vary']=='Accept-Encoding' and 'immutable' in zipped.headers['cache-control']
    assert zipped.headers['etag']!=plain.headers['etag']  # one validator per representation
    assert client.get(url,headers={'Accept-Encoding':'gzip','If-None-Match':zipped.headers['etag']}).status_code==304
    # an artifact without a sibling (older releases) is served as is
    assert 'content-encoding' not in client.get(f'/v1/evidence/releases/{rid}/artifacts/release.json',headers={'Accept-Encoding':'gzip'}).headers
    assert client.get(f'/v1/evidence/releases/{rid}/artifacts/nope.json').status_code==404
    (path/'parcel-index.json.gz').write_bytes(b'tampered');evidence.repository.cache_clear()
    assert client.get(url,headers={'Accept-Encoding':'gzip'}).status_code==409
