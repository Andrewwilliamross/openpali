"""Liveness and readiness.

Liveness: the process serves requests. Readiness: database reachable,
migrations applied, object store reachable, and a valid current or LKG
release exists. Product freshness is a separate signal on /v1/status.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import text

from openpali.storage.db import get_engine
from openpali.storage.objects import ObjectStore, RAW_BUCKET

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict:
    return {"status": "live"}


@router.get("/health/ready")
def ready(response: Response) -> dict:
    checks: dict[str, str] = {}
    ok = True

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            checks["database"] = "ok"
            checks["migrations"] = f"ok:{version}" if version else "missing"
            if not version:
                ok = False
            current = connection.execute(text(
                "SELECT current_release_id, lkg_release_id FROM ops.current_release WHERE id = 1"
            )).first()
            if current and (current[0] or current[1]):
                checks["release"] = "ok"
            else:
                checks["release"] = "no_current_or_lkg_release"
                ok = False
    except Exception as exc:  # noqa: BLE001 - readiness must not crash
        checks["database"] = f"error:{type(exc).__name__}"
        ok = False

    try:
        store = ObjectStore()
        store.client.head_bucket(Bucket=RAW_BUCKET)
        checks["object_store"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["object_store"] = f"error:{type(exc).__name__}"
        ok = False

    response.status_code = 200 if ok else 503
    return {"status": "ready" if ok else "not_ready", "checks": checks}
