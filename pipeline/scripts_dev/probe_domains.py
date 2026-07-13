"""One-off primary-source domain probe (CP1 evidence).

Runs groupBy statistics against the live authoritative layers through the
existing cached adapter so the raw responses land in data/raw with sha256
provenance. Output is printed as JSON for the evidence log.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from palisades.http import cached_get_json  # noqa: E402

BASE_LAYER = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
    "Parcels_Debris_Removal_Public/FeatureServer/0"
)
LADBS_LAYER = (
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/"
    "LADBS_WF_Fire_Data_Palisades_Recovery_Area/FeatureServer/0"
)
INSPECTION_TABLE = "https://maps.lacity.org/lahub/rest/services/WildfireRecovery/MapServer/4"
INSPECTION_TABLE_S5 = (
    "https://services5.arcgis.com/7nsPwEMP38bSkCjy/ArcGIS/rest/services/"
    "LADBS_WF_Inspection_Data_tbl_Palisades_Recovery_Area/FeatureServer/0"
)


def group_counts(layer: str, field: str, where: str = "1=1") -> list[dict]:
    data = cached_get_json(
        f"{layer}/query",
        {
            "where": where,
            "groupByFieldsForStatistics": field,
            "outStatistics": json.dumps(
                [{"statisticType": "count", "onStatisticField": field, "outStatisticFieldName": "n"}]
            ),
            "f": "json",
        },
        ttl_hours=0.0,
    )
    rows = []
    for feature in data.get("features", []):
        attrs = feature.get("attributes", {})
        rows.append({field: attrs.get(field), "n": attrs.get("n")})
    if "error" in data:
        rows.append({"error": data["error"]})
    return sorted(rows, key=lambda r: -(r.get("n") or 0))


def layer_meta(layer: str) -> dict:
    data = cached_get_json(layer, {"f": "pjson"}, ttl_hours=0.0)
    fields = {
        f["name"]: {
            "type": f.get("type"),
            "domain": f.get("domain"),
            "alias": f.get("alias"),
        }
        for f in data.get("fields", [])
    }
    return {
        "name": data.get("name"),
        "lastEditDate": (data.get("editingInfo") or {}).get("lastEditDate"),
        "dataLastEditDate": (data.get("editingInfo") or {}).get("dataLastEditDate"),
        "maxRecordCount": data.get("maxRecordCount"),
        "fields": fields,
        "error": data.get("error"),
    }


def main() -> None:
    out: dict = {}

    out["ladbs_meta"] = layer_meta(LADBS_LAYER)
    out["ladbs_PALISADES_WF_REBUILD"] = group_counts(LADBS_LAYER, "PALISADES_WF_REBUILD")
    out["ladbs_PERMIT_TYPE"] = group_counts(LADBS_LAYER, "PERMIT_TYPE")
    out["ladbs_PERMIT_STATUS"] = group_counts(LADBS_LAYER, "PERMIT_STATUS")
    out["ladbs_rebuild_by_type"] = group_counts(
        LADBS_LAYER, "PERMIT_TYPE,PALISADES_WF_REBUILD"
    )

    out["insp_meta_lahub"] = layer_meta(INSPECTION_TABLE)
    out["insp_INSP_STATUS_lahub"] = group_counts(INSPECTION_TABLE, "INSP_STATUS")
    out["insp_meta_s5"] = layer_meta(INSPECTION_TABLE_S5)
    out["insp_INSP_STATUS_s5"] = group_counts(INSPECTION_TABLE_S5, "INSP_STATUS")

    out["county_meta"] = layer_meta(BASE_LAYER)
    out["county_ROE_STATUS"] = group_counts(
        BASE_LAYER, "ROE_STATUS", where="FIRE_NAME='Palisades'"
    )
    out["county_REBUILD_PROGRESS"] = group_counts(
        BASE_LAYER, "REBUILD_PROGRESS", where="FIRE_NAME='Palisades'"
    )
    out["county_DAMAGE"] = group_counts(BASE_LAYER, "DAMAGE", where="FIRE_NAME='Palisades'")

    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
