"""Configured production source adapters.

Endpoints, filters, and terms references follow the frozen source policy in
openpali-one-shot/research/production-mvp-architecture.md and the live
evidence in state/evidence/domain-probe-2026-07-11.json.
"""

from __future__ import annotations

from palisades.apn import normalize_apn

from .arcgis_source import ArcGISLayerAdapter

COUNTY_LAYER = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
    "Parcels_Debris_Removal_Public/FeatureServer/0"
)
LADBS_PERMIT_LAYER = (
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/"
    "LADBS_WF_Fire_Data_Palisades_Recovery_Area/FeatureServer/0"
)
LADBS_INSPECTION_TABLE = (
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/ArcGIS/rest/services/"
    "LADBS_WF_Inspection_Data_tbl_Palisades_Recovery_Area/FeatureServer/0"
)
DINS_LAYER = (
    "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
    "POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0"
)

DESTROYED_WHERE = "FIRE_NAME='Palisades' AND DAMAGE='Destroyed (>50%)'"


def county_parcels_adapter() -> ArcGISLayerAdapter:
    return ArcGISLayerAdapter(
        source_id="county_base",
        title="LA County Parcels Debris Removal (Palisades destroyed universe)",
        jurisdiction="multi",
        layer_url=COUNTY_LAYER,
        where=DESTROYED_WHERE,
        out_fields=(
            "APN,AIN,SITUSFULLADDRESS,SITUSADDRESS,SITUSZIP,CENTER_LAT,CENTER_LON,LCITY,"
            "COMMUNITY,DAMAGE,STRUCTURECATEGORY,ROE_STATUS,DEBRIS_CLEARED,"
            "FSO_PKG_APPROVED_USACE,REBUILD_PROGRESS,USETYPE,USEDESCRIPTION,YEARBUILT1,"
            "SQFTMAIN1,BEDROOMS1,BATHROOMS1,UNITS1,TOTAL_UNITS"
        ),
        return_geometry=True,
        geometry_format="geojson",
        native_key_fn=lambda attrs: normalize_apn(attrs.get("APN") or attrs.get("AIN")),
        terms_reference="LA County GIS open data; layer metadata snapshotted per acquisition",
    )


def ladbs_permits_adapter() -> ArcGISLayerAdapter:
    return ArcGISLayerAdapter(
        source_id="ladbs_permits",
        title="LADBS Palisades Recovery permits",
        jurisdiction="LA",
        layer_url=LADBS_PERMIT_LAYER,
        where="1=1",
        out_fields=(
            "PERMIT,APN,ADDRESS,PERMIT_TYPE,PERMIT_SUBTYPE,TYPE,PERMIT_STATUS,"
            "SUBMIT_DATE,PC_APPROVED_DATE,ISSUE_DATE,COFO_DATE,STATUS_DATE,"
            "PALISADES_WF_REBUILD"
        ),
        native_key_field="PERMIT",
        terms_reference="LA City GeoHub; PALISADES_WF_REBUILD semantics per domain probe evidence",
    )


def ladbs_inspections_adapter() -> ArcGISLayerAdapter:
    return ArcGISLayerAdapter(
        source_id="ladbs_inspections",
        title="LADBS wildfire inspection requests (Palisades)",
        jurisdiction="LA",
        layer_url=LADBS_INSPECTION_TABLE,
        where="1=1",
        out_fields="PERMIT,INSP_DT,INSP_DESC,INSP_STATUS,ADDRESS",
        native_key_field="OBJECTID",
        terms_reference="LA City GeoHub; INSP_STATUS public domain is exactly {'Insp Scheduled'}",
    )


def dins_adapter() -> ArcGISLayerAdapter:
    return ArcGISLayerAdapter(
        source_id="calfire_dins",
        title="CAL FIRE DINS structure damage assessments (Palisades incident)",
        jurisdiction="multi",
        layer_url=DINS_LAYER,
        where="INCIDENTNAME='Palisades'",
        out_fields=(
            "OBJECTID,INCIDENTNAME,INCIDENTNUM,DAMAGE,STRUCTURETYPE,STRUCTURECATEGORY,"
            "APN,SITEADDRESS,CITY,COUNTY,LATITUDE,LONGITUDE"
        ),
        return_geometry=True,
        geometry_format="geojson",
        native_key_field="OBJECTID",
        terms_reference=(
            "CAL FIRE OSFM; data.ca.gov lists CC-BY 'no restrictions on public use' for DINS"
        ),
    )


ADAPTERS = {
    "county_base": county_parcels_adapter,
    "ladbs_permits": ladbs_permits_adapter,
    "ladbs_inspections": ladbs_inspections_adapter,
    "calfire_dins": dins_adapter,
}
