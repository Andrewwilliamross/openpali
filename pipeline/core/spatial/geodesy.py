"""Exact coordinate transforms for the spatial core.

Conventions
-----------
- Geodetic coordinates are (lon_deg, lat_deg, h_m) on WGS84.
- ECEF (Earth-Centered Earth-Fixed) coordinates are metres, float64, shape (N, 3).
- LARIAC / LA County layers arrive in California State Plane Zone V,
  EPSG:2229 (NAD83, **US survey feet**) — converted via pyproj, which handles
  the datum shift and the survey-foot unit exactly.
- ENU frames are right-handed local tangent planes (east, north, up), used for
  3D Tiles root transforms and for registration in metre-scale local space.

WGS84⇄ECEF is implemented directly in numpy (vectorised, no per-point pyproj
overhead on the hot path); the geodetic recovery uses Bowring's method, which
converges to sub-millimetre in two iterations for |h| < 10 km.
"""

from __future__ import annotations

import numpy as np
from pyproj import Transformer

# WGS84 ellipsoid
_A = 6378137.0  # semi-major axis (m)
_F = 1.0 / 298.257223563  # flattening
_B = _A * (1.0 - _F)  # semi-minor axis
_E2 = _F * (2.0 - _F)  # first eccentricity squared
_EP2 = (_A * _A - _B * _B) / (_B * _B)  # second eccentricity squared

# EPSG:2229 (CA State Plane V, NAD83, usft) -> EPSG:4979 (WGS84 3D, lon/lat/h)
_SP_TO_WGS84 = Transformer.from_crs(2229, 4979, always_xy=True)


def wgs84_to_ecef(lon_deg: np.ndarray, lat_deg: np.ndarray, h_m: np.ndarray) -> np.ndarray:
    """Geodetic (deg, deg, m) → ECEF (N, 3) float64 metres."""
    lon = np.radians(np.asarray(lon_deg, dtype=np.float64))
    lat = np.radians(np.asarray(lat_deg, dtype=np.float64))
    h = np.asarray(h_m, dtype=np.float64)
    sin_lat, cos_lat = np.sin(lat), np.cos(lat)
    n = _A / np.sqrt(1.0 - _E2 * sin_lat * sin_lat)  # prime-vertical radius
    x = (n + h) * cos_lat * np.cos(lon)
    y = (n + h) * cos_lat * np.sin(lon)
    z = (n * (1.0 - _E2) + h) * sin_lat
    return np.stack([x, y, z], axis=-1)


def ecef_to_wgs84(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ECEF (N, 3) m → (lon_deg, lat_deg, h_m). Bowring's method, 3 iterations."""
    xyz = np.asarray(xyz, dtype=np.float64)
    x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    # Bowring's initial parametric latitude, then iterate the geodetic latitude.
    beta = np.arctan2(z * _A, p * _B)
    lat = np.arctan2(z + _EP2 * _B * np.sin(beta) ** 3, p - _E2 * _A * np.cos(beta) ** 3)
    for _ in range(2):
        beta = np.arctan2(_B * np.sin(lat), _A * np.cos(lat))
        lat = np.arctan2(z + _EP2 * _B * np.sin(beta) ** 3, p - _E2 * _A * np.cos(beta) ** 3)
    sin_lat = np.sin(lat)
    n = _A / np.sqrt(1.0 - _E2 * sin_lat * sin_lat)
    # Height: use the cos branch away from the poles (always true for LA).
    h = p / np.cos(lat) - n
    return np.degrees(lon), np.degrees(lat), h


def stateplane_to_wgs84(x_usft: np.ndarray, y_usft: np.ndarray,
                        z_usft: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """EPSG:2229 (US survey feet, NAD83) → (lon_deg, lat_deg, h_m).

    pyproj's 2229→4979 pipeline converts horizontal survey feet; the vertical
    component in LARIAC layers is also survey feet, converted here explicitly
    (1 usft = 1200/3937 m exactly).
    """
    x = np.asarray(x_usft, dtype=np.float64)
    y = np.asarray(y_usft, dtype=np.float64)
    z = np.zeros_like(x) if z_usft is None else np.asarray(z_usft, dtype=np.float64)
    lon, lat, _ = _SP_TO_WGS84.transform(x, y, np.zeros_like(x))
    h_m = z * (1200.0 / 3937.0)
    return np.asarray(lon), np.asarray(lat), h_m


def enu_rotation(lon_deg: float, lat_deg: float) -> np.ndarray:
    """3×3 rotation: ECEF vector → ENU components at the given origin."""
    lon = np.radians(lon_deg)
    lat = np.radians(lat_deg)
    sl, cl = np.sin(lon), np.cos(lon)
    sp, cp = np.sin(lat), np.cos(lat)
    return np.array(
        [
            [-sl, cl, 0.0],
            [-sp * cl, -sp * sl, cp],
            [cp * cl, cp * sl, sp],
        ]
    )


def ecef_to_enu(xyz: np.ndarray, origin_ecef: np.ndarray,
                lon_deg: float, lat_deg: float) -> np.ndarray:
    """ECEF points → local ENU metres about origin."""
    r = enu_rotation(lon_deg, lat_deg)
    return (np.asarray(xyz, dtype=np.float64) - origin_ecef) @ r.T


def enu_to_ecef(enu: np.ndarray, origin_ecef: np.ndarray,
                lon_deg: float, lat_deg: float) -> np.ndarray:
    """Local ENU metres → ECEF."""
    r = enu_rotation(lon_deg, lat_deg)
    return np.asarray(enu, dtype=np.float64) @ r + origin_ecef


def enu_to_ecef_matrix(lon_deg: float, lat_deg: float, h_m: float = 0.0) -> np.ndarray:
    """4×4 column-major-agnostic ENU→ECEF rigid transform (3D Tiles root transform)."""
    origin = wgs84_to_ecef(np.array(lon_deg), np.array(lat_deg), np.array(h_m))
    r = enu_rotation(lon_deg, lat_deg).T  # ENU→ECEF is the transpose
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = origin
    return m
