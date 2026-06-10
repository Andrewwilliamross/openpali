"""Reconcile pipeline output against authoritative server-side counts.

The LADBS Palisades Recovery FeatureServer is both an ingestion source and the
official oracle: its server-side group-by counts feed the city's public dashboard.
After each run we re-query it under identical filters and compare.
"""

from __future__ import annotations

from . import arcgis
from .sources import BASE_LAYER, DESTROYED_WHERE, LADBS_LAYER


def _count(layer: str, where: str) -> int:
    return arcgis.layer_count(layer, where, ttl_hours=0)  # always live for validation


def _distinct_apns(where: str) -> int:
    feats = arcgis.query_layer(
        LADBS_LAYER, where, out_fields="APN", return_geometry=False, ttl_hours=0,
    )
    return len({f["attributes"].get("APN") for f in feats if f["attributes"].get("APN")})


def oracle_baselines() -> list[dict]:
    """Authoritative counts straight from the source layers (bypasses our cache).

    All LADBS metrics are computed on PERMIT_TYPE='Bldg-New' and counted by DISTINCT
    APN, to match the pipeline's parcel-level, home-rebuild semantics exactly.
    """
    b: list[dict] = []

    destroyed = _count(BASE_LAYER, DESTROYED_WHERE)
    b.append({"source": "LA County", "metric": "destroyed_parcels", "official": destroyed})

    b.append({"source": "LADBS", "metric": "parcels_bldgnew_application",
              "official": _distinct_apns("PERMIT_TYPE='Bldg-New'")})
    b.append({"source": "LADBS", "metric": "parcels_permit_issued_bldgnew",
              "official": _distinct_apns("PERMIT_TYPE='Bldg-New' AND ISSUE_DATE IS NOT NULL")})
    b.append({"source": "LADBS", "metric": "parcels_complete_cofo",
              "official": _distinct_apns("PERMIT_TYPE='Bldg-New' AND COFO_DATE IS NOT NULL")})

    return b


def reconcile(parcels: list[dict], baselines: list[dict]) -> list[dict]:
    """Attach our computed counts next to each official baseline and flag drift.

    `parcels` is the list of emitted GeoJSON-style property dicts (have 'stage',
    'jurisdiction', 'apn').
    """
    la = [p for p in parcels if p["jurisdiction"] == "LA"]
    ours = {
        "destroyed_parcels": len(parcels),
        "parcels_bldgnew_application": sum(1 for p in la if p["stage"] >= 2),
        "parcels_permit_issued_bldgnew": sum(1 for p in la if p["stage"] >= 3),
        "parcels_complete_cofo": sum(1 for p in la if p["stage"] == 5),
    }
    out = []
    for base in baselines:
        m = base["metric"]
        o = ours.get(m)
        official = base["official"]
        drift = None if (o is None or not official) else round(abs(o - official) / official * 100, 1)
        out.append({**base, "ours": o, "drift_pct": drift,
                    "ok": (drift is None or drift <= 5)})
    return out
