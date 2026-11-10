"""Portable release API; the production civic release pointer remains independent."""
import os
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request, Response
from openpali.intelligence.repository import EvidenceRepository
from openpali.api.problem import problem_response
from openpali.domain.lifecycles import ACQUISITION_TASK, IllegalTransition, catalog
from openpali.intelligence.workspace import ProjectClaim, TaskUpdate, Workspace

router=APIRouter(prefix='/v1/evidence',tags=['evidence workspace'])

@lru_cache
def repository():
    return EvidenceRepository(os.environ.get('OPENPALI_EVIDENCE_ROOT','data/out/evidence'))

@lru_cache
def workspace():
    return Workspace(os.environ.get('OPENPALI_WORKSPACE_PATH','data/out/workspace.sqlite'))


def load(release_id):
    try: return repository().release(release_id)
    except FileNotFoundError as exc: raise HTTPException(404,'evidence release not found; run evidence-build') from exc
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc


def prop(release_id,apn):
    data=load(release_id)
    if apn not in data['properties']: raise HTTPException(404,'parcel not in this release')
    return data['properties'][apn]


def writable(request):
    if os.environ.get('OPENPALI_LOCAL_WORKSPACE')!='1':
        raise HTTPException(403,'local draft workspace is disabled')
    # Local-only deployment; JSON/custom header also prevent cross-origin form posts.
    if request.headers.get('x-openpali-workspace')!='local-draft':
        raise HTTPException(403,'workspace header required')
    origin=request.headers.get('origin')
    allowed={'http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:8000'}
    if origin and origin not in allowed: raise HTTPException(403,'origin not allowed')


@router.get('/current')
def current(response:Response):
    try: manifest=repository().current()
    except FileNotFoundError as exc: raise HTTPException(503,'Run make evidence-build to create a release') from exc
    response.headers['Cache-Control']='no-cache'
    data=load(manifest['release_id'])
    return dict(**manifest,coverage=data['coverage'],sources=data['sources'],
                unmatched_evidence=data['unmatched_evidence'],permit_timing=data.get('permit_timing'),local_workspace=os.environ.get('OPENPALI_LOCAL_WORKSPACE')=='1')


@router.get('/releases/{release_id}/properties')
def properties(release_id:str,q:str=Query('',max_length=120),stage:str='',offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=500)):
    needle=q.strip().lower()
    rows=[p for p in load(release_id)['properties'].values() if
          (not needle or needle in p['address'].lower() or needle.replace('-','') in p['apn']) and (not stage or p['stage']==stage)]
    rows.sort(key=lambda p:p['apn'])
    return dict(release_id=release_id,total=len(rows),items=[{k:p[k] for k in ('apn','address','stage','damage','cohorts')} for p in rows[offset:offset+limit]])


@router.get('/releases/{release_id}/properties/{apn}')
def detail(release_id:str,apn:str):
    return dict(release_id=release_id,**prop(release_id,apn))


@router.get('/releases/{release_id}/tasks')
def tasks(release_id:str,kind:str='',limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
    rows=[dict(t,address=p['address']) for p in load(release_id)['properties'].values() for t in p['tasks'] if not kind or t['kind']==kind]
    rows.sort(key=lambda t:(-t['priority'],t['apn'],t['kind']))
    return dict(release_id=release_id,total=len(rows),items=rows[offset:offset+limit])


@router.get('/releases/{release_id}/artifacts/{name}')
def artifact(release_id:str,name:str,request:Request):
    accepts_gzip='gzip' in request.headers.get('accept-encoding','').lower()
    try: body,sha,encoding=repository().artifact(release_id,name,gzip=accepts_gzip)
    except FileNotFoundError as exc: raise HTTPException(404,'artifact not found') from exc
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    # The URL names an immutable release, so the bytes behind it never change.
    # Each encoding is its own representation with its own validator.
    headers={'ETag':f'"{sha}"','Cache-Control':'public, max-age=31536000, immutable','Vary':'Accept-Encoding'}
    if encoding: headers['Content-Encoding']=encoding
    if headers['ETag'] in [tag.strip() for tag in request.headers.get('if-none-match','').split(',')]:
        return Response(status_code=304,headers=headers)
    media='image/png' if name.endswith('.png') else 'application/geo+json' if name.endswith('.geojson') else 'application/json' if name.endswith('.json') else 'application/octet-stream'
    return Response(body,media_type=media,headers=headers)


@router.get('/releases/{release_id}/properties/{apn}/claims')
def claims(release_id:str,apn:str):
    prop(release_id,apn)
    if os.environ.get('OPENPALI_LOCAL_WORKSPACE')!='1': return dict(items=[],ranking=None)
    return dict(items=workspace().list('claim',apn),ranking=None,
                reason='Unverified claims do not establish work performed or comparable trade durations.')


@router.post('/releases/{release_id}/claims',status_code=201)
def claim(release_id:str,body:ProjectClaim,request:Request):
    writable(request); prop(release_id,body.apn)
    return workspace().append('claim',body.apn,release_id,dict(body.model_dump(mode='json'),verification='unverified',publication='local_draft'))


def require_task(release_id,task_id):
    if not any(t['task_id']==task_id for p in load(release_id)['properties'].values() for t in p['tasks']):
        raise HTTPException(404,'task not in release')


def workspace_enabled():
    return os.environ.get('OPENPALI_LOCAL_WORKSPACE')=='1'


@router.get('/lifecycles')
def lifecycles():
    """Every declared state machine: states, legal moves and terminal states."""
    return catalog()


@router.post('/releases/{release_id}/tasks/{task_id}',status_code=201,
             responses={200:{'description':'Task already in the requested state; no event appended'},
                        409:{'description':'Illegal transition; body lists current state and allowed_next'}})
def update_task(release_id:str,task_id:str,body:TaskUpdate,request:Request,response:Response):
    writable(request); require_task(release_id,task_id)
    ops=workspace(); current,history=ops.task_status(task_id)
    try: ACQUISITION_TASK.require(current,body.status)
    except IllegalTransition as exc:
        return problem_response(409,title=str(exc),type_='https://openpali.org/problems/illegal-transition',
                                lifecycle=exc.lifecycle,current=current,requested=body.status,allowed_next=exc.allowed)
    if body.status==current:
        # Idempotent retry (double click, second tab, agent retry): no duplicate event.
        response.status_code=200
        return history[-1]
    return ops.append('task',task_id,release_id,body.model_dump(mode='json'))


@router.get('/releases/{release_id}/tasks/{task_id}/history')
def task_history(release_id:str,task_id:str):
    require_task(release_id,task_id)
    if not workspace_enabled():
        return dict(items=[],status='open',allowed_next=[],writable=False)
    current,history=workspace().task_status(task_id)
    return dict(items=history,status=current,allowed_next=sorted(ACQUISITION_TASK.allowed(current)),writable=True)
