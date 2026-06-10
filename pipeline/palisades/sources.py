"""Fetch + normalize every source into a list of scored-ready Parcel objects.

See docs/DATA_SOURCES.md for the endpoint rationale. Pipeline shape:
  fetch_destroyed_parcels()  -> base universe + geometry + jurisdiction + debris + pre-fire
  attach_ladbs_permits()     -> City-of-LA permit/CofO timeline (the rich scoring signal)
  attach_inspections()       -> current construction milestone (stage-4 position)
  attach_malibu_markers()    -> Malibu coarse stage
  (county-unincorporated coarse stage comes from the base layer's REBUILD_PROGRESS)
"""

from __future__ import annotations

from datetime import date

import httpx

from . import arcgis
from .apn import normalize_apn
from .dates import from_epoch_ms, from_oracle
from .http import USER_AGENT, cached_get_json
from .model import Event, Parcel, Permit, classify_milestone
from .neighborhoods import assign

FIRE_START = date(2025, 1, 7)

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

# Deep link to the public LADBS permit record.
LADBS_PERMIT_URL = "https://www.ladbsservices2.lacity.org/OnlineServices/PermitReport/PcisPermitDetail?id={no}"

# LCITY (county base layer) -> our jurisdiction enum
_JURIS = {"Los Angeles": "LA", "Malibu": "MALIBU", "Unincorporated": "COUNTY"}

# County REBUILD_PROGRESS -> coarse stage (used for unincorporated lots)
_COUNTY_PROGRESS_STAGE = {
    "rebuild applications received": 2,
    "zoning reviews cleared": 2,
    "full building plans received": 2,
    "building plans approved": 2,
    "building permits issued": 3,
    "rebuild in construction": 4,
    "in construction": 4,
    "construction completed": 5,
    "completed": 5,
}

# Malibu iconShape -> coarse stage
_MALIBU_STAGE = {
    "InPlanning": 2,
    "PendingBSReview": 2,
    "InBPC": 2,
    "PermitIssued": 3,
}


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


def fetch_destroyed_parcels(ttl_hours: float = 12.0) -> dict[str, Parcel]:
    """Base universe: every destroyed parcel with polygon geometry + attributes."""
    out_fields = (
        "APN,AIN,SITUSFULLADDRESS,SITUSADDRESS,SITUSZIP,CENTER_LAT,CENTER_LON,LCITY,"
        "COMMUNITY,DAMAGE,STRUCTURECATEGORY,ROE_STATUS,DEBRIS_CLEARED,FSO_PKG_APPROVED_USACE,"
        "REBUILD_PROGRESS,USETYPE,USEDESCRIPTION,YEARBUILT1,SQFTMAIN1,BEDROOMS1,BATHROOMS1,"
        "UNITS1,TOTAL_UNITS"
    )
    feats = arcgis.query_layer(
        BASE_LAYER, DESTROYED_WHERE, out_fields=out_fields, return_geometry=True,
        out_sr=4326, f="geojson", page_size=1000, ttl_hours=ttl_hours,
    )
    parcels: dict[str, Parcel] = {}
    skipped = 0
    for f in feats:
        a = _attrs(f)
        apn = normalize_apn(a.get("APN") or a.get("AIN"))
        if not apn or apn in parcels:
            skipped += 1 if not apn else 0
            continue
        geom = f.get("geometry")
        if not geom:
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
        # destruction event (universe definition)
        p.events.append(Event(FIRE_START, "destroyed", "Destroyed in the Palisades Fire"))
        # debris-cleared event
        roe = (a.get("ROE_STATUS") or "").lower()
        cleared = roe.startswith("final sign off") or "opt-out" in roe
        if cleared:
            d = from_oracle(a.get("FSO_PKG_APPROVED_USACE")) or FIRE_START
            label = "Lot cleared (private opt-out)" if "opt-out" in roe else "Debris removal complete (USACE)"
            p.events.append(Event(d, "debris_cleared", label))
        # coarse stage for non-LA jurisdictions from the county progress field
        if juris != "LA":
            prog = (a.get("REBUILD_PROGRESS") or "").strip().lower()
            cs = _COUNTY_PROGRESS_STAGE.get(prog)
            if cs is not None:
                p.coarse = True
                p.coarse_stage = cs
        parcels[apn] = p
    if skipped:
        print(f"  warning: {skipped} destroyed features had an unparseable APN and were skipped")
    return parcels


