"""Release-qualified public routes.

A client resolves ``/v1/releases/current`` once, pins that release, and uses
only release-qualified URLs afterwards. Cursors embed the release ID and fail
on cross-release reuse. Immutable release representations carry strong ETags
and long cache lifetimes.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from openpali.storage.db import get_session_factory
from openpali.storage.models import (
    CurrentRelease,
    ObservationRevision,
    ParcelVersion,
    PropertyIdentity,
    Publication,
    RecoveryObservationRow,
    SnapshotMember,
    SnapshotPropertyState,
)

from ..schemas import (
    ObservationModel,
    ObservationPage,
    OccurrenceModel,
    PropertyDetail,
    PropertyPage,
    PropertySummary,
    ReleaseInfo,
    SourceHealthModel,
    SourcesResponse,
)

router = APIRouter(prefix="/v1", tags=["releases"])

MAX_PAGE = 100
IMMUTABLE_CACHE = "public, max-age=86400, immutable"
CURRENT_CACHE = "public, max-age=15, stale-while-revalidate=120"


def get_session() -> Session:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _etag(*parts: str) -> str:
    return '"' + hashlib.sha256("|".join(parts).encode()).hexdigest()[:24] + '"'


class NotModified(Exception):
    """Raised to short-circuit into a proper bodyless 304."""

    def __init__(self, etag: str, cache: str) -> None:
        self.etag = etag
        self.cache = cache


def _maybe_304(request: Request, response: Response, etag: str, cache: str) -> None:
    """Stamp caching headers; raise NotModified when the client's ETag matches."""

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache
    if request.headers.get("if-none-match") == etag:
        raise NotModified(etag, cache)


def _release_info(session: Session, publication: Publication, lkg: str | None) -> ReleaseInfo:
    manifest = publication.manifest or {}
    return ReleaseInfo(
        release_id=publication.release_id,
        snapshot_id=publication.snapshot_id,
        kind=publication.kind,
        status=publication.status,
        published_at=publication.promoted_at,
        manifest_sha256=publication.manifest_sha256,
        schema_versions=manifest.get("schema_versions", {}),
        policy_versions=manifest.get("policy_versions", {}),
        coverage=manifest.get("coverage", {}),
        limitations=manifest.get("limitations", []),
        lkg_release_id=lkg,
    )


def _current_row(session: Session) -> CurrentRelease | None:
    return session.get(CurrentRelease, 1)


@router.get("/releases/current", response_model=ReleaseInfo)
def resolve_current(
    request: Request, response: Response, session: Session = Depends(get_session)
) -> ReleaseInfo:
    row = _current_row(session)
    release_id = (row.current_release_id or row.lkg_release_id) if row else None
    if not release_id:
        raise HTTPException(503, "no published release is available yet")
    publication = session.execute(
        select(Publication).where(Publication.release_id == release_id)
    ).scalar_one()
    response.headers["Cache-Control"] = CURRENT_CACHE
    return _release_info(session, publication, row.lkg_release_id if row else None)


def get_release(
    release_id: str, session: Session = Depends(get_session)
) -> Publication:
    publication = session.execute(
        select(Publication).where(Publication.release_id == release_id)
    ).scalar_one_or_none()
    if publication is None or publication.status not in {"published", "lkg", "superseded"}:
        raise HTTPException(404, f"unknown or unpublished release: {release_id}")
    return publication


@router.get("/releases/{release_id}", response_model=ReleaseInfo)
def release_info(
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
) -> ReleaseInfo:
    etag = _etag(publication.release_id, "info", publication.manifest_sha256)
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    row = _current_row(session)
    return _release_info(session, publication, row.lkg_release_id if row else None)


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------


def _encode_cursor(release_id: str, last_apn: str) -> str:
    raw = json.dumps({"r": release_id, "a": last_apn}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str, release_id: str) -> str:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "malformed cursor") from exc
    if payload.get("r") != release_id:
        raise HTTPException(400, "cursor was issued for a different release")
    return str(payload.get("a") or "")


def _summary(state: SnapshotPropertyState, property_id: str) -> PropertySummary:
    return PropertySummary(
        property_id=property_id,
        apn=state.apn,
        address=state.address,
        neighborhood=state.neighborhood,
        jurisdiction=state.jurisdiction,
        lane_signals=state.lane_signals,
        milestones=state.milestones,
        last_evidence_date=state.last_evidence_date,
        conflict_count=state.conflict_count,
    )


