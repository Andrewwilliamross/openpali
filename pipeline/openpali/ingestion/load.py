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

from palisades.apn import normalize_apn

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
    AcquisitionRecord,
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
    #: source-specific join accounting (e.g. DINS APN/spatial join counts)
    join_stats: dict = field(default_factory=dict)

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
    session.execute(pg_insert(AcquisitionRecord).values(
        acquisition_run_id=run_row.id, record_version_id=version_id,
    ).on_conflict_do_nothing())
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
        prior = session.execute(select(ParcelVersion).where(
            ParcelVersion.apn == apn, ParcelVersion.record_version_id == version_id,
        )).scalar_one_or_none()
        needs_new_version = prior is None
        advances_current = current is None or observed_at >= current.observed_from
        if needs_new_version and current is not None and advances_current:
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
                    observed_to=current.observed_from if current and not advances_current else None,
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


# ---------------------------------------------------------------------------
# LADBS permits
# ---------------------------------------------------------------------------


def load_ladbs_permits(
    session: Session,
    records: list[SourceRecord],
    run_id: str,
    *,
    observed_at: datetime,
) -> LoadResult:
    """LADBS permits: record versions + permit->property links + observations.

    Every permit joins as evidence; only the qualification policy decides
    whether it can carry rebuild-lane milestones (TRUTH-001).
    """

    from openpali.domain.policy import classify_permit
    from openpali.storage.models import CaseLink

    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    result = LoadResult(source_id="ladbs_permits", run_id=run_id)

    for record in records:
        result.records_seen += 1
        payload = record.payload
        permit_no = str(payload.get("PERMIT") or "").strip() or record.native_key
        version_id, is_new = _upsert_record_version(
            session,
            source_id="ladbs_permits",
            native_key=permit_no,
            payload=payload,
            run_row=run_row,
            observed_at=observed_at,
        )
        if is_new:
            result.record_versions_new += 1

        classification = classify_permit(
            payload.get("PERMIT_TYPE"), payload.get("PALISADES_WF_REBUILD")
        )
        result.interpretations.append(classification.permit_type)
        result.interpretations.append(classification.rebuild_flag)

        apn = normalize_apn(payload.get("APN"))
        if apn:
            property_id = property_id_from_apn(apn)
            session.execute(
                pg_insert(CaseLink)
                .values(
                    subject_type="permit_application",
                    subject_id=permit_no,
                    object_type="property",
                    object_id=property_id,
                    link_type="permit_on_property",
                    method="source_apn",
                    confidence="high",
                    detail={"apn": apn,
                            "qualification": classification.qualification.value},
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "subject_type", "subject_id", "object_type", "object_id", "link_type",
                    ]
                )
            )
        else:
            result.skipped_no_key += 1

        normalized = normalize.normalize_ladbs_permit(
            payload,
            observed_at=observed_at,
            source_record=SourceRecordRef("ladbs_permits", permit_no, _payload_sha(payload)),
        )
        # normalize_ladbs_permit re-runs classification internally; drop the
        # duplicate interpretations to keep undocumented counts stable.
        result.observations_new += insert_observations(
            session, normalized.observations, record_version=version_id
        )
    session.flush()
    return result


def permit_maps_from_ledger(
    session: Session,
) -> tuple[dict[str, object], dict[str, str]]:
    """Rebuild permit classification + APN maps from the latest LADBS record
    versions (used when the inspection loader runs in a separate process)."""

    from openpali.domain.policy import classify_permit
    from openpali.storage.models import SourceRecordVersion
    from sqlalchemy import func as sa_func

    latest = (
        select(
            SourceRecordVersion.native_key,
            sa_func.max(SourceRecordVersion.id).label("max_id"),
        )
        .where(SourceRecordVersion.source_id == "ladbs_permits")
        .group_by(SourceRecordVersion.native_key)
        .subquery()
    )
    rows = session.execute(
        select(SourceRecordVersion).join(
            latest, SourceRecordVersion.id == latest.c.max_id
        )
    ).scalars()
    classifications: dict[str, object] = {}
    permit_to_apn: dict[str, str] = {}
    for row in rows:
        payload = row.payload
        classifications[row.native_key] = classify_permit(
            payload.get("PERMIT_TYPE"), payload.get("PALISADES_WF_REBUILD")
        )
        apn = normalize_apn(payload.get("APN"))
        if apn:
            permit_to_apn[row.native_key] = apn
    return classifications, permit_to_apn


