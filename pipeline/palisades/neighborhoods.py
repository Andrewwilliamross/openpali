"""Pacific Palisades sub-neighborhoods.

Approximate centers, used for (a) the map's jump-to dropdown and (b) assigning
each parcel to its nearest neighborhood for roll-up stats. Boundaries here are
informal — these are community names, not legal designations.
"""

from __future__ import annotations

import math

NEIGHBORHOODS: list[dict] = [
    {"name": "The Alphabets / Village", "center": (-118.5266, 34.0440), "zoom": 15.5},
    {"name": "Huntington Palisades", "center": (-118.5190, 34.0368), "zoom": 15.3},
    {"name": "El Medio Bluffs", "center": (-118.5450, 34.0405), "zoom": 15.3},
    {"name": "Marquez Knolls", "center": (-118.5520, 34.0480), "zoom": 15.2},
    {"name": "Castellammare", "center": (-118.5570, 34.0440), "zoom": 15.5},
    {"name": "Paseo Miramar / Castellammare Mesa", "center": (-118.5530, 34.0512), "zoom": 15.3},
    {"name": "Palisades Highlands", "center": (-118.5430, 34.0780), "zoom": 14.6},
    {"name": "Bienveneda / Temescal", "center": (-118.5390, 34.0560), "zoom": 15.0},
    {"name": "Rustic Canyon", "center": (-118.5120, 34.0400), "zoom": 15.2},
    {"name": "Santa Monica Canyon", "center": (-118.5085, 34.0330), "zoom": 15.4},
    {"name": "The Riviera", "center": (-118.5010, 34.0455), "zoom": 15.0},
    {"name": "Sunset Mesa (County)", "center": (-118.5660, 34.0420), "zoom": 15.2},
    {"name": "Topanga (County)", "center": (-118.5880, 34.0700), "zoom": 13.8},
    {"name": "Malibu — Las Flores / PCH", "center": (-118.6300, 34.0370), "zoom": 14.2},
]


def assign(lon: float, lat: float) -> str:
    """Nearest-center assignment (fine at this scale; ~1 sq-mi neighborhoods)."""
    best, best_d = "", math.inf
    for n in NEIGHBORHOODS:
        cx, cy = n["center"]
        # crude planar distance with latitude correction — adequate for 10 km extents
        d = ((lon - cx) * math.cos(math.radians(lat))) ** 2 + (lat - cy) ** 2
        if d < best_d:
            best, best_d = n["name"], d
    return best
