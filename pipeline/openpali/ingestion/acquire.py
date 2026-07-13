"""Acquisition service: adapter -> immutable raw objects + run ledger.

Every acquisition (online or offline replay) records source/layer, parameters,
upstream edit time, retrieval time, page/row counts, combined response hash,
schema fingerprint, terms reference, code version, and typed health/failure.
Identical bytes deduplicate at content-addressed keys without erasing
acquisition history: every run gets its own run/page rows (DATA-001).
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from openpali.adapters.arcgis_source import ArcGISLayerAdapter, _raw_key_for, utcnow
from openpali.adapters.base import AcquisitionError, AcquisitionRequest, RawAcquisition
from openpali.identity.ids import acquisition_run_id
from openpali.storage.models import (
    AcquisitionPage,
    AcquisitionRun,
    RawObject,
    Source,
)
from openpali.storage.objects import ObjectStore, RAW_BUCKET


def _code_version() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).resolve().parents[2],
        ).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 - version stamp must never break acquisition
        return "unknown"


@dataclass(slots=True)
class AcquisitionResult:
    run_id: str
    status: str
    record_count: int
    page_hashes: list[tuple[str, int]]
    raw: RawAcquisition | None
    error: str | None = None


def ensure_source(session: Session, adapter: ArcGISLayerAdapter, criticality: str = "required") -> None:
    existing = session.execute(
        select(Source).where(Source.source_id == adapter.source_id)
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            Source(
                source_id=adapter.source_id,
                title=adapter.title,
                jurisdiction=adapter.jurisdiction,
                authority="public agency ArcGIS service",
                url_template=adapter.layer_url,
                terms_reference=adapter.terms_reference,
                expected_cadence="daily",
                owner="openpali",
                criticality=criticality,
            )
        )
        session.flush()


def run_acquisition(
    session: Session,
    store: ObjectStore,
    adapter: ArcGISLayerAdapter,
    request: AcquisitionRequest,
    *,
    requested_at: datetime | None = None,
) -> AcquisitionResult:
    """Execute one acquisition and persist its complete evidence trail.

    ``requested_at`` doubles as the idempotency component of the run ID: a
    retried/restarted flow passing the same timestamp converges on the same
    run row instead of duplicating it.
    """

    ensure_source(session, adapter)
    requested_at = requested_at or utcnow()
    run_id = acquisition_run_id(
        adapter.source_id, dict(request.parameters), requested_at.isoformat()
    )
    existing = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one_or_none()
    if existing is not None and existing.status == "succeeded":
        pages = session.execute(
            select(AcquisitionPage, RawObject)
            .join(RawObject, AcquisitionPage.raw_object_id == RawObject.id)
            .where(AcquisitionPage.acquisition_run_id == existing.id)
            .order_by(AcquisitionPage.page_index)
        ).all()
        return AcquisitionResult(
            run_id=run_id,
            status="succeeded",
            record_count=existing.record_count or 0,
            page_hashes=[(raw.sha256, raw.byte_size) for _, raw in pages],
            raw=None,
        )

    run_row = existing or AcquisitionRun(
        run_id=run_id,
        source_id=adapter.source_id,
        parameters=dict(request.parameters),
        online=request.online,
        requested_at=requested_at,
        terms_reference=adapter.terms_reference,
        code_version=_code_version(),
        status="running",
    )
    if existing is None:
        session.add(run_row)
        session.flush()

    try:
        raw = adapter.acquire(request)
    except AcquisitionError as exc:
        run_row.status = "failed"
        run_row.error_class = exc.failure_class
        run_row.error_detail = str(exc)[:2000]
        session.flush()
        return AcquisitionResult(
            run_id=run_id, status="failed", record_count=0,
            page_hashes=[], raw=None, error=str(exc),
        )

    page_hashes: list[tuple[str, int]] = []
    for page in raw.pages:
        key = _raw_key_for(adapter.source_id, page.sha256)
        store.put_content(RAW_BUCKET, key, page.body, sha256=page.sha256)
        raw_object = session.execute(
            select(RawObject).where(RawObject.sha256 == page.sha256)
        ).scalar_one_or_none()
        if raw_object is None:
            raw_object = RawObject(
                sha256=page.sha256,
                object_uri=f"s3://{RAW_BUCKET}/{key}",
                media_type="application/json",
                byte_size=len(page.body),
                first_seen_at=page.retrieved_at,
            )
            session.add(raw_object)
            session.flush()
        session.add(
            AcquisitionPage(
                acquisition_run_id=run_row.id,
                page_index=page.index,
                raw_object_id=raw_object.id,
                request_url=page.url,
                request_params={k: str(v) for k, v in page.params.items()},
            )
        )
        page_hashes.append((page.sha256, len(page.body)))

    combined = hashlib.sha256(
        "\n".join(sorted(h for h, _ in page_hashes)).encode()
    ).hexdigest()
    run_row.retrieved_at = raw.retrieved_at
    run_row.upstream_edited_at = raw.upstream_edited_at
    run_row.page_count = len(raw.pages)
    run_row.record_count = raw.record_count
    run_row.response_sha256 = combined
    run_row.schema_fingerprint = raw.schema_fingerprint
    run_row.status = "succeeded"
    health = adapter.health(raw)
    # Persist server-side counts for independent universe reconciliation.
    for key in ("count_before", "count_after", "oid_field"):
        if key in raw.metadata:
            health[key] = raw.metadata[key]
    run_row.health = health
    session.flush()

    return AcquisitionResult(
        run_id=run_id,
        status="succeeded",
        record_count=raw.record_count,
        page_hashes=page_hashes,
        raw=raw,
    )


def rehydrate(
    session: Session, store: ObjectStore, adapter: ArcGISLayerAdapter, run_id: str
) -> RawAcquisition:
    """Rebuild a RawAcquisition from persisted rows + verified raw bytes,
    with zero network access (offline replay path)."""

    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    rows = session.execute(
        select(AcquisitionPage, RawObject)
        .join(RawObject, AcquisitionPage.raw_object_id == RawObject.id)
        .where(AcquisitionPage.acquisition_run_id == run_row.id)
        .order_by(AcquisitionPage.page_index)
    ).all()
    request = AcquisitionRequest(
        online=False,
        parameters=run_row.parameters,
        raw_page_hashes=tuple((raw.sha256, raw.byte_size) for _, raw in rows),
    )
    raw = adapter.acquire(request)
    # Replay keeps the ORIGINAL acquisition times (bitemporal truth).
    raw.retrieved_at = run_row.retrieved_at
    raw.requested_at = run_row.requested_at
    raw.upstream_edited_at = run_row.upstream_edited_at
    return raw


def frozen_source_health(session: Session, run_ids: list[str]) -> list[dict]:
    """Source-health entries frozen into a release manifest."""

    entries: list[dict] = []
    for run_id in run_ids:
        run_row = session.execute(
            select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
        ).scalar_one()
        source = session.execute(
            select(Source).where(Source.source_id == run_row.source_id)
        ).scalar_one_or_none()
        entries.append(
            {
                "source_id": run_row.source_id,
                "title": source.title if source else None,
                "ok": run_row.status == "succeeded",
                "records": run_row.record_count,
                "retrieved_at": (
                    run_row.retrieved_at.isoformat() if run_row.retrieved_at else None
                ),
                "upstream_edited_at": (
                    run_row.upstream_edited_at.isoformat()
                    if run_row.upstream_edited_at
                    else None
                ),
                "schema_fingerprint": run_row.schema_fingerprint,
                "response_sha256": run_row.response_sha256,
                "notes": {"run_id": run_id, "online": str(run_row.online)},
            }
        )
    return entries
