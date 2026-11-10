"""OpenPali public API application.

Contract highlights (BACKEND-001):
- ``/v1/releases/current`` is the sole current/LKG resolver; every civic,
  tile, and source route is release-qualified;
- release-qualified responses are immutable: strong ETags + long cache
  headers; the current resolver uses short stale-while-revalidate caching;
- errors are RFC 9457 problem details;
- readiness reflects migrations, dependencies, and a valid current release.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .problem import http_exception_handler, validation_exception_handler
from .routers import evidence, health, metrics, releases, status

API_VERSION = "1.0.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="OpenPali Rebuild Analysis API",
        version=API_VERSION,
        description=(
            "Connect public records and spatial data through versioned releases "
            "for analysis of the Palisades rebuild. "
            "Resolve /v1/releases/current once, then use release-qualified routes."
        ),
        docs_url="/v1/docs",
        openapi_url="/v1/openapi.json",
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    from .routers.releases import NotModified

    @app.exception_handler(NotModified)
    async def not_modified_handler(request: Request, exc: NotModified) -> Response:
        return Response(
            status_code=304,
            headers={"ETag": exc.etag, "Cache-Control": exc.cache},
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response

    app.include_router(health.router)
    app.include_router(evidence.router)
    app.include_router(releases.router)
    app.include_router(metrics.router)
    app.include_router(status.router)
    return app


app = create_app()


def export_openapi() -> str:
    """Serialize the OpenAPI schema deterministically (CI drift check)."""

    schema = app.openapi()
    return json.dumps(schema, sort_keys=True, indent=1)


if __name__ == "__main__":
    # `python -m openpali.api.app export-openapi > contracts/openapi.json`
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "export-openapi":
        sys.stdout.write(export_openapi())
    else:
        import uvicorn

        uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=8000)


def representation_etag(*parts: str) -> str:
    return '"' + hashlib.sha256("|".join(parts).encode()).hexdigest()[:24] + '"'
