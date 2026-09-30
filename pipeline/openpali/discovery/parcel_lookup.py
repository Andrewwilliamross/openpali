"""Resolve out-of-ZIP recovery parcel geometries by exact AIN, preserving gaps."""
import json
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import time
import httpx
from openpali.discovery.clearance import Archive, now
from openpali.discovery.parcel_universe import LAYER,FIELDS


def main():
    base=Path('Docs/Research/2026-09-24-')
    u=json.loads(Path(str(base)+'parcel-universe.json').read_text())
    geo=json.loads(Path(u['path']).read_text()); existing={f['properties']['AIN'] for f in geo['features']}
    c=json.loads(Path(str(base)+'clearance-inventory.json').read_text())
    ids={str(r['APN']).replace('-','') for r in map(json.loads,Path(c['index_path']).read_text().splitlines())}
    ids.add('4416020028')
    wanted=sorted(ids-existing)
    if len(wanted)>2000: raise ValueError('unexpected cohort growth')
    run=Path('data/raw/parcel-lookup')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with httpx.Client(timeout=60,follow_redirects=False) as client:
        archive=Archive(run,client); features=[]
        try:
            for start in range(0,len(wanted),100):
                batch=wanted[start:start+100]
                if any(len(a)!=10 or not a.isdigit() for a in batch): raise ValueError('bad AIN')
                where='AIN IN ('+','.join("'"+a+"'" for a in batch)+')'
                data=archive.json(LAYER+'/query',{'f':'geojson','where':where,'outFields':','.join(FIELDS),'returnGeometry':'true','outSR':4326},post=True)
                if data.get('exceededTransferLimit'): raise ValueError('truncated batch')
                rows=data['features']; returned=[f['properties']['AIN'] for f in rows]
                if len(returned)!=len(set(returned)) or not set(returned)<=set(batch): raise ValueError('ambiguous/substituted identifiers')
                features.extend(rows); time.sleep(0.5)
            path=run/'parcels.geojson'; body=json.dumps({'type':'FeatureCollection','features':features},separators=(',',':')).encode();path.write_bytes(body)
            report=dict(status='complete',source=LAYER,completed_at=now(),path=str(path),sha256=hashlib.sha256(body).hexdigest(),features=len(features),requested_ains=wanted,unresolved=sorted(set(wanted)-{f['properties']['AIN'] for f in features}),requests=archive.requests)
            Path(str(base)+'parcel-lookup.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:v for k,v in report.items() if k not in ('requests','requested_ains')}))
        finally:
            (run/'requests.json').write_text(json.dumps(archive.requests,indent=2)+'\n')
if __name__=='__main__': main()
