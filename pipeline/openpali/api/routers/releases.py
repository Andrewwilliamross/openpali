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
    # the public map addresses parcels by 10-digit APN; accept both
    if property_id.isdigit() and len(property_id) == 10:
        from openpali.identity.ids import property_id_from_apn

        property_id = property_id_from_apn(property_id)
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
        select(PropertyIdentity).where(PropertyIdentity.property_id == state.property_id)
    ).scalar_one_or_none()
    parcel = session.execute(
        select(ParcelVersion)
        .where(ParcelVersion.apn == state.apn, ParcelVersion.observed_to.is_(None))
        .order_by(ParcelVersion.observed_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    return PropertyDetail(
        property_id=state.property_id,
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


# ---------------------------------------------------------------------------
# forecast (stored batch predictions or typed insufficiency; ML-003)
# ---------------------------------------------------------------------------


@router.get("/releases/{release_id}/properties/{property_id}/forecast")
def property_forecast(
    property_id: str,
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
) -> dict:
    from openpali.storage.models import (
        CaseLink,
        ModelVersion,
        Prediction,
        PredictionSet,
    )

    etag = _etag(publication.release_id, "forecast", property_id)
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    state = _state_for_property(session, publication, property_id)

    # Eligibility comes from THIS RELEASE'S OBSERVATIONS: an application with
    # a rebuild_application_submitted observation in the snapshot related to
    # this parcel. CaseLink qualification refines (disqualifies) when the
    # civic loader recorded it, but its absence (e.g. the fixture ledger)
    # must never hide an eligible application from the forecast surface.
    member_ids = select(SnapshotMember.member_id).where(
        SnapshotMember.snapshot_id == publication.snapshot_id,
        SnapshotMember.member_type == "observation",
    )
    submitted_rows = list(
        session.execute(
            select(RecoveryObservationRow).where(
                RecoveryObservationRow.observation_id.in_(member_ids),
                RecoveryObservationRow.subject_type == "permit_application",
                RecoveryObservationRow.event_type == "rebuild_application_submitted",
                RecoveryObservationRow.related_subjects.contains(
                    [{"type": "parcel", "id": state.apn}]
                ),
            )
        ).scalars()
    )
    observed_apps = sorted({row.subject_id for row in submitted_rows})

    links = list(
        session.execute(
            select(CaseLink).where(
                CaseLink.object_type == "property",
                CaseLink.object_id == state.property_id,
                CaseLink.link_type == "permit_on_property",
            )
        ).scalars()
    )
    disqualified = {
        link.subject_id for link in links
        if (link.detail or {}).get("qualification")
        in {"not_fire_rebuild", "undocumented"}
    }
    qualifying = [app for app in observed_apps if app not in disqualified]

    prediction_sets = list(
        session.execute(
            select(PredictionSet).where(
                PredictionSet.snapshot_id == publication.snapshot_id
            ).order_by(PredictionSet.created_at.desc())
        ).scalars()
    )
    base = {
        "release_id": publication.release_id,
        "snapshot_id": publication.snapshot_id,
        "property_id": state.property_id,
        "qualifying_applications": qualifying,
        "disclaimer": (
            "Any estimate is computed at application submission time from a "
            "versioned batch run — it is never a current ETA and never a "
            "judgment of resident effort."
        ),
    }
    if not qualifying:
        return {
            **base,
            "status": "not_applicable",
            "reason": "no qualifying rebuild application is on record for this property",
        }
    if not prediction_sets:
        return {
            **base,
            "status": "insufficient_evidence",
            "reason": "no prediction set exists for this release's snapshot",
        }
    active_set = prediction_sets[0]
    if active_set.status == "insufficient" or active_set.model_id is None:
        return {
            **base,
            "status": "insufficient_evidence",
            "reason": active_set.insufficiency_reason,
            "prediction_set_id": active_set.prediction_set_id,
            "note": (
                "The learning system ran and declined to fit a challenger: the "
                "ledger cannot yet demonstrate point-in-time feature history. "
                "Descriptive censoring-aware cohort estimates remain available "
                "under /metrics/bottlenecks."
            ),
        }

    model = session.execute(
        select(ModelVersion).where(ModelVersion.model_id == active_set.model_id)
    ).scalar_one_or_none()
    applications = []
    for permit_no in qualifying:
        prediction = session.execute(
            select(Prediction).where(
                Prediction.prediction_set_id == active_set.prediction_set_id,
                Prediction.subject_type == "permit_application",
                Prediction.subject_id == permit_no,
            )
        ).scalar_one_or_none()
        if prediction is not None:
            applications.append(
                {
                    "application_id": permit_no,
                    "status": "predicted",
                    "target": prediction.target,
                    "horizon_days": prediction.horizon_days,
                    "estimate": prediction.estimate,
                    "basis": prediction.basis,
                    "generated_at": prediction.generated_at.isoformat(),
                }
            )
        else:
            applications.append(
                {
                    "application_id": permit_no,
                    "status": "outcome_or_beyond_horizon",
                    "note": (
                        "the application's 180-day horizon has resolved or "
                        "elapsed; see the observations timeline for the "
                        "observed outcome"
                    ),
                }
            )
    return {
        **base,
        "status": "available",
        "prediction_set_id": active_set.prediction_set_id,
        "model": {
            "model_id": model.model_id if model else active_set.model_id,
            "target": model.target if model else None,
            "training_cutoff": model.training_cutoff.isoformat() if model else None,
            "limitations": model.limitations if model else None,
        },
        "applications": applications,
    }


# ---------------------------------------------------------------------------
# spatial assets (release-selected versions; tiles streamed from the object
# store with immutable caching; SPATIAL-001)
# ---------------------------------------------------------------------------


@router.get("/releases/{release_id}/spatial/assets")
def spatial_assets(
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
) -> dict:
    etag = _etag(publication.release_id, "spatial", publication.manifest_sha256)
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    spatial = (publication.manifest or {}).get("spatial", {})
    return {
        "release_id": publication.release_id,
        "selection_policy": spatial.get("selection_policy"),
        "assets": spatial.get("assets", []),
        "excluded": spatial.get("excluded", []),
    }


def _release_asset(publication: Publication, asset_id: str, version_id: str) -> dict:
    for asset in (publication.manifest or {}).get("spatial", {}).get("assets", []):
        if asset["asset_id"] == asset_id and asset["version_id"] == version_id:
            return asset
    raise HTTPException(
        404,
        f"asset {asset_id}@{version_id} is not selected by release "
        f"{publication.release_id}; stale or foreign asset versions are not served",
    )


@router.get("/releases/{release_id}/spatial/{asset_id}/{version_id}/{path:path}")
def spatial_asset_file(
    asset_id: str,
    version_id: str,
    path: str,
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
) -> Response:
    from openpali.storage.objects import ObjectStore, SPATIAL_BUCKET

    _release_asset(publication, asset_id, version_id)
    if ".." in path or path.startswith("/") or not path:
        raise HTTPException(400, "invalid asset path")
    etag = _etag(publication.release_id, "spatial-file", asset_id, version_id, path)
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    store = ObjectStore()
    key = f"assets/{asset_id}/{version_id}/{path}"
    if not store.exists(SPATIAL_BUCKET, key):
        raise HTTPException(404, f"no such asset object: {path}")
    body = store.client.get_object(Bucket=SPATIAL_BUCKET, Key=key)["Body"].read()
    media = (
        "image/png" if path.endswith(".png")
        else "application/json" if path.endswith(".json")
        else "application/octet-stream"
    )
    return Response(
        content=body,
        media_type=media,
        headers={"ETag": etag, "Cache-Control": IMMUTABLE_CACHE},
    )


# ---------------------------------------------------------------------------
# corrections (FRONTEND-001): rate-limited public submission; contact stored
# separately under restricted retention; moderation is human, append-only
# ---------------------------------------------------------------------------

from collections import deque as _deque
from time import monotonic as _monotonic

from pydantic import BaseModel, Field

_CORRECTION_WINDOW_S = 3600
_CORRECTION_MAX_PER_WINDOW = 5
_correction_buckets: dict[str, _deque] = {}


class CorrectionIn(BaseModel):
    claim_ref: str = Field(min_length=1, max_length=200,
                           description="which shown claim is wrong (e.g. lane/event id)")
    message: str = Field(min_length=10, max_length=4000)
    contact: str | None = Field(default=None, max_length=200,
                                description="optional; stored separately, never published")


@router.post("/releases/{release_id}/properties/{property_id}/corrections", status_code=202)
def submit_correction(
    property_id: str,
    body: CorrectionIn,
    request: Request,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
) -> dict:
    # the public map identifies parcels by APN; accept it and resolve
    if property_id.isdigit() and len(property_id) == 10:
        from openpali.identity.ids import property_id_from_apn

        property_id = property_id_from_apn(property_id)
    _state_for_property(session, publication, property_id)  # 404 unknown property

    # per-client sliding window (single-process deployment; a shared limiter
    # belongs to the reverse proxy in multi-instance setups)
    client = request.client.host if request.client else "unknown"
    now = _monotonic()
    bucket = _correction_buckets.setdefault(client, _deque())
    while bucket and now - bucket[0] > _CORRECTION_WINDOW_S:
        bucket.popleft()
    if len(bucket) >= _CORRECTION_MAX_PER_WINDOW:
        raise HTTPException(429, "correction rate limit reached; please try again later")
    bucket.append(now)

    from openpali.storage.models import CorrectionContact, CorrectionSubmission

    idempotency = hashlib.sha256(
        f"{publication.release_id}:{property_id}:{body.claim_ref}:{body.message}".encode()
    ).hexdigest()
    existing = session.execute(
        select(CorrectionSubmission).where(
            CorrectionSubmission.idempotency_key == idempotency
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"submission_id": existing.submission_id, "state": existing.moderation_state,
                "note": "already received"}

    submission_id = "corr-" + idempotency[:20]
    session.add(
        CorrectionSubmission(
            submission_id=submission_id,
            release_id=publication.release_id,
            property_id=property_id,
            claim_ref=body.claim_ref,
            message=body.message,
            idempotency_key=idempotency,
        )
    )
    # the contact FK targets a non-PK unique column, which the ORM's insert
    # ordering does not treat as a dependency — flush the parent first
    session.flush()
    if body.contact:
        session.add(CorrectionContact(submission_id=submission_id, contact=body.contact))
    session.commit()
    return {
        "submission_id": submission_id,
        "state": "pending",
        "note": (
            "Thank you. A human reviews every correction; accepted corrections "
            "become append-only revisions with the original preserved."
        ),
    }


@router.get("/releases")
def list_releases(
    response: Response,
    session: Session = Depends(get_session),
    kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Recent publications (all kinds/states) — operational visibility for
    /status and the evaluator; current authority remains /releases/current."""

    query = select(Publication).order_by(Publication.created_at.desc()).limit(limit)
    if kind:
        query = query.where(Publication.kind == kind)
    rows = list(session.execute(query).scalars())
    response.headers["Cache-Control"] = CURRENT_CACHE
    return {
        "releases": [
            {
                "release_id": p.release_id,
                "snapshot_id": p.snapshot_id,
                "kind": p.kind,
                "status": p.status,
                "promoted_at": p.promoted_at.isoformat() if p.promoted_at else None,
                "manifest_sha256": p.manifest_sha256,
            }
            for p in rows
        ]
    }