def attach_ladbs_permits(parcels: dict[str, Parcel], ttl_hours: float = 12.0) -> dict[str, str]:
    """City-of-LA permit timeline. Returns a PERMIT->APN map for inspection joins."""
    feats = arcgis.query_layer(
        LADBS_LAYER, "1=1",
        out_fields="PERMIT,APN,ADDRESS,PERMIT_TYPE,PERMIT_SUBTYPE,TYPE,PERMIT_STATUS,"
        "SUBMIT_DATE,PC_APPROVED_DATE,ISSUE_DATE,COFO_DATE,STATUS_DATE,PALISADES_WF_REBUILD",
        return_geometry=False, page_size=1000, ttl_hours=ttl_hours,
    )
    permit_to_apn: dict[str, str] = {}
    for f in feats:
        a = _attrs(f)
        apn = normalize_apn(a.get("APN"))
        permit_no = (a.get("PERMIT") or "").strip()
        if permit_no and apn:
            permit_to_apn[permit_no] = apn
        p = parcels.get(apn)
        if not p:
            continue  # permit on a non-destroyed parcel; ignore for v1
        submit = from_epoch_ms(a.get("SUBMIT_DATE"))
        issue = from_epoch_ms(a.get("ISSUE_DATE"))
        cofo = from_epoch_ms(a.get("COFO_DATE"))
        pc = from_epoch_ms(a.get("PC_APPROVED_DATE"))
        ptype = a.get("PERMIT_TYPE") or ""
        # Only a new-building permit constitutes "rebuilding the home" and drives the
        # rebuild stage. Pools, demolition, grading, additions are shown as permit
        # records on the card but do not advance the lot's rebuild stage.
        is_building = ptype.startswith("Bldg-New")

        # A parcel with rich LADBS data is NOT coarse.
        p.coarse = False
        p.coarse_stage = None

        # Permit record for the card
        p.permits.append(Permit(
            no=permit_no, type=ptype, status=a.get("PERMIT_STATUS") or a.get("TYPE") or "",
            submitted=submit, issued=issue, valuation=None,
            url=LADBS_PERMIT_URL.format(no=permit_no) if permit_no else None,
        ))
        # Stage-advancing events come ONLY from new-building permits. Ancillary
        # permits (pool, demo, grading, additions) appear as permit records on the
        # card but never advance the lot's rebuild stage.
        if is_building:
            if submit:
                p.events.append(Event(submit, "permit_submitted",
                                      "Rebuild application filed", ref=permit_no))
            if pc and not issue:
                p.events.append(Event(pc, "permit_submitted",
                                      "Plans approved (permit pending)", ref=permit_no))
            if issue:
                p.events.append(Event(issue, "permit_issued", "Building permit issued", ref=permit_no))
            if cofo:
                p.events.append(Event(cofo, "cofo", "Certificate of Occupancy issued", ref=permit_no))
    return permit_to_apn


def attach_inspections(parcels: dict[str, Parcel], permit_to_apn: dict[str, str],
                       ttl_hours: float = 12.0) -> None:
    """Current construction milestone per permit -> stage-4 position."""
    feats = arcgis.query_layer(
        INSPECTION_TABLE, "1=1",
        out_fields="PERMIT,INSP_DT,INSP_DESC,INSP_STATUS",
        return_geometry=False, page_size=1000, ttl_hours=ttl_hours,
    )
    for f in feats:
        a = _attrs(f)
        permit_no = (a.get("PERMIT") or "").strip()
        apn = permit_to_apn.get(permit_no)
        p = parcels.get(apn) if apn else None
        if not p:
            continue
        milestone = classify_milestone(a.get("INSP_DESC"))
        if not milestone:
            continue
        d = from_epoch_ms(a.get("INSP_DT")) or date.today()
        p.events.append(Event(
            d, "inspection",
            f"{a.get('INSP_DESC')} inspection ({a.get('INSP_STATUS', 'scheduled').lower()})",
            milestone=milestone,
        ))


def attach_malibu_markers(parcels: dict[str, Parcel], ttl_hours: float = 12.0) -> None:
    """Malibu coarse stage from the city rebuild dashboard marker feed."""
    try:
        data = cached_get_json(MALIBU_MARKERS, ttl_hours=ttl_hours)
    except (httpx.HTTPError, ValueError):
        return  # unofficial endpoint; degrade gracefully if shape/host changes
    for m in data if isinstance(data, list) else []:
        apn = normalize_apn(m.get("apn"))
        p = parcels.get(apn) if apn else None
        if not p:
            continue
        stage = _MALIBU_STAGE.get(m.get("iconShape"))
        if stage is None:
            continue
        # Only set coarse stage if we don't already have richer (LADBS) data.
        if not p.coarse and any(e.kind in ("permit_issued", "cofo") for e in p.events):
            continue
        p.coarse = True
        p.coarse_stage = max(stage, p.coarse_stage or 0)


def build_parcels(ttl_hours: float = 12.0) -> list[Parcel]:
    parcels = fetch_destroyed_parcels(ttl_hours)
    permit_to_apn = attach_ladbs_permits(parcels, ttl_hours)
    attach_inspections(parcels, permit_to_apn, ttl_hours)
    attach_malibu_markers(parcels, ttl_hours)
    return list(parcels.values())