# ---------------------------------------------------------------------------
# LADBS inspections
# ---------------------------------------------------------------------------


def load_ladbs_inspections(
    session: Session,
    records: list[SourceRecord],
    run_id: str,
    *,
    observed_at: datetime,
    classifications: dict[str, object] | None = None,
    permit_to_apn: dict[str, str] | None = None,
) -> LoadResult:
    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    result = LoadResult(source_id="ladbs_inspections", run_id=run_id)
    if classifications is None or permit_to_apn is None:
        classifications, permit_to_apn = permit_maps_from_ledger(session)

    for record in records:
        result.records_seen += 1
        payload = record.payload
        version_id, is_new = _upsert_record_version(
            session,
            source_id="ladbs_inspections",
            native_key=record.native_key,
            payload=payload,
            run_row=run_row,
            observed_at=observed_at,
        )
        if is_new:
            result.record_versions_new += 1
        normalized = normalize.normalize_ladbs_inspection(
            payload,
            observed_at=observed_at,
            source_record=SourceRecordRef(
                "ladbs_inspections",
                str(payload.get("PERMIT") or record.native_key),
                _payload_sha(payload),
            ),
            permit_classifications=classifications,
            permit_to_apn=permit_to_apn,
        )
        result.interpretations.extend(normalized.interpretations)
        permit_no = str(payload.get("PERMIT") or "").strip()
        if permit_no and permit_no not in permit_to_apn and normalized.observations:
            result.skipped_no_key += 1  # orphan inspection (no joined permit)
        result.observations_new += insert_observations(
            session, normalized.observations, record_version=version_id
        )
    session.flush()
    return result


# ---------------------------------------------------------------------------
# Malibu dashboard markers
# ---------------------------------------------------------------------------


def load_malibu_markers(
    session: Session,
    records: list[SourceRecord],
    run_id: str,
    *,
    observed_at: datetime,
) -> LoadResult:
    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    result = LoadResult(source_id="malibu_dash", run_id=run_id)
    for record in records:
        result.records_seen += 1
        payload = record.payload
        version_id, is_new = _upsert_record_version(
            session,
            source_id="malibu_dash",
            native_key=record.native_key,
            payload=payload,
            run_row=run_row,
            observed_at=observed_at,
        )
        if is_new:
            result.record_versions_new += 1
        normalized = normalize.normalize_malibu_marker(
            payload,
            observed_at=observed_at,
            source_record=SourceRecordRef(
                "malibu_dash", record.native_key, _payload_sha(payload)
            ),
        )
        result.interpretations.extend(normalized.interpretations)
        result.observations_new += insert_observations(
            session, normalized.observations, record_version=version_id
        )
    session.flush()
    return result


# ---------------------------------------------------------------------------
# CAL FIRE DINS
# ---------------------------------------------------------------------------


