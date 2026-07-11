"""Fetch + normalize every source into a list of scored-ready Parcel objects.

See Docs/initialbuild_docs/DATA_SOURCES.md for the prototype endpoint rationale.
Pipeline shape:
  fetch_destroyed_parcels()  -> base universe + geometry + jurisdiction + debris + pre-fire
  attach_ladbs_permits()     -> City-of-LA permit/CofO timeline (the rich scoring signal)
  attach_inspections()       -> current construction milestone (stage-4 position)
  attach_malibu_markers()    -> Malibu coarse stage
  (county-unincorporated coarse stage comes from the base layer's REBUILD_PROGRESS)
"""

from __future__ import annotations

from datetime import date

import httpx

from . import arcgis, provenance
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

# Official-record deep link. The City's open-data portal (Socrata) is the only
# PUBLIC, no-login source that resolves a specific permit by number: the LADBS
# permit portal (permitla.lacitydbs.org) requires Okta login, and the legacy
# PcisPermitDetail page keys on an internal surrogate id, not the permit number.
# The "submitted from 2020" dataset (gwh9-jnip) covers the full lifecycle
# (submitted → issued → finaled) across building/grading/electrical/etc.
# It does NOT carry every permit class (e.g. Fire Sprinkler 260xx), so links are
# PRESENCE-GATED — only attached to permits actually present in the dataset.
SOCRATA_PERMIT_DATASET = "gwh9-jnip"
SOCRATA_PERMIT_URL = (
    "https://data.lacity.org/d/{ds}/explore/query/"
    "SELECT%20*%20WHERE%20%60permit_nbr%60%3D%22{no}%22/page/filter"
)

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
    with provenance.source("county_base"):
        feats = arcgis.query_layer(
            BASE_LAYER, DESTROYED_WHERE, out_fields=out_fields, return_geometry=True,
            out_sr=4326, f="geojson", page_size=1000, ttl_hours=ttl_hours,
        )
    parcels: dict[str, Parcel] = {}
    unparseable = duplicates = no_geometry = 0
    unknown_progress: set[str] = set()
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
            elif prog:
                unknown_progress.add(prog)
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
        unknown_labels=sorted(unknown_progress),
        schema_fingerprint=provenance.schema_fingerprint(_attrs(f) for f in feats),
        ok=True,
    )
    return parcels


def attach_ladbs_permits(parcels: dict[str, Parcel], ttl_hours: float = 12.0) -> dict[str, str]:
    """City-of-LA permit timeline. Returns a PERMIT->APN map for inspection joins."""
    with provenance.source("ladbs_permits"):
        feats = arcgis.query_layer(
            LADBS_LAYER, "1=1",
            out_fields="PERMIT,APN,ADDRESS,PERMIT_TYPE,PERMIT_SUBTYPE,TYPE,PERMIT_STATUS,"
            "SUBMIT_DATE,PC_APPROVED_DATE,ISSUE_DATE,COFO_DATE,STATUS_DATE,PALISADES_WF_REBUILD",
            return_geometry=False, page_size=1000, ttl_hours=ttl_hours,
        )
    permit_to_apn: dict[str, str] = {}
    unparseable = permits_attached = 0
    matched_apns: set[str] = set()
    for f in feats:
        a = _attrs(f)
        apn = normalize_apn(a.get("APN"))
        if not apn and a.get("APN"):
            unparseable += 1
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

        # Permit record for the card. The official-record url is filled in later
        # by presence-gating against the City open-data portal (build_parcels).
        p.permits.append(Permit(
            no=permit_no, type=ptype, status=a.get("PERMIT_STATUS") or a.get("TYPE") or "",
            submitted=submit, issued=issue, valuation=None, url=None,
        ))
        permits_attached += 1
        matched_apns.add(apn)
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
    provenance.set_stats(
        "ladbs_permits",
        endpoint=LADBS_LAYER, query="1=1",
        rows=len(feats), joined=permits_attached, parcels_matched=len(matched_apns),
        unparseable=unparseable,
        schema_fingerprint=provenance.schema_fingerprint(_attrs(f) for f in feats),
        ok=True,
    )
    return permit_to_apn


def attach_inspections(parcels: dict[str, Parcel], permit_to_apn: dict[str, str],
                       ttl_hours: float = 12.0) -> None:
    """Current construction milestone per permit -> stage-4 position."""
    with provenance.source("inspections"):
        feats = arcgis.query_layer(
            INSPECTION_TABLE, "1=1",
            out_fields="PERMIT,INSP_DT,INSP_DESC,INSP_STATUS",
            return_geometry=False, page_size=1000, ttl_hours=ttl_hours,
        )
    joined = 0
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
        joined += 1
    provenance.set_stats(
        "inspections",
        endpoint=INSPECTION_TABLE, query="1=1",
        rows=len(feats), joined=joined,
        schema_fingerprint=provenance.schema_fingerprint(_attrs(f) for f in feats),
        ok=True,
    )


def attach_malibu_markers(parcels: dict[str, Parcel], ttl_hours: float = 12.0) -> None:
    """Malibu coarse stage from the city rebuild dashboard marker feed."""
    try:
        with provenance.source("malibu_dash"):
            data = cached_get_json(MALIBU_MARKERS, ttl_hours=ttl_hours)
    except (httpx.HTTPError, ValueError) as e:
        # unofficial endpoint; degrade gracefully if shape/host changes
        provenance.set_stats("malibu_dash", endpoint=MALIBU_MARKERS, query=None,
                             rows=0, joined=0, ok=False, error=str(e) or type(e).__name__)
        return
    rows = data if isinstance(data, list) else []
    joined = 0
    unknown_shapes: set[str] = set()
    for m in rows:
        apn = normalize_apn(m.get("apn"))
        p = parcels.get(apn) if apn else None
        if not p:
            continue
        stage = _MALIBU_STAGE.get(m.get("iconShape"))
        if stage is None:
            if m.get("iconShape"):
                unknown_shapes.add(str(m["iconShape"]))
            continue
        # Only set coarse stage if we don't already have richer (LADBS) data.
        if not p.coarse and any(e.kind in ("permit_issued", "cofo") for e in p.events):
            continue
        p.coarse = True
        p.coarse_stage = max(stage, p.coarse_stage or 0)
        joined += 1
    provenance.set_stats(
        "malibu_dash",
        endpoint=MALIBU_MARKERS, query=None,
        rows=len(rows), joined=joined,
        unknown_labels=sorted(unknown_shapes),
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


def build_parcels(ttl_hours: float = 12.0) -> list[Parcel]:
    parcels = fetch_destroyed_parcels(ttl_hours)
    permit_to_apn = attach_ladbs_permits(parcels, ttl_hours)
    attach_inspections(parcels, permit_to_apn, ttl_hours)
    attach_malibu_markers(parcels, ttl_hours)

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
    return list(parcels.values())


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
                  "parcels_matched", "requested", "failed_chunks"):
            v = stats.get(k)
            if v not in (None, 0, []):
                entry[k] = v
        out.append(entry)
    return out
