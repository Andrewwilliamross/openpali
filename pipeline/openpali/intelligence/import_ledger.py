"""Stage a verified portable release in the canonical PostGIS ledger.

Does not publish or move the production pointer. Requires migrations 0001/0002.
"""
import argparse
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from openpali.storage.models import Source, AcquisitionRun, RawObject, AcquisitionPage, ParcelVersion, PropertyIdentity
from openpali.storage.db import session_scope
from openpali.ingestion.load import _upsert_record_version, _ensure_property, _geometry_value, insert_observations
from openpali.ingestion.normalize import normalize_county_parcel, normalize_ladbs_permit
from openpali.intelligence.permits import primary_home
from openpali.domain.observations import SourceRecordRef
from openpali.ingestion.snapshot import build_snapshot
from openpali.intelligence.repository import EvidenceRepository
from openpali.intelligence.build import digest


def import_release(session, root, release_id):
    repo=EvidenceRepository(root); data=repo.release(release_id)
    body,sha=repo.artifact(release_id,'release.json')
    observed=max(datetime.fromisoformat(e['observed_at'].replace('Z','+00:00')) for p in data['properties'].values() for e in p['evidence'] if e.get('observed_at'))
    source_id='research_evidence'; run_id=release_id
    session.execute(insert(Source).values(source_id=source_id,title='Verified multi-source research evidence release',criticality='optional',terms_reference='Per-record original agency source links and rights; local staging only').on_conflict_do_nothing(index_elements=['source_id']))
    run=session.execute(select(AcquisitionRun).where(AcquisitionRun.run_id==run_id)).scalar_one_or_none()
    if run is None:
        run=AcquisitionRun(run_id=run_id,source_id=source_id,online=False,parameters={'release_id':release_id},requested_at=observed,retrieved_at=observed,status='succeeded',record_count=len(data['properties']),response_sha256=sha,health={'status':'ok','portable_release':release_id})
        session.add(run);session.flush()
        raw=session.execute(select(RawObject).where(RawObject.sha256==sha)).scalar_one_or_none()
        if raw is None:
            raw=RawObject(sha256=sha,object_uri=(Path(root)/release_id/'release.json').resolve().as_uri(),media_type='application/json',byte_size=len(body),first_seen_at=observed,classification='local-research')
            session.add(raw);session.flush()
        session.add(AcquisitionPage(acquisition_run_id=run.id,page_index=0,raw_object_id=raw.id))
    for apn,p in data['properties'].items():
        version,_=_upsert_record_version(session,source_id=source_id,native_key=apn,payload=p,run_row=run,observed_at=observed)
        property_id=_ensure_property(session,apn)
        identity=session.execute(select(PropertyIdentity).where(PropertyIdentity.property_id==property_id)).scalar_one()
        prior=session.execute(select(ParcelVersion).where(ParcelVersion.apn==apn,ParcelVersion.record_version_id==version)).scalar_one_or_none()
        if prior is None:
            from shapely.geometry import shape
            center=shape(p['geometry']).representative_point() if p['geometry'] else None
            session.add(ParcelVersion(property_identity_id=identity.id,apn=apn,situs_address=p['address'],
                damage_class='Destroyed (>50%)' if p['damage']=='destroyed' else None,
                pre_fire={},center_lon=center.x if center else None,center_lat=center.y if center else None,
                geometry=_geometry_value({'_geometry':p['geometry']}),record_version_id=version,observed_from=observed))
        if p['cleanup']:
            result=normalize_county_parcel(p['cleanup'],observed_at=observed,source_record=SourceRecordRef(source_id,apn,digest(body)))
            insert_observations(session,result.observations,record_version=version)
        for permit in p.get('permit_records', []):
            if primary_home(permit):
                result=normalize_ladbs_permit(permit,observed_at=observed,
                    source_record=SourceRecordRef(source_id,permit['PERMIT'],sha))
                insert_observations(session,result.observations,record_version=version)
    session.flush()
    return build_snapshot(session,[run_id],observed)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path('data/out/evidence'));parser.add_argument('--release')
    args=parser.parse_args();release=args.release or EvidenceRepository(args.root).current()['release_id']
    with session_scope() as session:
        result=import_release(session,args.root,release);print(result)
if __name__=='__main__':main()
