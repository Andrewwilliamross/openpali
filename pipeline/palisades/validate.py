"""Reconcile pipeline output against authoritative server-side counts.

The LADBS Palisades Recovery FeatureServer is both an ingestion source and the
official oracle: its server-side group-by counts feed the city's public
dashboard. After each run we re-query it under the CORRECTED qualifying-rebuild
filters (PERMIT_TYPE='Bldg-New' AND PALISADES_WF_REBUILD='Rebuild') and compare
against our lane-milestone counts.

Live runs bypass the cache (ttl 0) so the oracle is genuinely independent of
the ingest path's cache; offline runs reuse the cached oracle responses so
reconciliation is never silently skipped — each baseline row carries the as_of
date of the fetch that actually produced it.

Independent cross-source reconciliation (Socrata, dashboards) is implemented in
the analytics platform track; this module covers same-source server-side
consistency for the static-artifact path.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import arcgis, provenance
from .sources import BASE_LAYER, DESTROYED_WHERE, LADBS_LAYER

QUALIFYING_WHERE = "PERMIT_TYPE='Bldg-New' AND PALISADES_WF_REBUILD='Rebuild'"


def _count(layer: str, where: str, ttl_hours: float) -> int:
    return arcgis.layer_count(layer, where, ttl_hours=ttl_hours)


def _distinct_apns(where: str, ttl_hours: float) -> int:
    feats = arcgis.query_layer(
        LADBS_LAYER, where, out_fields="APN", return_geometry=False, ttl_hours=ttl_hours,
    )
    return len({f["attributes"].get("APN") for f in feats if f["attributes"].get("APN")})


def oracle_baselines(ttl_hours: float = 0.0) -> list[dict]:
    """Authoritative counts straight from the source layers.

    LADBS metrics use the qualifying-rebuild cohort (Bldg-New AND Rebuild) and
    are counted by DISTINCT APN to match parcel-level milestone semantics.
    """
    with provenance.source("oracle"):
        b: list[dict] = []

        destroyed = _count(BASE_LAYER, DESTROYED_WHERE, ttl_hours)
        b.append({"source": "LA County", "metric": "destroyed_parcels", "official": destroyed})

        b.append({"source": "LADBS", "metric": "parcels_qualifying_application",
                  "official": _distinct_apns(QUALIFYING_WHERE, ttl_hours)})
        b.append({"source": "LADBS", "metric": "parcels_qualifying_permit_issued",
                  "official": _distinct_apns(
                      f"{QUALIFYING_WHERE} AND ISSUE_DATE IS NOT NULL", ttl_hours)})
        b.append({"source": "LADBS", "metric": "parcels_qualifying_cofo",
                  "official": _distinct_apns(
                      f"{QUALIFYING_WHERE} AND COFO_DATE IS NOT NULL", ttl_hours)})

    last = provenance.latest_fetch("oracle")
    as_of = (last or datetime.now(timezone.utc).isoformat())[:10]
    for row in b:
        row["as_of"] = as_of
    return b


def reconcile(parcels: list[dict], baselines: list[dict]) -> list[dict]:
    """Attach our computed counts next to each official baseline and flag drift.

    `parcels` is the list of emitted GeoJSON-style property dicts carrying
    milestone booleans ('application_submitted', 'permit_issued',
    'cofo_issued') and 'jurisdiction'.
    """
    la = [p for p in parcels if p["jurisdiction"] == "LA"]
    ours = {
        "destroyed_parcels": len(parcels),
        "parcels_qualifying_application": sum(1 for p in la if p.get("application_submitted")),
        "parcels_qualifying_permit_issued": sum(1 for p in la if p.get("permit_issued")),
        "parcels_qualifying_cofo": sum(1 for p in la if p.get("cofo_issued")),
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
