"""Socrata and Malibu JSON adapters behind the SourceAdapter contract.

Both follow the same evidence rules as the ArcGIS adapter: every page is an
immutable raw object, offline replay constructs no network client, and source
errors are typed rather than becoming empty datasets.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Iterable

import httpx

from openpali.storage.objects import ObjectStore, RAW_BUCKET

from .arcgis_source import USER_AGENT, _raw_key_for, utcnow
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


class SocrataDatasetAdapter:
    """One Socrata dataset (data.lacity.org) with deterministic :id paging."""

    def __init__(
        self,
        *,
        source_id: str,
        title: str,
        jurisdiction: str,
        domain: str,
        dataset_id: str,
        select: str,
        where: str | None,
        terms_reference: str,
        native_key_field: str,
        page_size: int = 5000,
        max_rows: int | None = None,
    ) -> None:
        self.source_id = source_id
        self.title = title
        self.jurisdiction = jurisdiction
        self.domain = domain
        self.dataset_id = dataset_id
        self.select = select
        self.where = where
        self.terms_reference = terms_reference
        self.native_key_field = native_key_field
        self.page_size = page_size
        self.max_rows = max_rows
        self.layer_url = f"https://{domain}/resource/{dataset_id}.json"

    def _get(self, client: httpx.Client, params: dict) -> bytes:
        last: Exception | None = None
        for attempt in range(4):
            try:
                response = client.get(self.layer_url, params=params)
                response.raise_for_status()
                return response.content
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
                time.sleep(min(2**attempt, 8))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 or exc.response.status_code == 429:
                    last = exc
                    time.sleep(min(2**attempt, 8) * 2)
                else:
                    raise TransientAcquisitionError(
                        f"{self.source_id}: HTTP {exc.response.status_code}"
                    ) from exc
        raise TransientAcquisitionError(f"{self.source_id}: transport failed: {last}") from last

    def acquire(self, request: AcquisitionRequest) -> RawAcquisition:
        if not request.online:
            return _acquire_offline_json(self, request)
        requested_at = utcnow()
        pages: list[RawPage] = []
        page_hashes: set[str] = set()
        rows_total = 0
        offset = 0
        page_index = 0
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(120.0, connect=20.0),
            follow_redirects=True,
            trust_env=True,
        ) as client:
            while True:
                params: dict = {
                    "$select": f":id,{self.select}",
                    "$order": ":id",
                    "$limit": self.page_size,
                    "$offset": offset,
                }
                if self.where:
                    params["$where"] = self.where
                body = self._get(client, params)
                digest = hashlib.sha256(body).hexdigest()
                if digest in page_hashes:
                    raise SourceMutationError(
                        f"{self.source_id}: repeated page bytes at offset {offset}"
                    )
                page_hashes.add(digest)
                try:
                    rows = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise SchemaDriftError(f"{self.source_id}: non-JSON response") from exc
                if not isinstance(rows, list):
                    raise SchemaDriftError(f"{self.source_id}: unexpected payload shape")
                pages.append(
                    RawPage(
                        index=page_index,
                        url=self.layer_url,
                        params=params,
                        body=body,
                        sha256=digest,
                        retrieved_at=utcnow(),
                    )
                )
                rows_total += len(rows)
                if len(rows) < self.page_size:
                    break
                if self.max_rows and rows_total >= self.max_rows:
                    break
                offset += len(rows)
                page_index += 1
                time.sleep(0.2)
        return RawAcquisition(
            source_id=self.source_id,
            request=request,
            pages=pages,
            requested_at=requested_at,
            retrieved_at=utcnow(),
            upstream_edited_at=None,
            record_count=rows_total,
            schema_fingerprint=_json_rows_fingerprint(pages),
            metadata={},
        )

    def normalize(self, raw: RawAcquisition) -> Iterable[SourceRecord]:
        for page in raw.pages:
            rows = json.loads(page.body)
            for row in rows:
                key = row.get(self.native_key_field) or row.get(":id")
                if key is None:
                    continue
                yield SourceRecord(native_key=str(key), payload=row, page_index=page.index)

    def health(self, raw: RawAcquisition) -> dict:
        return {
            "record_count": raw.record_count,
            "pages": len(raw.pages),
            "schema_fingerprint": raw.schema_fingerprint,
            "offline": bool(raw.metadata.get("offline_replay")),
        }


class MalibuMarkerAdapter:
    """Malibu rebuild dashboard marker feed (single JSON document).

    The endpoint is an undocumented internal feed of the official city
    dashboard; derived observations carry a coarse/unofficial-feed flag and
    the jurisdiction warning lives in the source registry entry.
    """

    source_id = "malibu_dash"
    title = "Malibu rebuild dashboard markers (unofficial feed)"
    jurisdiction = "MALIBU"
    terms_reference = (
        "maliburebuilds.org dashboard; internal marker endpoint has no "
        "documented public contract — coarse status only, snapshot + disclose"
    )
    layer_url = (
        "https://mlb-pptsrv.ci.malibu.ca.us/Home/GetProjectDashMarkers"
        "?sFireView=PalisadesRebuildStatsDetailWithBPComplete"
    )

    def acquire(self, request: AcquisitionRequest) -> RawAcquisition:
        if not request.online:
            return _acquire_offline_json(self, request)
        requested_at = utcnow()
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(60.0, connect=20.0),
            follow_redirects=True,
            trust_env=True,
        ) as client:
            last: Exception | None = None
            body: bytes | None = None
            for attempt in range(4):
                try:
                    response = client.get(self.layer_url)
                    response.raise_for_status()
                    body = response.content
                    break
                except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                    last = exc
                    time.sleep(min(2**attempt, 8))
            if body is None:
                raise TransientAcquisitionError(f"{self.source_id}: transport failed: {last}")
        try:
            rows = json.loads(body)
        except json.JSONDecodeError as exc:
            raise SchemaDriftError(f"{self.source_id}: non-JSON response") from exc
        if not isinstance(rows, list):
            raise SchemaDriftError(f"{self.source_id}: unexpected payload shape")
        page = RawPage(
            index=0,
            url=self.layer_url,
            params={},
            body=body,
            sha256=hashlib.sha256(body).hexdigest(),
            retrieved_at=utcnow(),
        )
        return RawAcquisition(
            source_id=self.source_id,
            request=request,
            pages=[page],
            requested_at=requested_at,
            retrieved_at=utcnow(),
            upstream_edited_at=None,
            record_count=len(rows),
            schema_fingerprint=_json_rows_fingerprint([page]),
            metadata={},
        )

    def normalize(self, raw: RawAcquisition) -> Iterable[SourceRecord]:
        for page in raw.pages:
            rows = json.loads(page.body)
            for row in rows:
                key = row.get("apn") or row.get("id")
                if key is None:
                    continue
                yield SourceRecord(native_key=str(key), payload=row, page_index=page.index)

    def health(self, raw: RawAcquisition) -> dict:
        return {
            "record_count": raw.record_count,
            "pages": len(raw.pages),
            "schema_fingerprint": raw.schema_fingerprint,
            "offline": bool(raw.metadata.get("offline_replay")),
        }


def _json_rows_fingerprint(pages: list[RawPage]) -> str | None:
    fields: dict[str, set[str]] = {}
    saw_rows = False
    for page in pages:
        try:
            rows = json.loads(page.body)
        except json.JSONDecodeError:
            return None
        if not isinstance(rows, list):
            continue
        for row in rows[:200]:
            if not isinstance(row, dict):
                continue
            saw_rows = True
            for key, value in row.items():
                fields.setdefault(key, set()).add(type(value).__name__)
    if not saw_rows:
        return None
    canon = json.dumps(sorted((k, "|".join(sorted(v))) for k, v in fields.items()))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def _acquire_offline_json(adapter, request: AcquisitionRequest) -> RawAcquisition:
    """Shared offline replay: hash-verified raw pages, no network client."""

    if not request.raw_page_hashes:
        raise OfflineInputError(
            f"{adapter.source_id}: offline acquisition requires raw page hashes"
        )
    store = ObjectStore()
    pages: list[RawPage] = []
    requested_at = utcnow()
    record_count = 0
    for index, (sha256, byte_size) in enumerate(request.raw_page_hashes):
        key = _raw_key_for(adapter.source_id, sha256)
        if not store.exists(RAW_BUCKET, key):
            raise OfflineInputError(
                f"{adapter.source_id}: raw object missing for offline replay: {sha256}"
            )
        body = store.get_verified(RAW_BUCKET, key, sha256, byte_size)
        rows = json.loads(body)
        if isinstance(rows, list):
            record_count += len(rows)
        pages.append(
            RawPage(index=index, url=f"offline:{key}", params={}, body=body,
                    sha256=sha256, retrieved_at=requested_at)
        )
    return RawAcquisition(
        source_id=adapter.source_id,
        request=request,
        pages=pages,
        requested_at=requested_at,
        retrieved_at=None,
        upstream_edited_at=None,
        record_count=record_count,
        schema_fingerprint=_json_rows_fingerprint(pages),
        metadata={"offline_replay": True},
    )
