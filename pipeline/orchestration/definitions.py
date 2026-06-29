"""OpenPali orchestration — the refresh pipeline as Dagster software-defined assets.

Replaces the manual `make refresh` (run.py + run_spatial.py + web_export) with one
lineage-tracked, retryable, observable asset graph. Per ADR 0001 the prime directive is
**wrap, don't rewrite**: every asset calls an existing pipeline function unchanged.

Asset graph
    parcels ─▶ scored_parcels ─▶ reconciliation ─▶ artifacts
                                     │ (asset_check: no >5% oracle drift)
    spatial_priors ─▶ web_tiles

Run
    cd pipeline
    uv run --group orchestration dagster dev -f orchestration/definitions.py      # UI + lineage
    uv run --group orchestration dagster asset materialize \
        -f orchestration/definitions.py --select "parcels,scored_parcels,reconciliation,artifacts"

Env
    OPENPALI_OFFLINE=1     rebuild from the on-disk cache only (ttl=inf); default is live (ttl=12h)
    OPENPALI_OUT_DIR=...   override artifact output dir (default: web/public/data, the real site data)
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from datetime import date, datetime, timezone
from typing import Literal, Optional

# Make the pipeline packages (palisades, core) importable regardless of cwd.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import dagster as dg
import pydantic

from core import runs
from core.spatial.runner import DEFAULT_STORE, run_nightly
from core.spatial.web_export import export_web_tiles
from palisades import emit, sources, validate
from palisades.score import score_all

OFFLINE = bool(os.environ.get("OPENPALI_OFFLINE"))
TTL = 1e9 if OFFLINE else 12.0
OUT_DIR = pathlib.Path(os.environ["OPENPALI_OUT_DIR"]) if os.environ.get("OPENPALI_OUT_DIR") else None  # None -> emit default

# Network-bound assets get a couple of retries; the underlying http layer already
# retries individual requests, this covers whole-source flakiness.
_NET_RETRY = dg.RetryPolicy(max_retries=2, delay=10)


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dg.asset(
    retry_policy=_NET_RETRY,
    description="Destroyed-parcel universe: geometry + jurisdiction + debris + permits, normalized to Parcel objects.",
)
def parcels(context) -> list:
    ps = sources.build_parcels(ttl_hours=TTL)
    if not ps:
        raise dg.Failure("no parcels returned — refusing to emit an empty universe")
    context.add_output_metadata({"count": len(ps), "ttl_hours": TTL, "offline": OFFLINE})
    return ps


@dg.asset(description="Rebuild score 0-100 + predicted completion (mutates Parcel objects in place).")
def scored_parcels(context, parcels: list) -> list:
    cohort = score_all(parcels, today=date.today())
    context.add_output_metadata({"cohort": dg.MetadataValue.json({str(k): v for k, v in cohort.items()})})
    return parcels


@dg.asset(
    retry_policy=_NET_RETRY,
    description="Reconcile our parcel-level counts against the live LADBS oracle (degrades gracefully if unreachable).",
)
def reconciliation(context, scored_parcels: list) -> list:
    prop_dicts = [{"apn": p.apn, "jurisdiction": p.jurisdiction, "stage": p.stage} for p in scored_parcels]
    try:
        baselines = validate.oracle_baselines()  # live-only; bypasses cache
    except Exception as e:  # noqa: BLE001 - validation must never block emit
        context.log.warning(f"oracle unavailable ({e}); reconciliation skipped")
        return []
    recon = validate.reconcile(prop_dicts, baselines)
    failing = [r["metric"] for r in recon if not r.get("ok", True)]
    # Durable, DuckDB-queryable record of every reconciliation (ADR 0001, Decision 4).
    runs.record("reconciliation", {"offline": OFFLINE, "n_metrics": len(recon),
                                    "n_failing": len(failing), "metrics": recon})
    if failing:
        runs.alert(f"oracle drift >5% on {failing}", context={"metrics": recon})
    context.add_output_metadata({"metrics": dg.MetadataValue.json(recon), "n_failing": len(failing)})
    return recon


@dg.asset_check(
    asset=reconciliation,
    description="Data-quality gate: warn if any official metric drifts >5% from our computed counts.",
)
def no_oracle_drift(reconciliation: list) -> dg.AssetCheckResult:
    failing = [r["metric"] for r in reconciliation if not r.get("ok", True)]
    return dg.AssetCheckResult(
        passed=(len(failing) == 0),
        severity=dg.AssetCheckSeverity.WARN,
        metadata={
            "failing_metrics": failing,
            "skipped_offline": len(reconciliation) == 0,
            "detail": dg.MetadataValue.json(reconciliation),
        },
    )


class _ParcelProps(pydantic.BaseModel):
    """Mirrors web/src/lib/types.ts ParcelProps — the pipeline↔web contract.

    extra='forbid' makes the check fail loudly if emit.py ever adds/renames a field
    without the frontend type being updated (the silent-drift class of bug). The full
    Pydantic→TS codegen is Phase 2; this is the cheap guard in the meantime.
    """

    model_config = pydantic.ConfigDict(extra="forbid")
    apn: str
    address: str
    neighborhood: str
    jurisdiction: Literal["LA", "COUNTY", "MALIBU"]
    struct: Literal["SFR", "MFR", "COM", "OTH"]
    stage: Literal[0, 1, 2, 3, 4, 5]
    stage_label: str
    score: float
    last_event: Optional[str]


@dg.asset_check(
    asset="artifacts",
    description="Contract gate: emitted parcels.geojson properties must match the web ParcelProps type.",
)
def parcels_contract() -> dg.AssetCheckResult:
    out = OUT_DIR or emit.OUT_DIR
    fc = json.loads((out / "parcels.geojson").read_text())
    violations: list[str] = []
    for feat in fc.get("features", []):
        try:
            _ParcelProps.model_validate(feat.get("properties", {}))
        except pydantic.ValidationError as e:
            violations.append(f"{feat.get('properties', {}).get('apn', '?')}: {e.errors()[0]['msg']}")
            if len(violations) >= 10:
                break
    return dg.AssetCheckResult(
        passed=(len(violations) == 0),
        severity=dg.AssetCheckSeverity.ERROR,
        metadata={"sample_violations": violations, "n_features": len(fc.get("features", []))},
    )


@dg.asset(description="Emit parcels.geojson / details.json / summary.json / meta.json for the web app.")
def artifacts(context, scored_parcels: list, reconciliation: list) -> dict:
    source_meta = [
        {"id": "county_base", "as_of": _today_iso(), "ok": True, "records": len(scored_parcels),
         "note": "LA County Parcels Debris Removal (destroyed)"},
        {"id": "ladbs_permits", "as_of": _today_iso(), "ok": True,
         "records": sum(len(p.permits) for p in scored_parcels), "note": "LADBS Palisades Recovery"},
    ]
    result = emit.emit_all(scored_parcels, baselines=reconciliation, source_meta=source_meta, out_dir=OUT_DIR)
    context.add_output_metadata({"features": result["features"], "totals": dg.MetadataValue.json(result["totals"])})
    return result


@dg.asset(description="Nightly spatial-core pass: LARIAC 3D priors -> H3-partitioned GeoParquet store (drains backlog).")
def spatial_priors(context) -> dict:
    report = run_nightly(store_root=DEFAULT_STORE).to_json()
    anomalies = report.get("anomalies", [])
    runs.record("spatial_nightly", {
        "universe": report["universe"], "priors_existing": report["priors_existing"],
        "priors_extracted": report["priors_extracted"], "n_anomalies": len(anomalies),
        "anomalies": anomalies, "duration_s": report.get("duration_s"),
    })
    if anomalies:
        runs.alert(f"{len(anomalies)} spatial anomalies this run", context={"anomalies": anomalies[:8]})
    context.add_output_metadata({
        "universe": report["universe"],
        "priors_existing": report["priors_existing"],
        "priors_extracted": report["priors_extracted"],
        "anomalies": len(anomalies),
    })
    return report


@dg.asset(description="Export the web-streamable splat pyramid (3D Tiles) from the spatial store.")
def web_tiles(context, spatial_priors: dict) -> None:
    result = export_web_tiles(DEFAULT_STORE)
    if isinstance(result, dict):
        context.add_output_metadata({k: v for k, v in result.items() if isinstance(v, (int, float, str))})


# 2D tracker fast path (no heavy spatial) — what the old `make data` did.
tracker_job = dg.define_asset_job(
    "tracker_refresh",
    selection=dg.AssetSelection.assets(parcels, scored_parcels, reconciliation, artifacts),
)
# Full nightly refresh incl. spatial backlog + tiles — what `make refresh` should do.
nightly_job = dg.define_asset_job("nightly_refresh", selection=dg.AssetSelection.all())

nightly_schedule = dg.ScheduleDefinition(
    job=nightly_job,
    cron_schedule="0 7 * * *",  # 07:00 UTC daily
    default_status=dg.DefaultScheduleStatus.STOPPED,  # opt-in; flip to RUNNING when deployed
)

defs = dg.Definitions(
    assets=[parcels, scored_parcels, reconciliation, artifacts, spatial_priors, web_tiles],
    asset_checks=[no_oracle_drift, parcels_contract],
    jobs=[tracker_job, nightly_job],
    schedules=[nightly_schedule],
)