@router.get("/releases/{release_id}/properties", response_model=PropertyPage)
def search_properties(
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
    q: str | None = Query(default=None, max_length=120, description="address or APN fragment"),
    bbox: str | None = Query(default=None, description="minLon,minLat,maxLon,maxLat"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=MAX_PAGE),
) -> PropertyPage:
    etag = _etag(publication.release_id, "props", q or "", bbox or "", cursor or "", str(limit))
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)

    query = (
        select(SnapshotPropertyState)
        .where(SnapshotPropertyState.snapshot_id == publication.snapshot_id)
        .order_by(SnapshotPropertyState.apn)
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(SnapshotPropertyState.apn > _decode_cursor(cursor, publication.release_id))
    if q:
        needle = q.strip()
        digits = "".join(c for c in needle if c.isdigit())
        if digits and len(digits) >= 4 and digits == needle.replace("-", "").replace(" ", ""):
            query = query.where(SnapshotPropertyState.apn.like(f"{digits}%"))
        else:
            query = query.where(SnapshotPropertyState.address.ilike(f"%{needle}%"))
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(x) for x in bbox.split(","))
        except ValueError as exc:
            raise HTTPException(400, "bbox must be minLon,minLat,maxLon,maxLat") from exc
        if (max_lon - min_lon) * (max_lat - min_lat) > 1.0:
            raise HTTPException(400, "bbox too large; maximum area is 1 square degree")
        apns_in_bbox = select(ParcelVersion.apn).where(
            func.ST_Intersects(
                ParcelVersion.geometry,
                func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326),
            )
        )
        query = query.where(SnapshotPropertyState.apn.in_(apns_in_bbox))

    states = list(session.execute(query).scalars())
    has_more = len(states) > limit
    states = states[:limit]
    items = [_summary(s, s.property_id) for s in states]
    next_cursor = (
        _encode_cursor(publication.release_id, states[-1].apn) if has_more and states else None
    )
    return PropertyPage(
        release_id=publication.release_id, items=items, next_cursor=next_cursor
    )


def _state_for_property(
    session: Session, publication: Publication, property_id: str
) -> SnapshotPropertyState:
    state = session.execute(
        select(SnapshotPropertyState).where(
            SnapshotPropertyState.snapshot_id == publication.snapshot_id,
            SnapshotPropertyState.property_id == property_id,
        )
    ).scalar_one_or_none()
    if state is None:
        raise HTTPException(404, f"property not in release {publication.release_id}: {property_id}")
    return state


