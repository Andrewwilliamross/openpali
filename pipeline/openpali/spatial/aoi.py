"""The frozen, checked-in Palisades AOI for the USGS post-fire spatial path.

The AOI was committed BEFORE any spatial execution (SPATIAL-001): four
independently requested USGS LOD tiles over the 'Alphabet Streets' area,
verified to contain 1,728 destroyed-universe parcels (>= the 25 required).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

AOI_PATH = Path(__file__).resolve().parent / "palisades_aoi.geojson"

VINTAGE_SLOT = "post_fire_2025_prelim"
OBSERVATION_KIND = "post_fire_observation"


@dataclass(slots=True)
class AoiTile:
    name: str
    utm_bounds: tuple[float, float, float, float]  # minE, minN, maxE, maxN

    @property
    def tif_name(self) -> str:
        return f"{self.name}.tif"

    @property
    def tfw_name(self) -> str:
        return f"{self.name}.tfw"


@dataclass(slots=True)
class FrozenAoi:
    name: str
    tiles: list[AoiTile]
    staged_base: str
    vendor_metadata_xml: str
    reference_page: str
    horizontal_crs: str
    vertical_datum: str
    resolution_m: float
    acquisition_date: str
    rights: str
    wgs84_polygon: list[list[float]]
    destroyed_parcels_inside: int

    @property
    def utm_bounds(self) -> tuple[float, float, float, float]:
        return (
            min(t.utm_bounds[0] for t in self.tiles),
            min(t.utm_bounds[1] for t in self.tiles),
            max(t.utm_bounds[2] for t in self.tiles),
            max(t.utm_bounds[3] for t in self.tiles),
        )

    @property
    def extent_wkt(self) -> str:
        ring = ", ".join(f"{lon} {lat}" for lon, lat in self.wgs84_polygon)
        return f"POLYGON(({ring}))"


def load_aoi(path: Path = AOI_PATH) -> FrozenAoi:
    doc = json.loads(path.read_text())
    source = doc["source"]
    return FrozenAoi(
        name=doc["name"],
        tiles=[
            AoiTile(name=t["name"], utm_bounds=tuple(t["utm_bounds"]))
            for t in doc["tiles"]
        ],
        staged_base=source["staged_base"],
        vendor_metadata_xml=source["vendor_metadata_xml"],
        reference_page=source["reference_page"],
        horizontal_crs=source["horizontal_crs"],
        vertical_datum=source["vertical_datum"],
        resolution_m=float(source["resolution_m"]),
        acquisition_date=source["acquisition_date"],
        rights=source["rights"],
        wgs84_polygon=doc["features"][0]["geometry"]["coordinates"][0],
        destroyed_parcels_inside=int(doc["verified"]["destroyed_parcels_inside"]),
    )
