"""ArcGIS REST FeatureServer helpers (paginated queries, counts)."""

from __future__ import annotations

from typing import Any

from .http import cached_get_json


def layer_count(layer_url: str, where: str = "1=1", *, ttl_hours: float = 12.0) -> int:
    data = cached_get_json(
        f"{layer_url}/query",
        {"where": where, "returnCountOnly": "true", "f": "json"},
        ttl_hours=ttl_hours,
    )
    return int(data["count"])


def query_layer(
    layer_url: str,
    where: str = "1=1",
    *,
    out_fields: str = "*",
    return_geometry: bool = False,
    out_sr: int = 4326,
    geometry_envelope: tuple[float, float, float, float] | None = None,
    page_size: int = 1000,
    ttl_hours: float = 12.0,
    f: str = "json",
) -> list[dict[str, Any]]:
    """Fetch all features matching `where`, transparently paging with resultOffset.

    Returns the raw feature dicts ({"attributes": ..., "geometry": ...} for f=json,
    GeoJSON Feature dicts for f=geojson).
    """
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        params: dict[str, Any] = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": str(return_geometry).lower(),
            "outSR": out_sr,
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": f,
        }
        if geometry_envelope:
            xmin, ymin, xmax, ymax = geometry_envelope
            params.update(
                geometry=f"{xmin},{ymin},{xmax},{ymax}",
                geometryType="esriGeometryEnvelope",
                inSR=4326,
                spatialRel="esriSpatialRelIntersects",
            )
        data = cached_get_json(f"{layer_url}/query", params, ttl_hours=ttl_hours)
        batch = data.get("features", [])
        features.extend(batch)
        more = data.get("exceededTransferLimit") or (
            data.get("properties", {}).get("exceededTransferLimit")
        )
        if not batch or (len(batch) < page_size and not more):
            break
        offset += len(batch)
    return features
