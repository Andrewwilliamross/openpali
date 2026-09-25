"""Acquire a bounded assessor-history batch from the evidence work queue.

Deterministic stratified samples preserve selection details. Explicit access
blocks stop the host, partial records remain recorded, and completed manifests
can be added to the build recipe without rerunning other sources.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import httpx
from openpali.discovery.assessor import collect,BASE
from openpali.discovery.clearance import Archive,now
from openpali.intelligence.repository import EvidenceRepository
from openpali.intelligence.workspace import Workspace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--queued-only',action='store_true')
    parser.add_argument('--register',action='store_true',help='Add the completed acquisition manifest to the local build recipe')
    args=parser.parse_args()
    if not 1<=args.limit<=25: parser.error('limit must be 1–25')
    repo=EvidenceRepository('data/out/evidence');rid=repo.current()['release_id'];data=repo.release(rid)
    ops=Workspace('data/out/workspace.sqlite');groups={'destroyed':[],'unknown':[]}
    for p in data['properties'].values():
        if p['assessor']: continue
        task=next((t for t in p['tasks'] if t['kind']=='property_history'),None)
        if args.queued_only and (not task or not ops.list('task',task['task_id'])): continue
        groups[p['damage']].append(p['apn'])
    selected=[]
    for rows in groups.values(): rows.sort(key=lambda a:hashlib.sha256((rid+a).encode()).hexdigest())
    while any(groups.values()) and len(selected)<args.limit:
        for key in sorted(groups):
            if groups[key] and len(selected)<args.limit: selected.append(groups[key].pop(0))
    if not selected: print('No eligible history tasks');return
    run=Path('data/raw/assessor')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report=dict(source=BASE,started_at=now(),scope='deterministic balanced damage/unknown sample of missing histories' if not args.queued_only else 'queued history tasks',input_release=rid,requested_ains=selected,parcels=[],status='in_progress',run_path=str(run))
    with httpx.Client(timeout=45,follow_redirects=False,headers={'User-Agent':'OpenPali public property-history acquisition'}) as client:
        archive=Archive(run,client)
        try:
            for ain in selected:
                record=collect(archive,ain,0.6);body=json.dumps(record,sort_keys=True,indent=2).encode();path=run/f'{ain}.json';path.write_bytes(body)
                report['parcels'].append(dict(ain=ain,path=str(path),sha256=hashlib.sha256(body).hexdigest(),status=record['status'],failures=record['failures'],profile=record['profile']))
                print(ain,record['status'],flush=True)
                if any(r['status'] in (401,403,429) for r in archive.requests):break
        finally:
            report.update(completed_at=now(),requests=archive.requests)
            report['status']='complete' if len(report['parcels'])==len(selected) and all(p['status']=='complete' for p in report['parcels']) else 'partial'
            manifest=run/'report.json';manifest.write_text(json.dumps(report,indent=2)+'\n')
    if args.register:
        recipe=Path('Docs/Research/evidence-extra-inputs.json')
        entries=json.loads(recipe.read_text()) if recipe.exists() else []
        entries.append(str(manifest));recipe.write_text(json.dumps(sorted(set(entries)),indent=2)+'\n')
    print(json.dumps({'manifest':str(manifest),'status':report['status'],'parcels':len(report['parcels'])}))
if __name__=='__main__':main()
