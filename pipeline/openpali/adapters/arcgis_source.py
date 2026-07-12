"""ArcGIS FeatureServer/MapServer layer adapter.

Deterministic pagination (DATA-001):
- stable ``orderByFields=<oid> ASC`` ordering with resultOffset paging;
- layer metadata (fields + editing info) snapshotted per acquisition as page 0;
- server count queried before and after paging — a mismatch is a typed
  ``SourceMutationError``, never a silently partial dataset;
- repeated page bytes are detected and rejected;
- offline mode replays exact hash-verified raw pages and constructs no client.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Callable, Iterable

import httpx

from openpali.storage.objects import ObjectStore, RAW_BUCKET

from .base import (
    AcquisitionRequest,
    OfflineInputError,
    RawAcquisition,
    RawPage,
    SchemaDriftError,
    SourceMutationError,
    SourceRecord,
    TransientAcquisitionError,
)

USER_AGENT = "OpenPali/0.2 (open-source civic recovery project; respring.ai)"
PAGE_SIZE = 1000


def _fingerprint_fields(fields: list[dict]) -> str:
    canon = json.dumps(
        sorted((f.get("name", ""), f.get("type", "")) for f in fields),
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class ArcGISLayerAdapter:
    """One configured ArcGIS layer behind the SourceAdapter contract."""

    def __init__(
        self,
        *,
        source_id: str,
        title: str,
        jurisdiction: str,
        layer_url: str,
        where: str,
        out_fields: str,
        terms_reference: str,
        return_geometry: bool = False,
        geometry_format: str = "json",
        native_key_field: str = "OBJECTID",
        native_key_fn: Callable[[dict], str | None] | None = None,
        page_size: int = PAGE_SIZE,
    ) -> None:
        self.source_id = source_id
        self.title = title
        self.jurisdiction = jurisdiction
        self.layer_url = layer_url
        self.where = where
        self.out_fields = out_fields
        self.terms_reference = terms_reference
        self.return_geometry = return_geometry
        self.geometry_format = geometry_format
        self.native_key_field = native_key_field
        self.native_key_fn = native_key_fn
        self.page_size = page_size

    # -- online ---------------------------------------------------------------

    def _get(self, client: httpx.Client, url: str, params: dict) -> bytes:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = client.get(url, params=params)
                response.raise_for_status()
                return response.content
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                time.sleep(min(2**attempt, 8))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    last_error = exc
                    time.sleep(min(2**attempt, 8))
                else:
                    raise TransientAcquisitionError(
                        f"{self.source_id}: HTTP {exc.response.status_code} at {url}"
                    ) from exc
        raise TransientAcquisitionError(
            f"{self.source_id}: transport failed after retries: {last_error}"
        ) from last_error

    def _count(self, client: httpx.Client, params_base: dict) -> int:
        body = self._get(
            client,
            f"{self.layer_url}/query",
            {"where": self.where, "returnCountOnly": "true", "f": "json"},
        )
        data = json.loads(body)
        if "count" not in data:
            raise SchemaDriftError(f"{self.source_id}: count query returned {data!r:.200}")
        return int(data["count"])

    def acquire(self, request: AcquisitionRequest) -> RawAcquisition:
        if not request.online:
            return self._acquire_offline(request)
        requested_at = utcnow()
        pages: list[RawPage] = []
        page_hashes: set[str] = set()

        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(90.0, connect=20.0),
            follow_redirects=True,
            trust_env=True,  # honors HTTPS_PROXY inside the worker container
        ) as client:
            # page 0: layer metadata snapshot (schema + editing info evidence)
            meta_url = self.layer_url
            meta_params = {"f": "pjson"}
            meta_body = self._get(client, meta_url, meta_params)
            meta = json.loads(meta_body)
            fields = meta.get("fields") or []
            if not fields:
                raise SchemaDriftError(f"{self.source_id}: layer metadata has no fields")
            fingerprint = _fingerprint_fields(fields)
            if (
                request.expected_schema_fingerprint
                and fingerprint != request.expected_schema_fingerprint
            ):
                raise SchemaDriftError(
                    f"{self.source_id}: schema fingerprint {fingerprint} != "
                    f"expected {request.expected_schema_fingerprint}"
                )
            editing = meta.get("editingInfo") or {}
            edited_ms = editing.get("dataLastEditDate") or editing.get("lastEditDate")
            upstream_edited_at = (
                datetime.fromtimestamp(edited_ms / 1000, tz=timezone.utc)
                if edited_ms
                else None
            )
            pages.append(
                RawPage(
                    index=0,
                    url=meta_url,
                    params=meta_params,
                    body=meta_body,
                    sha256=hashlib.sha256(meta_body).hexdigest(),
                    retrieved_at=utcnow(),
                )
            )

            count_before = self._count(client, {})
            oid_field = meta.get("objectIdField") or self.native_key_field or "OBJECTID"

            offset = 0
            feature_total = 0
            page_index = 1
            while True:
                params = {
                    "where": self.where,
                    "outFields": self.out_fields,
                    "returnGeometry": str(self.return_geometry).lower(),
                    "orderByFields": f"{oid_field} ASC",
                    "resultOffset": offset,
                    "resultRecordCount": self.page_size,
                    "f": self.geometry_format,
                }
                if self.return_geometry and self.geometry_format == "geojson":
                    params["outSR"] = 4326
                body = self._get(client, f"{self.layer_url}/query", params)
                digest = hashlib.sha256(body).hexdigest()
                if digest in page_hashes:
                    raise SourceMutationError(
                        f"{self.source_id}: repeated page bytes at offset {offset}"
                    )
                page_hashes.add(digest)
                data = json.loads(body)
                if "error" in data:
                    raise SchemaDriftError(f"{self.source_id}: server error {data['error']}")
                batch = data.get("features", [])
                pages.append(
                    RawPage(
                        index=page_index,
                        url=f"{self.layer_url}/query",
                        params=params,
                        body=body,
                        sha256=digest,
                        retrieved_at=utcnow(),
                    )
                )
                feature_total += len(batch)
                exceeded = data.get("exceededTransferLimit") or (
                    (data.get("properties") or {}).get("exceededTransferLimit")
                )
                if not batch or (len(batch) < self.page_size and not exceeded):
                    break
                offset += len(batch)
                page_index += 1
                time.sleep(0.2)  # politeness to public agency servers

            count_after = self._count(client, {})

        if count_before != count_after:
            raise SourceMutationError(
                f"{self.source_id}: server count changed during acquisition "
                f"({count_before} -> {count_after})"
            )
        if feature_total != count_before:
            raise SourceMutationError(
                f"{self.source_id}: paged {feature_total} features but server "
                f"count is {count_before}"
            )

        return RawAcquisition(
            source_id=self.source_id,
            request=request,
            pages=pages,
            requested_at=requested_at,
            retrieved_at=utcnow(),
            upstream_edited_at=upstream_edited_at,
            record_count=feature_total,
            schema_fingerprint=fingerprint,
            metadata={"count_before": count_before, "count_after": count_after,
                      "oid_field": oid_field},
        )

    # -- offline ---------------------------------------------------------------

    def _acquire_offline(self, request: AcquisitionRequest) -> RawAcquisition:
        """Replay exact raw bytes from the object store. No network client is
        constructed on this path."""

        if not request.raw_page_hashes:
            raise OfflineInputError(
                f"{self.source_id}: offline acquisition requires raw page hashes"
            )
        store = ObjectStore()
        pages: list[RawPage] = []
        requested_at = utcnow()
        for index, (sha256, byte_size) in enumerate(request.raw_page_hashes):
            key = _raw_key_for(self.source_id, sha256)
            if not store.exists(RAW_BUCKET, key):
                raise OfflineInputError(
                    f"{self.source_id}: raw object missing for offline replay: {sha256}"
                )
            body = store.get_verified(RAW_BUCKET, key, sha256, byte_size)
            pages.append(
                RawPage(
                    index=index,
                    url=f"offline:{key}",
                    params={},
                    body=body,
                    sha256=sha256,
                    retrieved_at=requested_at,
                )
            )
        meta = json.loads(pages[0].body)
        fields = meta.get("fields") or []
        fingerprint = _fingerprint_fields(fields) if fields else None
        record_count = 0
        for page in pages[1:]:
            record_count += len(json.loads(page.body).get("features", []))
        editing = (meta.get("editingInfo") or {})
        edited_ms = editing.get("dataLastEditDate") or editing.get("lastEditDate")
        return RawAcquisition(
            source_id=self.source_id,
            request=request,
            pages=pages,
            requested_at=requested_at,
            retrieved_at=None,
            upstream_edited_at=(
                datetime.fromtimestamp(edited_ms / 1000, tz=timezone.utc)
                if edited_ms
                else None
            ),
            record_count=record_count,
            schema_fingerprint=fingerprint,
            metadata={"offline_replay": True},
        )

    # -- normalization ----------------------------------------------------------

    def normalize(self, raw: RawAcquisition) -> Iterable[SourceRecord]:
        for page in raw.pages:
            if page.index == 0:
                continue
            data = json.loads(page.body)
            for feature in data.get("features", []):
                attrs = feature.get("attributes") or feature.get("properties") or {}
                geometry = feature.get("geometry")
                payload = dict(attrs)
                if geometry is not None:
                    payload["_geometry"] = geometry
                if self.native_key_fn is not None:
                    key = self.native_key_fn(attrs)
                else:
                    key = attrs.get(self.native_key_field)
                if key is None:
                    continue
                yield SourceRecord(
                    native_key=str(key), payload=payload, page_index=page.index
                )

    def health(self, raw: RawAcquisition) -> dict:
        return {
            "record_count": raw.record_count,
            "pages": len(raw.pages),
            "schema_fingerprint": raw.schema_fingerprint,
            "upstream_edited_at": (
                raw.upstream_edited_at.isoformat() if raw.upstream_edited_at else None
            ),
            "offline": bool(raw.metadata.get("offline_replay")),
        }


def _raw_key_for(source_id: str, sha256: str) -> str:
    """Content-addressed raw key without a retrieval-date component.

    The retrieval date lives on acquisition-run/page rows; keeping it out of
    the key means identical bytes deduplicate across days while acquisition
    history stays complete (DATA-001).
    """

    return f"raw/{source_id}/{sha256}.json"
