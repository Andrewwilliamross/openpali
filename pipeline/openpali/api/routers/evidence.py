"""Portable release API; the production civic release pointer remains independent."""
import os
from functools import lru_cache
from fastapi import APIRouter, HTTPException, Request, Response
from openpali.intelligence.repository import EvidenceRepository

router=APIRouter(prefix='/v1/evidence',tags=['evidence'])

@lru_cache
def repository():
    return EvidenceRepository(os.environ.get('OPENPALI_EVIDENCE_ROOT','data/out/evidence'))


def load(release_id):
    try: return repository().release(release_id)
    except FileNotFoundError as exc: raise HTTPException(404,'evidence release not found; run evidence-build') from exc
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc


@router.get('/current')
def current(response:Response):
    try: manifest=repository().current()
    except FileNotFoundError as exc: raise HTTPException(503,'Run make evidence-build to create a release') from exc
    response.headers['Cache-Control']='no-cache'
    data=load(manifest['release_id'])
    return dict(**manifest,coverage=data['coverage'],sources=data['sources'],
                unmatched_evidence=data['unmatched_evidence'],permit_timing=data.get('permit_timing'))


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
