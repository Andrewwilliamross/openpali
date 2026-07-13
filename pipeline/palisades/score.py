"""DEPRECATED prototype rebuild score (0-100) + heuristic completion date.

This module is retired from the public product (TRUTH-001): it is not called
by the pipeline entrypoint, its outputs are never emitted, and no API, sort
order, map color/style, spatial presentation, or user-facing recovery claim
may depend on it. It survives only as characterization-tested reference code
until the censoring-aware analytics/ML platform fully replaces its cohort
math. Defects that forced retirement:

- medians computed only from parcels that advanced (ignores right-censoring);
- fixed arbitrary stage bands and unsourced priors;
- consumed stage labels contaminated by scheduled inspections, ancillary
  permits, and fabricated cleanup dates;
- no temporal split, calibration, interval coverage, or model versioning.

Historical description (Docs/initialbuild_docs/METHODOLOGY.md):
  1. stage band; 2. milestone/velocity position within band; 3. predicted
  completion from cohort-median transition times.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta

from .model import (
    INSPECTION_MILESTONES,
    KIND_STAGE,
    STAGE_BANDS,
    STAGE_LABELS,
    Parcel,
)

# Fallback priors (days) when the cohort has too few observed transitions.
# Rough LADBS fire-rebuild figures: plan check ~3-4 months, permit→first
# inspection ~2 months, construction ~14 months.
PRIOR_TRANSITION_DAYS = {2: 110, 3: 65, 4: 430}
MIN_SAMPLE = 15


def _stage_entry_dates(p: Parcel) -> dict[int, date]:
    """Earliest date each stage was entered."""
    entries: dict[int, date] = {}
    for e in p.sorted_events():
        s = KIND_STAGE.get(e.kind)
        if s is not None and s not in entries:
            entries[s] = e.date
    return entries


def _current_stage(p: Parcel) -> int:
    entries = _stage_entry_dates(p)
    return max(entries) if entries else 0


def cohort_transition_medians(parcels: list[Parcel]) -> dict[int, dict[str, float]]:
    """For each stage s in {2,3,4}: stats of observed days spent in s before
    advancing (from parcels that DID advance). Coarse (date-less) parcels are
    excluded so they don't corrupt the velocity medians."""
    durations: dict[int, list[float]] = {2: [], 3: [], 4: []}
    for p in parcels:
        if p.coarse:
            continue
        entries = _stage_entry_dates(p)
        for s in (2, 3, 4):
            if s in entries:
                nxt = [d for st, d in entries.items() if st > s]
                if nxt:
                    dur = (min(nxt) - entries[s]).days
                    if 0 <= dur < 2000:
                        durations[s].append(dur)
    out: dict[int, dict[str, float]] = {}
    for s, vals in durations.items():
        if len(vals) >= MIN_SAMPLE:
            vals.sort()
            out[s] = {
                "median": statistics.median(vals),
                "p25": vals[max(0, int(len(vals) * 0.25) - 1)],
                "n": len(vals),
            }
        else:
            out[s] = {"median": PRIOR_TRANSITION_DAYS[s], "p25": PRIOR_TRANSITION_DAYS[s] * 0.5, "n": len(vals)}
    return out


def _milestone_progress(p: Parcel) -> tuple[float, str | None]:
    """Stage-4 position from the furthest inspection milestone reached."""
    best = 0.10
    best_name = None
    reached = {e.milestone for e in p.events if e.kind == "inspection" and e.milestone}
    for name, frac in INSPECTION_MILESTONES:
        if name in reached:
            best = frac
            best_name = name
    return best, best_name


def _remaining_to_complete(stage: int, days_in: int, cohort: dict[int, dict[str, float]]) -> float:
    remaining = 0.0
    for s in range(max(stage, 2), 5):
        st = cohort.get(s, {"median": PRIOR_TRANSITION_DAYS[s], "p25": PRIOR_TRANSITION_DAYS[s] * 0.5})
        if s == stage:
            remaining += max(st["median"] - days_in, st["p25"] * 0.5)
        else:
            remaining += st["median"]
    return remaining


