"""Configured production source adapters.

Endpoints, filters, and terms references follow the frozen source policy in
openpali-one-shot/research/production-mvp-architecture.md and the live
evidence in state/evidence/domain-probe-2026-07-11.json.
"""

from __future__ import annotations

from palisades.apn import normalize_apn

from .arcgis_source import ArcGISLayerAdapter
from .json_source import MalibuMarkerAdapter, SocrataDatasetAdapter

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
        out_fields="OBJECTID,PERMIT,INSP_DT,INSP_DESC,INSP_STATUS,ADDRESS",
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
            "OBJECTID,GLOBALID,INCIDENTNAME,INCIDENTNUM,INCIDENTSTARTDATE,DAMAGE,"
            "STRUCTURETYPE,STRUCTURECATEGORY,APN,SITEADDRESS,CITY,COUNTY,"
            "LATITUDE,LONGITUDE"
        ),
        return_geometry=True,
        geometry_format="geojson",
        native_key_field="GLOBALID",
        terms_reference=(
            "CAL FIRE OSFM; data.ca.gov lists CC-BY 'no restrictions on public use' for DINS"
        ),
    )


#: Palisades recovery-area bounding box for the Socrata cross-check
#: population (covers the LADBS recovery area; verified counts 2026-07-12:
#: 9,881 permits submitted since the fire, 30,774 total in-box).
PALISADES_BBOX_WHERE = (
    "lat between 33.99 and 34.13 AND lon between -118.62 and -118.44"
)


def socrata_permits_adapter() -> SocrataDatasetAdapter:
    return SocrataDatasetAdapter(
        source_id="socrata_permits",
        title="LA City open data: building permits (Palisades bbox, independent cross-check)",
        jurisdiction="LA",
        domain="data.lacity.org",
        dataset_id="gwh9-jnip",
        select=(
            "permit_nbr,apn,permit_type,permit_sub_type,status_desc,status_date,"
            "submitted_date,lat,lon,primary_address,zip_code"
        ),
        where=f"{PALISADES_BBOX_WHERE} AND submitted_date >= '2025-01-07T00:00:00'",
        native_key_field="permit_nbr",
        terms_reference=(
            "data.lacity.org terms: data may be corrected/overwritten and prior "
            "versions not retained — immutable raw snapshots are load-bearing"
        ),
    )


def socrata_cofo_adapter() -> SocrataDatasetAdapter:
    return SocrataDatasetAdapter(
        source_id="socrata_cofo",
        title="LA City open data: certificates of occupancy since fire (CC0, cross-check)",
        jurisdiction="LA",
        domain="data.lacity.org",
        dataset_id="3f9m-afei",
        select=(
            "cofo_number,cofo_issue_date,latest_status,assessor_book,assessor_page,"
            "assessor_parcel,pcis_permit,permit_type,permit_sub_type,street_name,zip_code"
        ),
        where="cofo_issue_date >= '2025-01-07T00:00:00'",
        native_key_field="cofo_number",
        terms_reference="data.lacity.org dataset 3f9m-afei, license CC0 1.0",
    )


def malibu_adapter() -> MalibuMarkerAdapter:
    return MalibuMarkerAdapter()


ADAPTERS = {
    "county_base": county_parcels_adapter,
    "ladbs_permits": ladbs_permits_adapter,
    "ladbs_inspections": ladbs_inspections_adapter,
    "calfire_dins": dins_adapter,
    "socrata_permits": socrata_permits_adapter,
    "socrata_cofo": socrata_cofo_adapter,
    "malibu_dash": malibu_adapter,
}
