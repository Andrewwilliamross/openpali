"""Fetch + normalize every source into parcels with typed recovery observations.

Acquisition stays here (cached ArcGIS/JSON adapters + provenance); semantic
interpretation lives in ``openpali.domain`` / ``openpali.ingestion.normalize``
and is shared with the golden corpus tests and the platform ingestion path.

Pipeline shape:
  fetch_destroyed_parcels()  -> base universe + geometry + county observations
  attach_ladbs_permits()     -> permit records + permitting/design observations
  attach_inspections()       -> outcome-aware inspection observations
  attach_malibu_markers()    -> Malibu coarse observations
  build_parcels()            -> conflicts + parallel-lane projection per parcel
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from openpali.domain.conflicts import detect_conflicts
from openpali.domain.lanes import project_lanes
from openpali.domain.observations import RecoveryObservation, SourceRecordRef
from openpali.domain.policy import PermitClassification, PermitQualification
from openpali.domain.taxonomy import Interpretation, undocumented_values
from openpali.ingestion import normalize

from . import arcgis, provenance
from .apn import normalize_apn
from .dates import from_epoch_ms
from .http import cached_get_json
from .model import Parcel, Permit
from .neighborhoods import assign

BASE_LAYER = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
    "Parcels_Debris_Removal_Public/FeatureServer/0"
)
LADBS_LAYER = (
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/"
    "LADBS_WF_Fire_Data_Palisades_Recovery_Area/FeatureServer/0"
)
INSPECTION_TABLE = "https://maps.lacity.org/lahub/rest/services/WildfireRecovery/MapServer/4"
MALIBU_MARKERS = (
    "https://mlb-pptsrv.ci.malibu.ca.us/Home/GetProjectDashMarkers"
    "?sFireView=PalisadesRebuildStatsDetailWithBPComplete"
)

DESTROYED_WHERE = "FIRE_NAME='Palisades' AND DAMAGE='Destroyed (>50%)'"

# Official-record deep link. The City's open-data portal (Socrata) is the only
# PUBLIC, no-login source that resolves a specific permit by number. Links are
# PRESENCE-GATED — only attached to permits actually present in the dataset.
SOCRATA_PERMIT_DATASET = "gwh9-jnip"
SOCRATA_PERMIT_URL = (
    "https://data.lacity.org/d/{ds}/explore/query/"
    "SELECT%20*%20WHERE%20%60permit_nbr%60%3D%22{no}%22/page/filter"
)

# LCITY (county base layer) -> our jurisdiction enum
_JURIS = {"Los Angeles": "LA", "Malibu": "MALIBU", "Unincorporated": "COUNTY"}


@dataclass(slots=True)
class BuildReport:
    """Cross-source normalization accounting consumed by the publication gates."""

    interpretations: list[Interpretation] = field(default_factory=list)
    conflicts: list[RecoveryObservation] = field(default_factory=list)
    unjoined_permits: int = 0
    orphan_inspections: int = 0
    qualifying_applications: int = 0

    @property
    def undocumented(self) -> list[str]:
        return undocumented_values(self.interpretations)


def _struct_type(usetype: str | None, category: str | None, units: int | None) -> str:
    cat = (category or "").lower()
    use = (usetype or "").lower()
    if "single" in cat:
        return "SFR"
    if units and units > 1:
        return "MFR"
    if "commercial" in use or "commercial" in cat:
        return "COM"
    if "residential" in use:
        return "SFR"
    return "OTH"


def _attrs(feature: dict) -> dict:
    """Feature attributes regardless of f=json ({'attributes'}) or f=geojson ({'properties'})."""
    return feature.get("attributes") or feature.get("properties") or {}


def _int(v: object) -> int | None:
    try:
        i = int(float(v))  # handles "5", 5.0
        return i if i != 0 else (0 if v in (0, "0") else None)
    except (TypeError, ValueError):
        return None


def _observed_at(source_id: str) -> datetime:
    """When the source data was actually acquired (cache mtime for hits)."""

    last = provenance.latest_fetch(source_id)
    if last:
        return datetime.fromisoformat(last)
    return datetime.now(timezone.utc).replace(microsecond=0)


def fetch_destroyed_parcels(
    ttl_hours: float = 12.0, report: BuildReport | None = None
) -> dict[str, Parcel]:
    """Base universe: every destroyed parcel with geometry, attributes, and
    county-derived observations (destruction, cleanup, coarse progress)."""

    report = report if report is not None else BuildReport()
    out_fields = (
        "APN,AIN,SITUSFULLADDRESS,SITUSADDRESS,SITUSZIP,CENTER_LAT,CENTER_LON,LCITY,"
        "COMMUNITY,DAMAGE,STRUCTURECATEGORY,ROE_STATUS,DEBRIS_CLEARED,FSO_PKG_APPROVED_USACE,"
        "REBUILD_PROGRESS,USETYPE,USEDESCRIPTION,YEARBUILT1,SQFTMAIN1,BEDROOMS1,BATHROOMS1,"
        "UNITS1,TOTAL_UNITS"
    )
    with provenance.source("county_base"):
        feats = arcgis.query_layer(
            BASE_LAYER, DESTROYED_WHERE, out_fields=out_fields, return_geometry=True,
            out_sr=4326, f="geojson", page_size=1000, ttl_hours=ttl_hours,
        )
    observed_at = _observed_at("county_base")
    parcels: dict[str, Parcel] = {}
    unparseable = duplicates = no_geometry = 0
    for f in feats:
        a = _attrs(f)
        apn = normalize_apn(a.get("APN") or a.get("AIN"))
        if not apn:
            unparseable += 1
            continue
        if apn in parcels:
            duplicates += 1
            continue
        geom = f.get("geometry")
        if not geom:
            no_geometry += 1
            continue
        lon, lat = a.get("CENTER_LON"), a.get("CENTER_LAT")
        juris = _JURIS.get(a.get("LCITY"), "COUNTY")
        units = _int(a.get("UNITS1")) or _int(a.get("TOTAL_UNITS"))
        p = Parcel(
            apn=apn,
            # street-only situs reads cleanly on the map/card; full address carries city+zip
            address=(a.get("SITUSADDRESS") or a.get("SITUSFULLADDRESS") or "").strip(),
            jurisdiction=juris,
            struct=_struct_type(a.get("USETYPE"), a.get("STRUCTURECATEGORY"), units),
            damage="Destroyed",
            units=units,
            geometry=geom,
            lon=lon,
            lat=lat,
            neighborhood=assign(lon, lat) if lon and lat else "",
            pre_fire={
                "use": a.get("USEDESCRIPTION") or a.get("USETYPE"),
                "year_built": _int(a.get("YEARBUILT1")),
                "sqft": _int(a.get("SQFTMAIN1")),
                "beds": _int(a.get("BEDROOMS1")),
                "baths": _int(a.get("BATHROOMS1")),
                "units": units,
            },
        )
        record = normalize.normalize_county_parcel(
            a,
            observed_at=observed_at,
            source_record=SourceRecordRef("county_base", apn),
        )
        p.observations.extend(record.observations)
        report.interpretations.extend(record.interpretations)
        parcels[apn] = p
    if unparseable:
        print(f"  warning: {unparseable} destroyed features had an unparseable APN and were skipped")
    if no_geometry:
        print(f"  warning: {no_geometry} destroyed features had no geometry and were skipped")
    provenance.set_stats(
        "county_base",
        endpoint=BASE_LAYER, query=DESTROYED_WHERE,
        rows=len(feats), joined=len(parcels),
        unparseable=unparseable, duplicates=duplicates, no_geometry=no_geometry,
        undocumented_values=report.undocumented,
        schema_fingerprint=provenance.schema_fingerprint(_attrs(f) for f in feats),
        ok=True,
    )
    return parcels


def attach_ladbs_permits(
    parcels: dict[str, Parcel],
    ttl_hours: float = 12.0,
    report: BuildReport | None = None,
) -> tuple[dict[str, str], dict[str, PermitClassification]]:
    """City-of-LA permits: card records plus typed observations.

    Returns (permit_no -> APN, permit_no -> classification) for the
    inspection join. EVERY permit joins for evidence; only the qualification
    policy decides whether an inspection can ever touch the construction lane.
    """

    report = report if report is not None else BuildReport()
    with provenance.source("ladbs_permits"):
        feats = arcgis.query_layer(
            LADBS_LAYER, "1=1",
            out_fields="PERMIT,APN,ADDRESS,PERMIT_TYPE,PERMIT_SUBTYPE,TYPE,PERMIT_STATUS,"
            "SUBMIT_DATE,PC_APPROVED_DATE,ISSUE_DATE,COFO_DATE,STATUS_DATE,PALISADES_WF_REBUILD",
            return_geometry=False, page_size=1000, ttl_hours=ttl_hours,
        )
    observed_at = _observed_at("ladbs_permits")
    permit_to_apn: dict[str, str] = {}
    classifications: dict[str, PermitClassification] = {}
    unparseable = permits_attached = 0
    matched_apns: set[str] = set()
    for f in feats:
        a = _attrs(f)
        record = normalize.normalize_ladbs_permit(
            a,
            observed_at=observed_at,
            source_record=SourceRecordRef("ladbs_permits", str(a.get("PERMIT") or "")),
        )
        report.interpretations.extend(record.interpretations)
        if not record.apn and a.get("APN"):
            unparseable += 1
        if record.permit_no:
            if record.classification is not None:
                classifications[record.permit_no] = record.classification
            if record.apn:
                permit_to_apn[record.permit_no] = record.apn
            else:
                report.unjoined_permits += 1
        p = parcels.get(record.apn) if record.apn else None
        if not p:
            continue  # permit on a non-destroyed parcel; ignore for v1
        p.observations.extend(record.observations)
        qualification = (
            record.classification.qualification.value
            if record.classification
            else PermitQualification.UNDOCUMENTED.value
        )
        if (
            record.classification is not None
            and record.classification.qualification
            is PermitQualification.QUALIFYING_REBUILD_APPLICATION
        ):
            report.qualifying_applications += 1
        p.permits.append(Permit(
            no=record.permit_no,
            type=a.get("PERMIT_TYPE") or "",
            status=a.get("PERMIT_STATUS") or a.get("TYPE") or "",
            submitted=from_epoch_ms(a.get("SUBMIT_DATE")),
            issued=from_epoch_ms(a.get("ISSUE_DATE")),
            valuation=None,
            url=None,
            qualification=qualification,
        ))
        permits_attached += 1
        matched_apns.add(record.apn)
    provenance.set_stats(
        "ladbs_permits",
        endpoint=LADBS_LAYER, query="1=1",
        rows=len(feats), joined=permits_attached, parcels_matched=len(matched_apns),
        unparseable=unparseable,
        unjoined_permits=report.unjoined_permits,
        qualifying_applications=report.qualifying_applications,
        schema_fingerprint=provenance.schema_fingerprint(_attrs(f) for f in feats),
        ok=True,
    )
    return permit_to_apn, classifications


def attach_inspections(
    parcels: dict[str, Parcel],
    permit_to_apn: dict[str, str],
    classifications: dict[str, PermitClassification],
    ttl_hours: float = 12.0,
    report: BuildReport | None = None,
) -> None:
    """Outcome-aware inspection observations. Scheduled is never progress."""

    report = report if report is not None else BuildReport()
    with provenance.source("inspections"):
        feats = arcgis.query_layer(
            INSPECTION_TABLE, "1=1",
            out_fields="PERMIT,INSP_DT,INSP_DESC,INSP_STATUS",
            return_geometry=False, page_size=1000, ttl_hours=ttl_hours,
        )
    observed_at = _observed_at("inspections")
    joined = 0
    for f in feats:
        a = _attrs(f)
        permit_no = str(a.get("PERMIT") or "").strip()
        record = normalize.normalize_ladbs_inspection(
            a,
            observed_at=observed_at,
            source_record=SourceRecordRef("ladbs_inspections", permit_no),
            permit_classifications=classifications,
            permit_to_apn=permit_to_apn,
        )
        report.interpretations.extend(record.interpretations)
        apn = permit_to_apn.get(permit_no)
        p = parcels.get(apn) if apn else None
        if p is None:
            if permit_no and record.observations:
                report.orphan_inspections += 1
            continue
        p.observations.extend(record.observations)
        joined += 1
    provenance.set_stats(
        "inspections",
        endpoint=INSPECTION_TABLE, query="1=1",
        rows=len(feats), joined=joined,
        orphan_inspections=report.orphan_inspections,
        schema_fingerprint=provenance.schema_fingerprint(_attrs(f) for f in feats),
        ok=True,
    )


def attach_malibu_markers(
    parcels: dict[str, Parcel],
    ttl_hours: float = 12.0,
    report: BuildReport | None = None,
) -> None:
    """Malibu coarse observations from the city rebuild dashboard marker feed."""

    report = report if report is not None else BuildReport()
    try:
        with provenance.source("malibu_dash"):
            data = cached_get_json(MALIBU_MARKERS, ttl_hours=ttl_hours)
    except (httpx.HTTPError, ValueError) as e:
        # unofficial endpoint; degrade gracefully if shape/host changes
        provenance.set_stats("malibu_dash", endpoint=MALIBU_MARKERS, query=None,
                             rows=0, joined=0, ok=False, error=str(e) or type(e).__name__)
        return
    observed_at = _observed_at("malibu_dash")
    rows = data if isinstance(data, list) else []
    joined = 0
    for m in rows:
        apn = normalize_apn(m.get("apn"))
        p = parcels.get(apn) if apn else None
        if not p:
            continue
        record = normalize.normalize_malibu_marker(
            m,
            observed_at=observed_at,
            source_record=SourceRecordRef("malibu_dash", str(m.get("apn") or "")),
        )
        report.interpretations.extend(record.interpretations)
        if record.observations:
            p.observations.extend(record.observations)
            joined += 1
    provenance.set_stats(
        "malibu_dash",
        endpoint=MALIBU_MARKERS, query=None,
        rows=len(rows), joined=joined,
        schema_fingerprint=provenance.schema_fingerprint(rows),
        ok=True,
    )


def socrata_permit_presence(permit_nos: set[str], ttl_hours: float = 12.0) -> set[str]:
    """Which of these permit numbers actually resolve in the City open-data
    portal — so we only ever attach a deep link that works. Batched `in(...)`
    queries against gwh9-jnip; each chunk is independently cached."""
    found: set[str] = set()
    nos = sorted(n for n in permit_nos if n)
    failed_chunks = 0
    for i in range(0, len(nos), 200):
        chunk = nos[i : i + 200]
        inlist = "','".join(chunk)
        try:
            with provenance.source("socrata_links"):
                rows = cached_get_json(
                    f"https://data.lacity.org/resource/{SOCRATA_PERMIT_DATASET}.json",
                    {"$select": "permit_nbr", "$where": f"permit_nbr in('{inlist}')", "$limit": 5000},
                    ttl_hours=ttl_hours,
                )
        except (httpx.HTTPError, ValueError):
            failed_chunks += 1
            continue  # never let a verification lookup break the build
        for r in rows:
            if r.get("permit_nbr"):
                found.add(r["permit_nbr"])
    provenance.set_stats(
        "socrata_links",
        endpoint=f"https://data.lacity.org/resource/{SOCRATA_PERMIT_DATASET}.json",
        query="permit_nbr in(<permit numbers>)",
        rows=len(found), requested=len(nos), failed_chunks=failed_chunks,
        ok=failed_chunks == 0,
    )
    return found


def build_parcels(ttl_hours: float = 12.0) -> tuple[list[Parcel], BuildReport]:
    report = BuildReport()
    parcels = fetch_destroyed_parcels(ttl_hours, report)
    permit_to_apn, classifications = attach_ladbs_permits(parcels, ttl_hours, report)
    attach_inspections(parcels, permit_to_apn, classifications, ttl_hours, report)
    attach_malibu_markers(parcels, ttl_hours, report)

    # Same-snapshot contradiction detection over the full observation set,
    # then per-parcel parallel-lane projection (APN-indexed; observations
    # already live on their parcel, only derived conflicts need routing).
    all_observations = [o for p in parcels.values() for o in p.observations]
    detected_at = _observed_at("county_base")
    report.conflicts = detect_conflicts(all_observations, detected_at=detected_at)
    conflicts_by_apn: dict[str, list[RecoveryObservation]] = {}
    for conflict in report.conflicts:
        for ref in (conflict.subject, *conflict.related_subjects):
            if ref.type.value == "parcel":
                conflicts_by_apn.setdefault(ref.id, []).append(conflict)
    for apn, p in parcels.items():
        have = {o.observation_id for o in p.observations}
        for conflict in conflicts_by_apn.get(apn, []):
            if conflict.observation_id not in have:
                p.observations.append(conflict)
                have.add(conflict.observation_id)
        p.lane_state = project_lanes(p.observations)

    # Presence-gate official-record links: attach a deep link only to permits
    # that genuinely resolve in the City open-data portal.
    all_permits = {pm.no for p in parcels.values() for pm in p.permits if pm.no}
    present = socrata_permit_presence(all_permits, ttl_hours)
    linked = 0
    for p in parcels.values():
        for pm in p.permits:
            if pm.no in present:
                pm.url = SOCRATA_PERMIT_URL.format(ds=SOCRATA_PERMIT_DATASET, no=pm.no)
                linked += 1
    print(f"  official-record links: {linked}/{len(all_permits)} permits resolve in open data")
    return list(parcels.values()), report


_SOURCE_NOTES = {
    "county_base": "LA County Parcels Debris Removal (destroyed)",
    "ladbs_permits": "LADBS Palisades Recovery",
    "inspections": "LA City Wildfire Recovery inspections",
    "malibu_dash": "Malibu rebuild dashboard markers (unofficial)",
    "socrata_links": "City open-data permit deep-link presence",
}


def source_health() -> list[dict]:
    """Per-source health + provenance entries for meta.json (docs/ARTIFACTS.md).

    `as_of`/`fetched_at` reflect when the data was ACTUALLY fetched (cache mtime
    on offline runs), not when the pipeline ran — honest freshness.
    """
    out: list[dict] = []
    for sid, note in _SOURCE_NOTES.items():
        stats = provenance.get_stats(sid)
        agg = provenance.summarize(sid)
        last = agg["last_fetch"]
        entry: dict = {
            "id": sid,
            "as_of": last[:10] if last else None,
            "ok": bool(stats.get("ok", False)),
            "records": stats.get("rows", 0),
            "note": note,
            "endpoint": stats.get("endpoint"),
            "query": stats.get("query"),
            "joined": stats.get("joined"),
            "sha256": agg["sha256"],
            "schema_fingerprint": stats.get("schema_fingerprint"),
            "requests": agg["requests"],
            "bytes": agg["bytes"],
            "cache_hits": agg["cache_hits"],
            "fetched_at": last,
        }
        if stats.get("error"):
            entry["error"] = stats["error"]
        for k in ("unparseable", "duplicates", "no_geometry", "unknown_labels",
                  "undocumented_values", "unjoined_permits", "orphan_inspections",
                  "qualifying_applications",
                  "parcels_matched", "requested", "failed_chunks"):
            v = stats.get(k)
            if v not in (None, 0, []):
                entry[k] = v
        out.append(entry)
    return out
