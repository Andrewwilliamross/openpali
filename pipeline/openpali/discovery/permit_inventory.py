"""Acquire complete current LADBS permit and scheduled-inspection tables by frozen IDs."""
import json
import hashlib
from pathlib import Path
from datetime import datetime,timezone
import httpx
from openpali.discovery.clearance import Archive,now
from openpali.adapters.registry import ladbs_permits_adapter,ladbs_inspections_adapter


def main():
    run=Path('data/raw/permit-inventory')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');reports=[]
    with httpx.Client(timeout=60,follow_redirects=False) as client:
        archive=Archive(run,client)
        try:
            for adapter in (ladbs_permits_adapter(),ladbs_inspections_adapter()):
                base=adapter.layer_url;meta=archive.json(base,{'f':'json'});response=archive.json(base+'/query',{'f':'json','where':'1=1','returnIdsOnly':'true'})
                ids=sorted(response['objectIds']);field=response['objectIdFieldName'];rows=[]
                if not ids or len(ids)>100000 or len(set(ids))!=len(ids):raise ValueError('invalid table size/identifiers')
                for start in range(0,len(ids),500):
                    batch=ids[start:start+500];data=archive.json(base+'/query',{'f':'json','objectIds':','.join(map(str,batch)),'outFields':'*','returnGeometry':'false'},post=True)
                    page=[f['attributes'] for f in data['features']]
                    if data.get('exceededTransferLimit') or len(page)!=len(batch) or {p[field] for p in page}!=set(batch):raise ValueError('incomplete permit batch')
                    rows.extend(page)
                path=run/(adapter.source_id+'.json');body=json.dumps(rows,sort_keys=True).encode();path.write_bytes(body)
                reports.append(dict(source_id=adapter.source_id,source=base,path=str(path),sha256=hashlib.sha256(body).hexdigest(),count=len(rows),fields=meta['fields'],observed_at=now()))
        finally:
            (run/'requests.json').write_text(json.dumps(archive.requests,indent=2)+'\n')
    report=dict(status='complete',completed_at=now(),tables=reports,requests=archive.requests)
    Path('Docs/Research/2026-09-24-permit-inventory.json').write_text(json.dumps(report,indent=2)+'\n')
    print([(r['source_id'],r['count']) for r in reports])
if __name__=='__main__':main()