@router.get("/releases/{release_id}/properties/{property_id}", response_model=PropertyDetail)
def property_detail(
    property_id: str,
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
) -> PropertyDetail:
    etag = _etag(publication.release_id, "prop", property_id)
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    state = _state_for_property(session, publication, property_id)
    identity = session.execute(
        select(PropertyIdentity).where(PropertyIdentity.property_id == property_id)
    ).scalar_one_or_none()
    parcel = session.execute(
        select(ParcelVersion)
        .where(ParcelVersion.apn == state.apn, ParcelVersion.observed_to.is_(None))
        .order_by(ParcelVersion.observed_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    return PropertyDetail(
        property_id=property_id,
        apn=state.apn,
        address=state.address,
        neighborhood=state.neighborhood,
        jurisdiction=state.jurisdiction,
        identity={
            "seed_policy_version": identity.seed_policy_version if identity else None,
            "confidence": identity.confidence if identity else None,
            "state": identity.state if identity else None,
        },
        pre_fire=(parcel.pre_fire if parcel else {}),
        lane_signals=state.lane_signals,
        milestones=state.milestones,
        projection_policy_version=state.projection_policy_version,
        observation_count=state.observation_count,
        conflict_count=state.conflict_count,
        last_evidence_date=state.last_evidence_date,
        center=(
            [parcel.center_lon, parcel.center_lat]
            if parcel and parcel.center_lon is not None and parcel.center_lat is not None
            else None
        ),
        release_id=publication.release_id,
        snapshot_id=publication.snapshot_id,
    )


def _occurrence_model(row: RecoveryObservationRow) -> OccurrenceModel:
    return OccurrenceModel(
        kind=row.occurred_kind,
        date=row.occurred_earliest if row.occurred_kind == "exact" else None,
        earliest=row.occurred_earliest if row.occurred_kind == "interval" else None,
        latest=row.occurred_latest if row.occurred_kind == "interval" else None,
    )


@router.get(
    "/releases/{release_id}/properties/{property_id}/observations",
    response_model=ObservationPage,
)
def property_observations(
    property_id: str,
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE),
) -> ObservationPage:
    etag = _etag(publication.release_id, "obs", property_id, cursor or "", str(limit))
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    state = _state_for_property(session, publication, property_id)

    related = [{"type": "parcel", "id": state.apn}]
    # Visibility: snapshot membership (point-in-time correct by construction).
    member_ids = select(SnapshotMember.member_id).where(
        SnapshotMember.snapshot_id == publication.snapshot_id,
        SnapshotMember.member_type == "observation",
    )
    query = (
        select(RecoveryObservationRow)
        .where(
            RecoveryObservationRow.observation_id.in_(member_ids),
            (
                (RecoveryObservationRow.subject_type == "parcel")
                & (RecoveryObservationRow.subject_id == state.apn)
            )
            | RecoveryObservationRow.related_subjects.contains(related),
        )
        .order_by(RecoveryObservationRow.observation_id)
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(
            RecoveryObservationRow.observation_id > _decode_cursor(cursor, publication.release_id)
        )
    rows = list(session.execute(query).scalars())
    has_more = len(rows) > limit
    rows = rows[:limit]

    retractions = {
        r.target_observation_id: r
        for r in session.execute(
            select(ObservationRevision).where(
                ObservationRevision.target_observation_id.in_(
                    [row.observation_id for row in rows] or [""]
                )
            )
        ).scalars()
    }
    items = [
        ObservationModel(
            observation_id=row.observation_id,
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            lane=row.lane,
            event_type=row.event_type,
            status=row.status,
            occurred=_occurrence_model(row),
            observed_at=row.observed_at,
            source_id=row.source_id,
            record_version_id=row.record_version_id,
            policy_version=row.policy_version,
            label=row.label,
            related_subjects=row.related_subjects,
            detail=row.detail,
            retracted=row.observation_id in retractions,
            retraction_reason=(
                retractions[row.observation_id].reason
                if row.observation_id in retractions
                else None
            ),
        )
        for row in rows
    ]
    next_cursor = (
        _encode_cursor(publication.release_id, rows[-1].observation_id)
        if has_more and rows
        else None
    )
    return ObservationPage(
        release_id=publication.release_id,
        property_id=property_id,
        items=items,
        next_cursor=next_cursor,
    )


# ---------------------------------------------------------------------------
# sources (frozen in the release manifest)
# ---------------------------------------------------------------------------


@router.get("/releases/{release_id}/sources", response_model=SourcesResponse)
def release_sources(
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
) -> SourcesResponse:
    etag = _etag(publication.release_id, "sources", publication.manifest_sha256)
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    manifest = publication.manifest or {}
    sources = [SourceHealthModel(**s) for s in manifest.get("sources", [])]
    return SourcesResponse(
        release_id=publication.release_id,
        snapshot_id=publication.snapshot_id,
        sources=sources,
    )


# ---------------------------------------------------------------------------
# vector tiles
# ---------------------------------------------------------------------------

MVT_QUERY = text(
    """
    WITH bounds AS (
        SELECT ST_TileEnvelope(:z, :x, :y) AS geom
    ),
    mvtgeom AS (
        SELECT
            ST_AsMVTGeom(
                ST_Transform(pv.geometry, 3857), bounds.geom, 4096, 64, true
            ) AS geom,
            sps.property_id,
            sps.apn,
            sps.jurisdiction,
            (sps.milestones ->> 'cleanup_complete')::boolean AS cleanup_complete,
            (sps.milestones ->> 'application_submitted')::boolean AS application_submitted,
            (sps.milestones ->> 'plan_check_approved')::boolean AS plan_check_approved,
            (sps.milestones ->> 'permit_issued')::boolean AS permit_issued,
            (sps.milestones ->> 'construction_evidence')::boolean AS construction_evidence,
            (sps.milestones ->> 'cofo_issued')::boolean AS cofo_issued,
            sps.lane_signals ->> 'lane_permit' AS lane_permit,
            sps.conflict_count
        FROM civic.snapshot_property_state sps
        JOIN LATERAL (
            SELECT geometry FROM civic.parcel_version pv
            WHERE pv.apn = sps.apn AND pv.observed_to IS NULL
            ORDER BY pv.observed_from DESC LIMIT 1
        ) pv ON true
        CROSS JOIN bounds
        WHERE sps.snapshot_id = :snapshot_id
          AND ST_Transform(pv.geometry, 3857) && bounds.geom
    )
    SELECT ST_AsMVT(mvtgeom.*, 'parcels', 4096, 'geom') FROM mvtgeom
    """
)


@router.get("/releases/{release_id}/tiles/parcels/{z}/{x}/{y}.mvt")
def parcel_tile(
    z: int,
    x: int,
    y: int,
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
) -> Response:
    if not (0 <= z <= 22):
        raise HTTPException(400, "zoom out of range")
    if z < 10:
        raise HTTPException(400, "parcel tiles are served at z>=10")
    etag = _etag(publication.release_id, "mvt", str(z), str(x), str(y))
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    row = session.execute(
        MVT_QUERY, {"z": z, "x": x, "y": y, "snapshot_id": publication.snapshot_id}
    ).scalar()
    payload = bytes(row) if row is not None else b""
    return Response(
        content=payload,
        media_type="application/vnd.mapbox-vector-tile",
        headers={"ETag": etag, "Cache-Control": IMMUTABLE_CACHE},
    )