def load_dins_structures(
    session: Session,
    records: list[SourceRecord],
    run_id: str,
    *,
    observed_at: datetime,
) -> LoadResult:
    """DINS structures: record versions, structure identities, damage
    observations, and a deterministic APN-then-spatial parcel join with
    explicit unmatched/ambiguous accounting (DATA-001)."""

    from sqlalchemy import text as sa_text

    from openpali.storage.models import CaseLink, StructureVersion

    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    result = LoadResult(source_id="calfire_dins", run_id=run_id)
    join_stats = {
        "matched_apn": 0,
        "matched_spatial": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "records_without_apn": 0,
        "damage_distribution": {},
    }

    for record in records:
        result.records_seen += 1
        payload = record.payload
        global_id = str(payload.get("GLOBALID") or "").strip() or record.native_key
        version_id, is_new = _upsert_record_version(
            session,
            source_id="calfire_dins",
            native_key=global_id,
            payload=payload,
            run_row=run_row,
            observed_at=observed_at,
        )
        if is_new:
            result.record_versions_new += 1

        damage_raw = str(payload.get("DAMAGE") or "")
        join_stats["damage_distribution"][damage_raw] = (
            join_stats["damage_distribution"].get(damage_raw, 0) + 1
        )

        # --- deterministic parcel join: (1) source APN, (2) spatial point ---
        apn = normalize_apn(payload.get("APN"))
        join_method = None
        joined_apn = None
        if not apn:
            join_stats["records_without_apn"] += 1
        if apn:
            known = session.execute(
                select(ParcelVersion.apn).where(
                    ParcelVersion.apn == apn, ParcelVersion.observed_to.is_(None)
                ).limit(1)
            ).scalar_one_or_none()
            if known:
                join_method, joined_apn = "source_apn", apn
        if join_method is None:
            lon = payload.get("LONGITUDE")
            lat = payload.get("LATITUDE")
            if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                hits = list(session.execute(
                    sa_text(
                        "SELECT apn FROM civic.parcel_version "
                        "WHERE observed_to IS NULL AND geometry IS NOT NULL "
                        "AND ST_Contains(geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326))"
                    ),
                    {"lon": lon, "lat": lat},
                ).scalars())
                unique_hits = sorted(set(hits))
                if len(unique_hits) == 1:
                    join_method, joined_apn = "spatial_point", unique_hits[0]
                elif len(unique_hits) > 1:
                    join_stats["ambiguous"] += 1
        if join_method is None:
            join_stats["unmatched"] += 1
        elif join_method == "source_apn":
            join_stats["matched_apn"] += 1
        else:
            join_stats["matched_spatial"] += 1

        # --- structure identity (append-only version row) ---
        if joined_apn:
            property_id = property_id_from_apn(joined_apn)
            identity_row = session.execute(
                select(PropertyIdentity).where(
                    PropertyIdentity.property_id == property_id
                )
            ).scalar_one_or_none()
            if identity_row is not None:
                existing_structure = session.execute(
                    select(StructureVersion).where(
                        StructureVersion.structure_id == f"dins-{global_id}",
                        StructureVersion.observed_to.is_(None),
                    ).limit(1)
                ).scalar_one_or_none()
                if existing_structure is None:
                    session.add(
                        StructureVersion(
                            structure_id=f"dins-{global_id}",
                            property_identity_id=identity_row.id,
                            source_native_id=global_id,
                            kind=str(payload.get("STRUCTURECATEGORY") or ""),
                            record_version_id=version_id,
                            observed_from=observed_at,
                        )
                    )
                session.execute(
                    pg_insert(CaseLink)
                    .values(
                        subject_type="structure",
                        subject_id=f"dins-{global_id}",
                        object_type="property",
                        object_id=property_id,
                        link_type="structure_on_property",
                        method=join_method,
                        confidence="high" if join_method == "source_apn" else "medium",
                        detail={"apn": joined_apn},
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "subject_type", "subject_id", "object_type", "object_id",
                            "link_type",
                        ]
                    )
                )

        normalized = normalize.normalize_dins_structure(
            payload,
            observed_at=observed_at,
            source_record=SourceRecordRef(
                "calfire_dins", global_id, _payload_sha(payload)
            ),
        )
        result.interpretations.extend(normalized.interpretations)
        # Route the damage observation to the JOINED parcel (source APN may be
        # absent while the spatial join succeeds).
        observations = normalized.observations
        if joined_apn and observations:
            observations = [_with_related_parcel(o, joined_apn) for o in observations]
        result.observations_new += insert_observations(
            session, observations, record_version=version_id
        )
    session.flush()
    result.join_stats = join_stats
    return result


def _with_related_parcel(observation, apn: str):
    """Return the observation with the joined parcel in related_subjects."""

    from dataclasses import replace

    from openpali.domain.observations import SubjectRef, SubjectType

    parcel_ref = SubjectRef(SubjectType.PARCEL, apn)
    if parcel_ref in observation.related_subjects:
        return observation
    return replace(
        observation,
        related_subjects=observation.related_subjects + (parcel_ref,),
    )


# ---------------------------------------------------------------------------
# Socrata cross-checks (verification data, never identity/event authority)
# ---------------------------------------------------------------------------


def load_socrata_crosscheck(
    session: Session,
    records: list[SourceRecord],
    run_id: str,
    *,
    observed_at: datetime,
) -> LoadResult:
    """Store immutable record versions for independent reconciliation.

    Cross-check datasets validate named metrics; they never create identities
    or recovery observations (frozen source policy)."""

    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    result = LoadResult(source_id=run_row.source_id, run_id=run_id)
    for record in records:
        result.records_seen += 1
        _, is_new = _upsert_record_version(
            session,
            source_id=run_row.source_id,
            native_key=record.native_key,
            payload=record.payload,
            run_row=run_row,
            observed_at=observed_at,
        )
        if is_new:
            result.record_versions_new += 1
    session.flush()
    return result