def score_parcel(p: Parcel, cohort: dict[int, dict[str, float]], today: date) -> None:
    """Mutates p: stage, score, est_completion, score_explain."""
    # Coarse parcels (Malibu markers, county REBUILD_PROGRESS) carry a stage but no
    # dated timeline — score at mid-band, no velocity adjustment, conservative ETA.
    if p.coarse and p.coarse_stage is not None:
        stage = p.coarse_stage
        p.stage = stage
        lo, hi = STAGE_BANDS[stage]
        p.score = round((lo + hi) / 2, 1) if stage not in (0, 5) else float(lo)
        if stage in (0, 5):
            p.est_completion = None
        else:
            p.est_completion = _humanize_eta(today + timedelta(days=_remaining_to_complete(stage, 0, cohort)))
        p.score_explain = (
            f"Status from the {p.jurisdiction_label()} rebuild dashboard "
            f"({STAGE_LABELS[stage]}); detailed permit timeline not published for this jurisdiction."
        )
        return

    entries = _stage_entry_dates(p)
    stage = _current_stage(p)
    p.stage = stage
    lo, hi = STAGE_BANDS[stage]

    if stage == 5:
        p.score = 100.0
        p.est_completion = None
        p.score_explain = "Rebuild complete — certificate of occupancy issued."
        return
    if stage == 0:
        p.score = 2.0
        p.est_completion = None
        p.score_explain = "No rebuild application on file for this lot."
        return

    entered = entries[stage]
    days_in = (today - entered).days
    last = p.last_event_date() or entered
    days_quiet = (today - last).days

    # --- position within band ---
    if stage == 4:
        pos, milestone = _milestone_progress(p)
    else:
        pos, milestone = 0.5, None

    stats = cohort.get(stage)
    typical = stats["median"] if stats else PRIOR_TRANSITION_DAYS.get(stage, 120)
    if stage in (2, 3, 4):
        ratio = days_quiet / max(typical, 1)
        if ratio > 1.5:  # visibly stalled
            pos -= min(0.35, 0.15 * ratio)
        elif days_quiet <= 30:  # recent movement
            pos += 0.15
    pos = max(0.05, min(0.95, pos))
    p.score = round(lo + pos * (hi - lo), 1)

    # --- predicted completion ---
    remaining = _remaining_to_complete(stage, days_in, cohort)
    if stage == 1:
        remaining += cohort.get(2, {"median": PRIOR_TRANSITION_DAYS[2]})["median"] * 0.3  # time to file
    eta = today + timedelta(days=remaining)
    p.est_completion = _humanize_eta(eta)

    # --- explanation ---
    label = STAGE_LABELS[stage].lower()
    months_in = max(1, round(days_in / 30.4))
    typical_m = max(1, round(typical / 30.4))
    if stage == 4 and milestone:
        nice = milestone.replace("_", "/")
        p.score_explain = (
            f"Under construction — {nice} milestone reached. "
            f"{'Active recently.' if days_quiet <= 45 else f'No inspection in {round(days_quiet / 30.4)} months.'}"
        )
    elif stage in (2, 3):
        speed = (
            "moving faster than typical"
            if days_in < typical * 0.75
            else ("slower than typical" if days_quiet > typical * 1.5 else "tracking the typical pace")
        )
        p.score_explain = (
            f"In {label} for {months_in} month{'s' if months_in != 1 else ''}; "
            f"cohort typically advances in about {typical_m} months — {speed}."
        )
    else:
        p.score_explain = "Lot cleared of debris; no permit application on file yet."


def _humanize_eta(d: date) -> str:
    m = d.month
    part = "Early" if m <= 4 else ("Mid" if m <= 8 else "Late")
    return f"{part} {d.year}"


def score_all(parcels: list[Parcel], today: date | None = None) -> dict[int, dict[str, float]]:
    """Score every parcel in place; returns the cohort stats used (for meta/debug)."""
    today = today or date.today()
    cohort = cohort_transition_medians(parcels)
    for p in parcels:
        score_parcel(p, cohort, today)
    return cohort
