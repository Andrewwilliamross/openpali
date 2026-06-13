"""Nightly spatial-core orchestration.

Architectural constraints enforced here:

- **The denominator.** Every run evaluates against the complete destroyed-parcel
  universe (5,877 APNs from the county base layer). A lot with no spatial data
  is written to the asset index as an explicit ``static_baseline`` row with its
  parcel polygon — it is never dropped from the indexed dataset.

- **Idempotency.** Batches are keyed by (partition, epoch-label, kind) so a
  re-run of the same night overwrites rather than duplicates; the asset index
  keeps the newest row per (APN, kind).

- **Fail-safes.** Every external dependency is wrapped: a schema change or
  timeout on one source degrades that source only. Previously stored assets
  are preserved (parquet partitions are append-only across epochs), affected
  rows are marked ``stale_cached``, and the anomaly is flagged in the run
  manifest (``store/meta.json``) for the operator.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from shapely.geometry import shape

from palisades.sources import fetch_destroyed_parcels

from .prisms import GroundZSampler, footprint_prism_batch, parcel_prism_batch
from .scene_client import SceneClient, extract_footprint_prior
from .schema import SpatialStore

DEFAULT_STORE = Path(__file__).resolve().parents[3] / "data" / "spatial"


@dataclass
class NightlyReport:
    universe: int = 0
    priors_existing: int = 0
    priors_extracted: int = 0
    priors_footprint_fallback: int = 0
    static_baseline: int = 0
    stale_cached: int = 0
    renderable_existing: int = 0
    renderable_extrusions: int = 0
    renderable_prisms: int = 0
    renderable_skipped: int = 0
    anomalies: list[dict] = field(default_factory=list)
    duration_s: float = 0.0

    def to_json(self) -> dict:
        return {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "universe": self.universe,
            "priors_existing": self.priors_existing,
            "priors_extracted": self.priors_extracted,
            "priors_footprint_fallback": self.priors_footprint_fallback,
            "static_baseline": self.static_baseline,
            "stale_cached": self.stale_cached,
            "renderable_existing": self.renderable_existing,
            "renderable_extrusions": self.renderable_extrusions,
            "renderable_prisms": self.renderable_prisms,
            "renderable_skipped": self.renderable_skipped,
            "anomalies": self.anomalies,
            "duration_s": round(self.duration_s, 1),
        }


def _flag(report: NightlyReport, source: str, error: Exception | str) -> None:
    report.anomalies.append({"source": source, "error": str(error)[:400]})


def run_nightly(*, store_root: Path = DEFAULT_STORE, limit: int | None = None,
                apns: list[str] | None = None, epoch_label: str | None = None,
                ) -> NightlyReport:
    """One idempotent pass: ensure every destroyed parcel has its best-available
    spatial state in the store. `limit` bounds how many *new* extractions are
    attempted per run (the LARIAC prior is static — the backlog drains across
    nights and then this becomes a cheap no-op verification pass)."""
    t0 = time.monotonic()
    report = NightlyReport()
    store = SpatialStore(root=store_root)
    epoch_label = epoch_label or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_epoch = time.time()

    # ---- 1. the denominator (county base layer; cached by the v1 fetch layer) ----
    try:
        universe = fetch_destroyed_parcels(ttl_hours=12.0)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        _flag(report, "county_base_layer", e)
        if store.assets_path.exists():
            # preserve the last valid state; tonight is a no-op with an anomaly
            report.duration_s = time.monotonic() - t0
            _write_meta(store, report)
            return report
        raise  # first ever run cannot proceed without the universe
    report.universe = len(universe)

    # ---- 2. scene-layer APN index (static snapshot; cached on disk) ----
    client = SceneClient()
    try:
        scene_index = client.build_apn_index()
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as e:
        _flag(report, "lariac_scene_index", e)
        scene_index = {}

    # ---- 3. per-parcel reconciliation against the full universe ----
    existing = {(a["apn"], a["kind"]): a for a in store.iter_assets()}
    todo = sorted(universe.keys()) if apns is None else [a for a in apns if a in universe]
    extracted = 0
    for apn in todo:
        parcel = universe[apn]
        prev = existing.get((apn, "lariac_prior"))
        # only LIVE/STALE assets count as done — static_baseline rows are the
        # backlog, and must be retried until real geometry lands
        if prev is not None and prev["status"] in ("live", "stale_cached"):
            report.priors_existing += 1
            continue
        if limit is not None and extracted >= limit:
            # not an anomaly — backlog continues tomorrow; lot stays baseline
            _index_baseline(store, apn, parcel, now_epoch)
            report.static_baseline += 1
            continue

        batch = None
        source = ""
        try:
            if apn in scene_index:
                batch = client.extract_parcel_prior(apn, scene_index[apn], t_epoch=now_epoch)
                source = "lariac_scene"
            if batch is None:
                batch = extract_footprint_prior(apn, t_epoch=now_epoch)
                source = "lariac_footprint_extrusion"
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as e:
            _flag(report, f"extract:{apn}", e)
            if prev is not None and prev["status"] in ("live", "stale_cached"):
                report.stale_cached += 1  # keep the previous asset, mark it
                store.index_asset(apn=apn, kind="lariac_prior", t_epoch=prev["t_epoch"],
                                  n_points=prev["n_points"], geometry_wkb=prev["geometry"],
                                  status="stale_cached", source=prev["source"],
                                  anomaly=str(e)[:200])
            else:
                _index_baseline(store, apn, parcel, now_epoch)
                report.static_baseline += 1
            continue

        if batch is None or len(batch) == 0:
            _index_baseline(store, apn, parcel, now_epoch)
            report.static_baseline += 1
            continue

        store.write_batch(batch, epoch_label=epoch_label)
        geom_wkb = shape(parcel.geometry).wkb if parcel.geometry else b""
        store.index_asset(apn=apn, kind="lariac_prior", t_epoch=now_epoch,
                          n_points=len(batch), geometry_wkb=geom_wkb,
                          status="live", source=source)
        existing[(apn, "lariac_prior")] = {"status": "live", "source": source,
                                           "t_epoch": now_epoch, "n_points": len(batch)}
        extracted += 1
        if source == "lariac_scene":
            report.priors_extracted += 1
        else:
            report.priors_footprint_fallback += 1

    # ---- 4. renderable placeholders (ROADMAP D2: every lot renders in 3D) ----
    # Scene-modelled parcels stream their real surfels; everything else gets a
    # labeled placeholder batch (kind="splats") so the web pyramid covers the
    # full 5,877-parcel universe. Tracked as its own asset kind so re-runs are
    # cheap no-ops and coverage.json can cite source + acquisition time.
    ground = _GroundSamplerLazy(store, report)
    for apn in todo:
        parcel = universe[apn]
        prior = existing.get((apn, "lariac_prior"))
        prior_source = (prior or {}).get("source", "none")
        if prior_source == "lariac_scene":
            continue  # real geometry already renderable
        rend = existing.get((apn, "renderable_splats"))
        if rend is not None and rend["status"] == "live":
            report.renderable_existing += 1
            continue
        try:
            batch = None
            source = ""
            if prior_source == "lariac_footprint_extrusion":
                batch = footprint_prism_batch(apn, t_epoch=now_epoch)
                source = "lariac_footprint_extrusion"
            if batch is None or len(batch) == 0:
                gz = None
                if parcel.lon and parcel.lat:
                    gz = ground.ground_z(parcel.lon, parcel.lat)
                if gz is not None and parcel.geometry:
                    batch = parcel_prism_batch(apn, parcel.geometry, gz,
                                               t_epoch=now_epoch)
                    source = "parcel_prism"
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as e:
            _flag(report, f"renderable:{apn}", e)
            report.renderable_skipped += 1
            continue
        if batch is None or len(batch) == 0:
            # no ground reference yet (e.g. first-ever run) — next run resolves
            report.renderable_skipped += 1
            continue
        store.write_batch(batch, epoch_label=epoch_label)
        geom_wkb = shape(parcel.geometry).wkb if parcel.geometry else b""
        store.index_asset(apn=apn, kind="renderable_splats", t_epoch=now_epoch,
                          n_points=len(batch), geometry_wkb=geom_wkb,
                          status="live", source=source)
        if source == "parcel_prism":
            report.renderable_prisms += 1
        else:
            report.renderable_extrusions += 1

    store.flush_assets()
    report.duration_s = time.monotonic() - t0
    _write_meta(store, report)
    return report


class _GroundSamplerLazy:
    """Builds the neighbour ground-height sampler on first use only.

    Reads the store's splat positions once (a few seconds for 10M rows) and
    only when at least one parcel-prism lot actually needs an elevation.
    """

    def __init__(self, store: SpatialStore, report: NightlyReport) -> None:
        self._store = store
        self._report = report
        self._sampler: GroundZSampler | None = None
        self._failed = False

    def ground_z(self, lon: float, lat: float) -> float | None:
        if self._failed:
            return None
        if self._sampler is None:
            try:
                batch = self._store.read(kind="splats")
                if batch is None or len(batch) == 0:
                    raise ValueError("store has no splats yet")
                self._sampler = GroundZSampler(batch.xyz_ecef)
            except (ValueError, OSError) as e:
                _flag(self._report, "ground_sampler", e)
                self._failed = True
                return None
        return self._sampler.ground_z(lon, lat)


def _index_baseline(store: SpatialStore, apn: str, parcel, now_epoch: float) -> None:
    """Explicit static-baseline row: the lot exists, has no spatial updates yet,
    and stays in the indexed dataset (constraint: never drop a lot)."""
    geom_wkb = shape(parcel.geometry).wkb if parcel.geometry else b""
    store.index_asset(apn=apn, kind="lariac_prior", t_epoch=now_epoch, n_points=0,
                      geometry_wkb=geom_wkb, status="static_baseline",
                      source="none")


def _write_meta(store: SpatialStore, report: NightlyReport) -> None:
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / "meta.json").write_text(json.dumps(report.to_json(), indent=1))
