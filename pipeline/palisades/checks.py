"""Expectation gates — the pipeline refuses to publish artifacts that fail them.

Severity model:
  error — block emit entirely; the previously published artifacts stay in place
  warn  — publish, but record the incident in meta.json for the UI/operators
  info  — publish + record; expected operational notes (counts moved, etc.)

These are the audit's "data contract" checks implemented in-pipeline (per
ROADMAP.md D4): no orchestration platform, just enforced invariants.
"""

from __future__ import annotations

from typing import Any

from .model import STAGE_LABELS, Parcel

ERROR, WARN, INFO = "error", "warn", "info"

APN_PARSE_RATE_MAX = 0.01   # >1% unparseable APNs in a source is a wiring break
DUPLICATE_RATE_MAX = 0.02   # >2% duplicate APN rows suggests join-key breakage
UNIVERSE_DROP_MAX = 0.05    # universe shrank >5% vs published artifact


def _inc(level: str, code: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message}


def run_gates(
    parcels: list[Parcel],
    source_health: list[dict[str, Any]],
    reconciliation: list[dict[str, Any]],
    prev_summary: dict[str, Any] | None = None,
    prev_meta: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    incidents: list[dict[str, str]] = []
    health = {h["id"]: h for h in source_health}

    if not parcels:
        incidents.append(_inc(ERROR, "universe_empty",
                              "0 destroyed parcels built — refusing to publish"))
        return incidents

    # --- universe source integrity (county_base defines the denominator) ---
    cb = health.get("county_base", {})
    rows = cb.get("records") or 0
    if rows:
        bad = cb.get("unparseable", 0)
        if bad / rows > APN_PARSE_RATE_MAX:
            incidents.append(_inc(ERROR, "apn_parse_rate",
                                  f"county_base: {bad}/{rows} rows have unparseable APNs"))
        dup = cb.get("duplicates", 0)
        if dup / rows > DUPLICATE_RATE_MAX:
            incidents.append(_inc(ERROR, "duplicate_apns",
                                  f"county_base: {dup}/{rows} duplicate APN rows"))
        elif dup:
            incidents.append(_inc(INFO, "duplicate_apns",
                                  f"county_base: {dup} duplicate APN rows deduped (first kept)"))
        ng = cb.get("no_geometry", 0)
        if ng:
            incidents.append(_inc(WARN, "missing_geometry",
                                  f"county_base: {ng} destroyed parcels dropped for missing geometry"))

    lp = health.get("ladbs_permits", {})
    lrows = lp.get("records") or 0
    if lrows and (lp.get("unparseable", 0) / lrows) > APN_PARSE_RATE_MAX:
        incidents.append(_inc(WARN, "apn_parse_rate",
                              f"ladbs_permits: {lp['unparseable']}/{lrows} rows have unparseable APNs"))

    # --- source availability ---
    for h in source_health:
        if not h.get("ok", False):
            detail = h.get("error") or "no data fetched"
            incidents.append(_inc(WARN, "source_failed", f"{h['id']}: {detail}"))

    # --- status taxonomy ---
    bad_stages = sorted({p.stage for p in parcels} - set(STAGE_LABELS))
    if bad_stages:
        incidents.append(_inc(ERROR, "stage_taxonomy",
                              f"parcels carry undefined stages: {bad_stages}"))
    for h in source_health:
        labels = h.get("unknown_labels") or []
        if labels:
            incidents.append(_inc(WARN, "label_taxonomy",
                                  f"{h['id']}: unrecognized status labels {labels} — "
                                  f"affected parcels may be under-staged"))

    # --- universe delta vs the previously published artifact ---
    prev = ((prev_summary or {}).get("totals") or {}).get("destroyed")
    if prev:
        cur = len(parcels)
        if cur < prev * (1 - UNIVERSE_DROP_MAX):
            incidents.append(_inc(ERROR, "universe_shrank",
                                  f"destroyed universe fell {prev} → {cur} (>{UNIVERSE_DROP_MAX:.0%}); "
                                  f"likely upstream filter/schema breakage"))
        elif cur != prev:
            incidents.append(_inc(INFO, "universe_changed",
                                  f"destroyed universe {prev} → {cur}"))

    # --- reconciliation against official numbers ---
    if not reconciliation:
        incidents.append(_inc(WARN, "reconciliation_unavailable",
                              "no official baselines this run — summary.baselines will be empty"))
    else:
        for r in reconciliation:
            if not r.get("ok", True):
                incidents.append(_inc(WARN, "official_drift",
                                      f"{r['metric']}: official={r['official']} ours={r['ours']} "
                                      f"drift={r['drift_pct']}% (>5% — METHODOLOGY.md notice applies)"))

    # --- schema drift vs the previously published meta ---
    prev_sources = {s.get("id"): s for s in (prev_meta or {}).get("sources", [])}
    for h in source_health:
        ps = prev_sources.get(h["id"]) or {}
        old_fp, new_fp = ps.get("schema_fingerprint"), h.get("schema_fingerprint")
        if old_fp and new_fp and old_fp != new_fp:
            incidents.append(_inc(WARN, "schema_drift",
                                  f"{h['id']}: schema fingerprint {old_fp} → {new_fp}"))

    return incidents


def has_errors(incidents: list[dict[str, str]]) -> bool:
    return any(i["level"] == ERROR for i in incidents)
