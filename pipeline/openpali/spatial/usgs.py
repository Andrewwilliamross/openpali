"""USGS 2025 post-wildfire 3DEP DEM: acquisition + raw asset registration.

The four AOI LOD tiles (plus their .tfw world files and the vendor metadata
XML) flow through the SAME production acquisition contract as every civic
source: typed adapter -> run_acquisition -> immutable content-addressed raw
objects -> AcquisitionRun/AcquisitionPage evidence rows -> zero-network
replay by exact hash. Raw DEM tiles are then registered as versioned spatial
assets carrying the flight acquisition window (2025-01-21) — distinct from
our retrieval time — CRS EPSG:6340, vertical datum NAVD88 (GEOID18),
observation kind ``post_fire_observation``, and rights ``public_domain``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from openpali.adapters.base import (
    AcquisitionRequest,
    OfflineInputError,
    RawAcquisition,
    RawPage,
    SchemaDriftError,
    SourceRecord,
    TransientAcquisitionError,
)
from openpali.adapters.arcgis_source import USER_AGENT, _raw_key_for, utcnow
from openpali.ingestion.acquire import run_acquisition
from openpali.spatial.aoi import (
    OBSERVATION_KIND,
    VINTAGE_SLOT,
    FrozenAoi,
    load_aoi,
)
from openpali.spatial.registry import register_asset_version, version_id_from_hashes
from openpali.storage.models import AcquisitionRun, Source
from openpali.storage.objects import ObjectStore, RAW_BUCKET

USGS_SOURCE_ID = "usgs_3dep_postfire_dem"
AOI_SUBJECT_TYPE = "aoi"
AOI_SUBJECT_ID = "palisades-alphabet-streets"

#: flight acquisition window of the emergency lidar collect (vendor metadata:
#: NV5 acquisition for the Palisades fire impact zone). This is the OBSERVATION
#: time of the terrain surface; our HTTP retrieval time is ingest time only.
FLIGHT_DATE = date(2025, 1, 21)


def _parse_tfw(body: bytes) -> dict:
    """World file: pixel size x, rot, rot, pixel size y (negative), origin x/y
    of the CENTER of the upper-left pixel."""

    values = [float(v) for v in body.decode().split()]
    if len(values) != 6:
        raise SchemaDriftError(f"tfw expected 6 values, got {len(values)}")
    return {
        "pixel_size_x": values[0],
        "rotation_x": values[1],
        "rotation_y": values[2],
        "pixel_size_y": values[3],
        "upper_left_center_x": values[4],
        "upper_left_center_y": values[5],
    }


def _parse_vendor_dates(xml_body: bytes) -> dict:
    """Pull the FGDC acquisition date range out of the vendor metadata XML."""

    text = xml_body.decode(errors="replace")
    single = re.findall(r"<caldate>(\d{8})</caldate>", text)
    begin = re.findall(r"<begdate>(\d{8})</begdate>", text)
    end = re.findall(r"<enddate>(\d{8})</enddate>", text)

    def _fmt(raw: str) -> str:
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"

    return {
        "caldates": sorted({_fmt(v) for v in single}),
        "begdate": _fmt(begin[0]) if begin else None,
        "enddate": _fmt(end[0]) if end else None,
    }


class UsgsDemAdapter:
    """SourceAdapter for the staged USGS bare-earth DEM tiles.

    Page layout (order is deterministic; replay depends on it):
        0                       vendor metadata XML
        1 .. n                  tile GeoTIFFs (AOI order)
        n+1 .. 2n               tile .tfw world files (AOI order)
    """

    jurisdiction = "USGS (federal, public domain)"

    def __init__(self, aoi: FrozenAoi | None = None) -> None:
        self.aoi = aoi or load_aoi()
        self.source_id = USGS_SOURCE_ID
        self.title = "USGS 2025 Post-Wildfire LiDAR bare-earth DEM (PRELIMINARY), Palisades AOI"
        self.layer_url = self.aoi.staged_base
        self.terms_reference = self.aoi.reference_page

    # -- online ---------------------------------------------------------------

    def _get(self, client: httpx.Client, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = client.get(url)
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

    def acquire(self, request: AcquisitionRequest) -> RawAcquisition:
        if not request.online:
            return self._acquire_offline(request)
        requested_at = utcnow()
        pages: list[RawPage] = []

        def add_page(index: int, url: str, body: bytes, params: dict) -> None:
            pages.append(
                RawPage(
                    index=index,
                    url=url,
                    params=params,
                    body=body,
                    sha256=hashlib.sha256(body).hexdigest(),
                    retrieved_at=utcnow(),
                )
            )

        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(180.0, connect=20.0),
            follow_redirects=True,
            trust_env=True,  # honors HTTPS_PROXY inside the worker container
        ) as client:
            xml_body = self._get(client, self.aoi.vendor_metadata_xml)
            add_page(0, self.aoi.vendor_metadata_xml, xml_body, {"kind": "vendor_xml"})
            n = len(self.aoi.tiles)
            for i, tile in enumerate(self.aoi.tiles):
                url = f"{self.aoi.staged_base}/{tile.tif_name}"
                body = self._get(client, url)
                if body[:4] not in (b"II*\x00", b"MM\x00*"):
                    raise SchemaDriftError(
                        f"{self.source_id}: {tile.tif_name} is not a TIFF "
                        f"(magic {body[:4]!r})"
                    )
                add_page(1 + i, url, body, {"kind": "dem_tif", "tile": tile.name})
            for i, tile in enumerate(self.aoi.tiles):
                url = f"{self.aoi.staged_base}/{tile.tfw_name}"
                body = self._get(client, url)
                tfw = _parse_tfw(body)  # validates format + georeference
                expected_ulx = tile.utm_bounds[0] + tfw["pixel_size_x"] / 2
                if abs(tfw["upper_left_center_x"] - expected_ulx) > 0.01:
                    raise SchemaDriftError(
                        f"{self.source_id}: {tile.tfw_name} origin "
                        f"{tfw['upper_left_center_x']} != frozen AOI bound "
                        f"{expected_ulx}"
                    )
                add_page(1 + n + i, url, body, {"kind": "tfw", "tile": tile.name})

        return RawAcquisition(
            source_id=self.source_id,
            request=request,
            pages=pages,
            requested_at=requested_at,
            retrieved_at=utcnow(),
            upstream_edited_at=None,  # static staged product; no edit feed
            record_count=len(self.aoi.tiles),
            schema_fingerprint=hashlib.sha256(
                "|".join(t.name for t in self.aoi.tiles).encode()
            ).hexdigest()[:16],
            metadata={"vendor_dates": _parse_vendor_dates(pages[0].body)},
        )

    # -- offline ---------------------------------------------------------------

    def _acquire_offline(self, request: AcquisitionRequest) -> RawAcquisition:
        if not request.raw_page_hashes:
            raise OfflineInputError(
                f"{self.source_id}: offline acquisition requires raw page hashes"
            )
        store = ObjectStore()
        pages: list[RawPage] = []
        for index, (sha256, byte_size) in enumerate(request.raw_page_hashes):
            key = _raw_key_for(self.source_id, sha256)
            if not store.exists(RAW_BUCKET, key):
                raise OfflineInputError(
                    f"{self.source_id}: raw object missing for offline replay: {key}"
                )
            body = store.get_verified(RAW_BUCKET, key, sha256, byte_size)
            pages.append(
                RawPage(
                    index=index,
                    url=f"replay://{key}",
                    params={},
                    body=body,
                    sha256=sha256,
                    retrieved_at=utcnow(),
                )
            )
        return RawAcquisition(
            source_id=self.source_id,
            request=request,
            pages=pages,
            requested_at=utcnow(),
            retrieved_at=None,
            upstream_edited_at=None,
            record_count=max(0, (len(pages) - 1) // 2),
            schema_fingerprint=None,
            metadata={"vendor_dates": _parse_vendor_dates(pages[0].body)} if pages else {},
        )

    # -- normalize / health -----------------------------------------------------

    def normalize(self, raw: RawAcquisition) -> list[SourceRecord]:
        """One record per tile: georeference + content identity, byte-derived."""

        n = raw.record_count
        records: list[SourceRecord] = []
        for i in range(n):
            tif_page = raw.pages[1 + i]
            tfw_page = raw.pages[1 + n + i]
            tile_name = tif_page.params.get("tile") or f"tile_{i}"
            records.append(
                SourceRecord(
                    native_key=tile_name,
                    payload={
                        "tile": tile_name,
                        "tif_sha256": tif_page.sha256,
                        "tif_bytes": len(tif_page.body),
                        "tfw_sha256": tfw_page.sha256,
                        "georeference": _parse_tfw(tfw_page.body),
                        "vendor_xml_sha256": raw.pages[0].sha256,
                    },
                    page_index=1 + i,
                )
            )
        return records

    def health(self, raw: RawAcquisition) -> dict:
        return {
            "tiles": raw.record_count,
            "bytes_total": sum(len(p.body) for p in raw.pages),
            "vendor_xml_present": bool(raw.pages),
            "vendor_dates": raw.metadata.get("vendor_dates", {}),
        }


@dataclass(slots=True)
class UsgsRefreshResult:
    run_id: str
    status: str
    tiles: int
    raw_assets_registered: int
    page_hashes: list[tuple[str, int]]


def refresh_usgs(
    session: Session,
    store: ObjectStore,
    *,
    online: bool = True,
    requested_at: datetime | None = None,
) -> UsgsRefreshResult:
    """Acquire the frozen AOI tiles and register one raw asset version each."""

    aoi = load_aoi()
    adapter = UsgsDemAdapter(aoi)
    existing_source = session.execute(
        select(Source).where(Source.source_id == USGS_SOURCE_ID)
    ).scalar_one_or_none()
    if existing_source is None:
        session.add(
            Source(
                source_id=USGS_SOURCE_ID,
                title=adapter.title,
                jurisdiction=adapter.jurisdiction,
                authority="USGS 3D Elevation Program staged product",
                url_template=aoi.staged_base,
                terms_reference=aoi.reference_page,
                expected_cadence="static (one-time emergency product)",
                owner="openpali",
                criticality="spatial",
            )
        )
        session.flush()

    request = AcquisitionRequest(
        online=online,
        parameters={"aoi": aoi.name, "tiles": [t.name for t in aoi.tiles]},
    )
    result = run_acquisition(session, store, adapter, request, requested_at=requested_at)
    if result.status != "succeeded":
        return UsgsRefreshResult(
            run_id=result.run_id, status=result.status, tiles=0,
            raw_assets_registered=0, page_hashes=[],
        )

    raw = result.raw
    if raw is None:  # idempotent re-run: rebuild from persisted pages
        from openpali.ingestion.acquire import rehydrate

        raw = rehydrate(session, store, adapter, result.run_id)

    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == result.run_id)
    ).scalar_one()
    vendor_dates = raw.metadata.get("vendor_dates", {})
    flight_start, flight_end = _flight_window(vendor_dates)

    registered = 0
    for record in adapter.normalize(raw):
        tile = next(t for t in aoi.tiles if t.name == record.native_key)
        payload = record.payload
        created = register_asset_version(
            session,
            asset_id=f"usgs-dem-{tile.name}",
            version_id=version_id_from_hashes(payload["tif_sha256"], payload["tfw_sha256"]),
            subject_type=AOI_SUBJECT_TYPE,
            subject_id=AOI_SUBJECT_ID,
            asset_kind="dem_raster",
            vintage_slot=VINTAGE_SLOT,
            source_id=USGS_SOURCE_ID,
            observation_kind=OBSERVATION_KIND,
            rights_state="public_domain",
            horizontal_crs=aoi.horizontal_crs,
            vertical_datum=aoi.vertical_datum,
            units="meters",
            transform={
                "georeference": payload["georeference"],
                "utm_bounds": list(tile.utm_bounds),
                "kind": "tfw_world_file",
            },
            acquisition_start=flight_start,
            acquisition_end=flight_end,
            processed_at=None,  # raw bytes: no processing has happened
            extent_wkt=None,
            resolution_m=aoi.resolution_m,
            coverage={"tile": tile.name, "pixels": [1500, 1500]},
            quality={
                "provider_statement": aoi.rights,
                "preliminary": True,
                "content_units": 1,
            },
            lineage=[
                {
                    "kind": "raw_object",
                    "run_id": result.run_id,
                    "sha256": payload["tif_sha256"],
                    "bytes": payload["tif_bytes"],
                },
                {"kind": "vendor_xml", "sha256": payload["vendor_xml_sha256"]},
            ],
            object_uri=f"s3://{RAW_BUCKET}/{_raw_key_for(USGS_SOURCE_ID, payload['tif_sha256'])}",
            object_sha256=payload["tif_sha256"],
            format_version="geotiff-float32",
            status="stored",
        )
        registered += int(created)

    run_row.health = {**(run_row.health or {}), "raw_assets_registered": registered}
    session.flush()
    return UsgsRefreshResult(
        run_id=result.run_id,
        status="succeeded",
        tiles=len(aoi.tiles),
        raw_assets_registered=registered,
        page_hashes=result.page_hashes,
    )


def _flight_window(vendor_dates: dict) -> tuple[datetime, datetime]:
    """Flight acquisition window: vendor XML range when present, else the
    frozen AOI's documented flight date. Never our retrieval time."""

    beg = vendor_dates.get("begdate")
    end = vendor_dates.get("enddate")
    cal = vendor_dates.get("caldates") or []
    if not beg and cal:
        beg, end = cal[0], cal[-1]
    start_date = date.fromisoformat(beg) if beg else FLIGHT_DATE
    end_date = date.fromisoformat(end) if end else start_date
    return (
        datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc),
        datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc),
    )


def raw_tile_assets(session: Session) -> list[dict]:
    """The registered raw DEM tile assets with verified object references."""

    from openpali.storage.models import SpatialAsset

    rows = list(
        session.execute(
            select(SpatialAsset).where(
                SpatialAsset.source_id == USGS_SOURCE_ID,
                SpatialAsset.asset_kind == "dem_raster",
            ).order_by(SpatialAsset.asset_id)
        ).scalars()
    )
    return [
        {
            "asset_id": a.asset_id,
            "version_id": a.version_id,
            "tile": (a.coverage or {}).get("tile"),
            "sha256": a.object_sha256,
            "object_uri": a.object_uri,
            "transform": a.transform,
            "acquisition_start": a.acquisition_start,
            "acquisition_end": a.acquisition_end,
            "resolution_m": a.resolution_m,
        }
        for a in rows
    ]
