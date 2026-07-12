"""Load service: normalized source records -> canonical bitemporal ledger.

Idempotent by construction: source-record versions, parcel versions, and
observations all derive deterministic IDs from content, and inserts use
ON CONFLICT DO NOTHING. Reprocessing the same bytes creates no duplicates
(DATA-002). ``observed_at`` always carries the ORIGINAL acquisition time —
replays must never advance observation time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from geoalchemy2.shape import from_shape
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from openpali.adapters.base import RawAcquisition, SourceRecord
from openpali.domain.observations import RecoveryObservation, SourceRecordRef
from openpali.domain.taxonomy import Interpretation
from openpali.identity.ids import (
    IDENTITY_SEED_POLICY_VERSION,
    canonical_json,
    identity_seed_for_apn,
    property_id_from_apn,
    record_version_id,
)
from openpali.ingestion import normalize
from openpali.storage.models import (
    AcquisitionRun,
    ParcelVersion,
    PropertyIdentity,
    RecoveryObservationRow,
    SourceRecordVersion,
)


@dataclass(slots=True)
class LoadResult:
    source_id: str
    run_id: str
    records_seen: int = 0
    record_versions_new: int = 0
    observations_new: int = 0
    parcels_new: int = 0
    parcels_superseded: int = 0
    skipped_no_key: int = 0
    interpretations: list[Interpretation] = field(default_factory=list)

    @property
    def undocumented(self) -> list[str]:
        from openpali.domain.taxonomy import undocumented_values

        return undocumented_values(self.interpretations)


def _payload_sha(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def _occurrence_columns(observation: RecoveryObservation) -> dict:
    from openpali.domain.temporal import DateInterval, ExactDate

    occurred = observation.occurred
    if isinstance(occurred, ExactDate):
        return {
            "occurred_kind": "exact",
            "occurred_earliest": occurred.value,
            "occurred_latest": occurred.value,
        }
    if isinstance(occurred, DateInterval):
        return {
            "occurred_kind": "interval",
            "occurred_earliest": occurred.earliest_date,
            "occurred_latest": occurred.latest_date,
        }
    return {"occurred_kind": "unknown", "occurred_earliest": None, "occurred_latest": None}


def insert_observations(
    session: Session,
    observations: list[RecoveryObservation],
    *,
    record_version: str | None,
) -> int:
    if not observations:
        return 0
    rows = []
    for observation in observations:
        rows.append(
            {
                "observation_id": observation.observation_id,
                "subject_type": observation.subject.type.value,
                "subject_id": observation.subject.id,
                "lane": observation.lane.value if observation.lane else None,
                "event_type": observation.event_type,
                "status": observation.status.value,
                **_occurrence_columns(observation),
                "observed_at": observation.observed_at,
                "record_version_id": record_version,
                "source_id": observation.source_record.source_id,
                "policy_version": observation.policy_version,
                "label": observation.label,
                "related_subjects": [s.to_json() for s in observation.related_subjects],
                "detail": dict(observation.detail),
            }
        )
    statement = (
        pg_insert(RecoveryObservationRow)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["observation_id"])
        .returning(RecoveryObservationRow.observation_id)
    )
    inserted = session.execute(statement).scalars().all()
    return len(inserted)


def _upsert_record_version(
    session: Session,
    *,
    source_id: str,
    native_key: str,
    payload: dict,
    run_row: AcquisitionRun,
    observed_at: datetime,
) -> tuple[str, bool]:
    payload_sha = _payload_sha(payload)
    version_id = record_version_id(source_id, native_key, payload_sha)
    statement = (
        pg_insert(SourceRecordVersion)
        .values(
            record_version_id=version_id,
            source_id=source_id,
            native_key=native_key,
            acquisition_run_id=run_row.id,
            payload_sha256=payload_sha,
            payload=payload,
            first_observed_at=observed_at,
        )
        .on_conflict_do_nothing(index_elements=["record_version_id"])
        .returning(SourceRecordVersion.record_version_id)
    )
    inserted = session.execute(statement).scalars().all()
    return version_id, bool(inserted)


def _ensure_property(session: Session, apn: str) -> str:
    property_id = property_id_from_apn(apn)
    statement = (
        pg_insert(PropertyIdentity)
        .values(
            property_id=property_id,
            identity_seed=identity_seed_for_apn(apn),
            seed_policy_version=IDENTITY_SEED_POLICY_VERSION,
        )
        .on_conflict_do_nothing(index_elements=["identity_seed"])
    )
    session.execute(statement)
    return property_id


def _geometry_value(payload: dict):
    geometry = payload.get("_geometry")
    if not geometry:
        return None
    try:
        geom: BaseGeometry = shape(geometry)
    except Exception:  # noqa: BLE001 - malformed source geometry stays null
        return None
    if geom.geom_type == "Polygon":
        from shapely.geometry import MultiPolygon

        geom = MultiPolygon([geom])
    if geom.geom_type != "MultiPolygon":
        return None
    return from_shape(geom, srid=4326)


def load_county_records(
    session: Session,
    records: list[SourceRecord],
    run_id: str,
    *,
    observed_at: datetime,
) -> LoadResult:
    """County parcels: identity + parcel version + county observations."""

    from palisades.neighborhoods import assign

    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    result = LoadResult(source_id="county_base", run_id=run_id)

    for record in records:
        result.records_seen += 1
        apn = record.native_key
        payload = record.payload
        version_id, is_new = _upsert_record_version(
            session,
            source_id="county_base",
            native_key=apn,
            payload=payload,
            run_row=run_row,
            observed_at=observed_at,
        )
        if is_new:
            result.record_versions_new += 1
        property_id = _ensure_property(session, apn)

        identity_row = session.execute(
            select(PropertyIdentity).where(PropertyIdentity.property_id == property_id)
        ).scalar_one()

        payload_sha = _payload_sha(payload)
        current = session.execute(
            select(ParcelVersion)
            .where(ParcelVersion.apn == apn, ParcelVersion.observed_to.is_(None))
            .order_by(ParcelVersion.observed_from.desc())
            .limit(1)
        ).scalar_one_or_none()
        needs_new_version = current is None or current.record_version_id != version_id
        if needs_new_version and current is not None:
            current.observed_to = observed_at
            result.parcels_superseded += 1
        if needs_new_version:
            lon = payload.get("CENTER_LON")
            lat = payload.get("CENTER_LAT")
            units = payload.get("UNITS1") or payload.get("TOTAL_UNITS")
            session.add(
                ParcelVersion(
                    property_identity_id=identity_row.id,
                    apn=apn,
                    jurisdiction={"Los Angeles": "LA", "Malibu": "MALIBU",
                                  "Unincorporated": "COUNTY"}.get(payload.get("LCITY"), "COUNTY"),
                    situs_address=(payload.get("SITUSADDRESS")
                                   or payload.get("SITUSFULLADDRESS") or "").strip(),
                    neighborhood=assign(lon, lat) if lon and lat else "",
                    struct_type=None,
                    damage_class=payload.get("DAMAGE"),
                    units=int(units) if isinstance(units, (int, float)) and units else None,
                    pre_fire={
                        "use": payload.get("USEDESCRIPTION") or payload.get("USETYPE"),
                        "year_built": payload.get("YEARBUILT1"),
                        "sqft": payload.get("SQFTMAIN1"),
                        "beds": payload.get("BEDROOMS1"),
                        "baths": payload.get("BATHROOMS1"),
                        "units": units,
                    },
                    center_lon=lon,
                    center_lat=lat,
                    geometry=_geometry_value(payload),
                    record_version_id=version_id,
                    observed_from=observed_at,
                )
            )
            result.parcels_new += 1

        normalized = normalize.normalize_county_parcel(
            payload,
            observed_at=observed_at,
            source_record=SourceRecordRef("county_base", apn, payload_sha),
        )
        result.interpretations.extend(normalized.interpretations)
        result.observations_new += insert_observations(
            session, normalized.observations, record_version=version_id
        )
    session.flush()
    return result
