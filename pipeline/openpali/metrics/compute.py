"""Metric computation + independent reconciliation for one snapshot.

Values land in ``analytics.metric_value``; reconciliations in
``analytics.reconciliation_result``. Recomputation for the same snapshot is
idempotent (upsert by snapshot/metric/version/cohort).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from openpali.metrics.catalog import (
    CATALOG_VERSION,
    FLOW_WINDOW_DAYS,
    KM_MIN_SAMPLE,
    SPECS,
)
from openpali.storage.models import (
    AcquisitionRun,
    CivicSnapshot,
    MetricDefinition,
    MetricValue,
    ReconciliationResult,
    RecoveryObservationRow,
    SnapshotMember,
    SnapshotPropertyState,
    SourceRecordVersion,
)


def _ensure_definitions(session: Session) -> None:
    for spec in SPECS:
        session.execute(
            pg_insert(MetricDefinition)
            .values(**spec.row())
            .on_conflict_do_nothing(index_elements=["metric_id", "version"])
        )


def _put_value(
    session: Session,
    snapshot_id: str,
    metric_id: str,
    cohort: dict,
    *,
    value: float | None,
    sample_size: int | None = None,
    interval: tuple[float | None, float | None] = (None, None),
    missing_count: int | None = None,
    status: str = "computed",
    computation: dict | None = None,
) -> None:
    cohort_key = ",".join(f"{k}={v}" for k, v in sorted(cohort.items())) or "all"
    statement = (
        pg_insert(MetricValue)
        .values(
            snapshot_id=snapshot_id,
            metric_id=metric_id,
            version=CATALOG_VERSION,
            cohort=cohort,
            cohort_key=cohort_key,
            value=value,
            interval_low=interval[0],
            interval_high=interval[1],
            sample_size=sample_size,
            missing_count=missing_count,
            status=status,
            computation=computation or {},
        )
        .on_conflict_do_update(
            index_elements=["snapshot_id", "metric_id", "version", "cohort_key"],
            set_={
                "value": value,
                "interval_low": interval[0],
                "interval_high": interval[1],
                "sample_size": sample_size,
                "missing_count": missing_count,
                "status": status,
                "computation": computation or {},
            },
        )
    )
    session.execute(statement)


def _member_observations(session: Session, snapshot_id: str) -> list[RecoveryObservationRow]:
    member_ids = select(SnapshotMember.member_id).where(
        SnapshotMember.snapshot_id == snapshot_id,
        SnapshotMember.member_type == "observation",
    )
    return list(
        session.execute(
            select(RecoveryObservationRow).where(
                RecoveryObservationRow.observation_id.in_(member_ids)
            )
        ).scalars()
    )


def _application_table(
    observations: list[RecoveryObservationRow],
) -> dict[str, dict]:
    """Per qualifying-application submission/issuance dates (permit subjects)."""

    applications: dict[str, dict] = defaultdict(dict)
    for row in observations:
        if row.subject_type != "permit_application":
            continue
        if row.event_type == "rebuild_application_submitted":
            entry = applications[row.subject_id]
            entry["submitted_kind"] = row.occurred_kind
            if row.occurred_kind == "exact":
                entry["submitted"] = row.occurred_earliest
        elif row.event_type == "rebuild_permit_issued":
            entry = applications[row.subject_id]
            entry["issued_kind"] = row.occurred_kind
            if row.occurred_kind == "exact":
                entry["issued"] = row.occurred_earliest
    return dict(applications)


def compute_all(session: Session, snapshot_id: str) -> dict:
    _ensure_definitions(session)
    snapshot = session.execute(
        select(CivicSnapshot).where(CivicSnapshot.snapshot_id == snapshot_id)
    ).scalar_one()
    cutoff_date: date = snapshot.cutoff.date()

    states = list(
        session.execute(
            select(SnapshotPropertyState).where(
                SnapshotPropertyState.snapshot_id == snapshot_id
            )
        ).scalars()
    )
    observations = _member_observations(session, snapshot_id)

    summary: dict = {"snapshot_id": snapshot_id, "metrics": 0, "reconciliations": 0}

    # --- 1. universe ---------------------------------------------------------
    _put_value(session, snapshot_id, "universe_destroyed_parcels", {},
               value=float(len(states)), sample_size=len(states))
    summary["metrics"] += 1

    # --- 2. lane signal prevalence ------------------------------------------
    jurisdictions = ["all"] + sorted({s.jurisdiction for s in states if s.jurisdiction})
    for jurisdiction in jurisdictions:
        cohort_states = states if jurisdiction == "all" else [
            s for s in states if s.jurisdiction == jurisdiction
        ]
        lane_counts: Counter = Counter()
        for state in cohort_states:
            for lane_key, signal in state.lane_signals.items():
                lane_counts[(lane_key, signal)] += 1
        for (lane_key, signal), count in sorted(lane_counts.items()):
            _put_value(
                session, snapshot_id, "lane_signal_prevalence",
                {"jurisdiction": jurisdiction, "lane": lane_key, "signal": signal},
                value=float(count), sample_size=len(cohort_states),
            )
            summary["metrics"] += 1

    # --- 3. milestone prevalence ---------------------------------------------
    milestone_keys = (
        "cleanup_complete", "application_submitted", "plan_check_approved",
        "permit_issued", "construction_evidence", "cofo_issued",
    )
    for jurisdiction in jurisdictions:
        cohort_states = states if jurisdiction == "all" else [
            s for s in states if s.jurisdiction == jurisdiction
        ]
        for key in milestone_keys:
            count = sum(1 for s in cohort_states if s.milestones.get(key))
            _put_value(
                session, snapshot_id, "milestone_prevalence",
                {"jurisdiction": jurisdiction, "milestone": key},
                value=float(count), sample_size=len(cohort_states),
            )
            summary["metrics"] += 1

    # --- 4. weekly transition incidence --------------------------------------
    applications = _application_table(observations)
    weekly_submitted: Counter = Counter()
    weekly_issued: Counter = Counter()
    undated_submissions = undated_issuances = 0
    for entry in applications.values():
        submitted = entry.get("submitted")
        if submitted is not None:
            weekly_submitted[(submitted - timedelta(days=submitted.weekday())).isoformat()] += 1
        elif "submitted_kind" in entry:
            undated_submissions += 1
        issued = entry.get("issued")
        if issued is not None:
            weekly_issued[(issued - timedelta(days=issued.weekday())).isoformat()] += 1
        elif "issued_kind" in entry:
            undated_issuances += 1
    for week, count in sorted(weekly_submitted.items()):
        _put_value(session, snapshot_id, "weekly_transition_incidence",
                   {"event": "application_submitted", "week": week},
                   value=float(count), missing_count=undated_submissions)
        summary["metrics"] += 1
    for week, count in sorted(weekly_issued.items()):
        _put_value(session, snapshot_id, "weekly_transition_incidence",
                   {"event": "permit_issued", "week": week},
                   value=float(count), missing_count=undated_issuances)
        summary["metrics"] += 1

    # --- 5. censoring-aware time to issuance ---------------------------------
    km_summary = _kaplan_meier_issuance(
        session, snapshot_id, applications, cutoff_date
    )
    summary["metrics"] += km_summary["values_written"]
    summary["time_to_issuance"] = {
        k: v for k, v in km_summary.items() if k != "values_written"
    }

    # --- 6. backlog / inflow / outflow ---------------------------------------
    window_start = cutoff_date - timedelta(days=FLOW_WINDOW_DAYS)
    backlog = sum(
        1 for e in applications.values()
        if "submitted_kind" in e and "issued_kind" not in e
    )
    inflow = sum(
        1 for e in applications.values()
        if e.get("submitted") and window_start < e["submitted"] <= cutoff_date
    )
    outflow = sum(
        1 for e in applications.values()
        if e.get("issued") and window_start < e["issued"] <= cutoff_date
    )
    flows = {
        "backlog": backlog,
        "inflow": inflow,
        "outflow": outflow,
        "net_flow": inflow - outflow,
        "throughput_per_day": outflow / FLOW_WINDOW_DAYS,
    }
    for name, value in flows.items():
        _put_value(session, snapshot_id, "permitting_backlog_flow",
                   {"measure": name}, value=float(value),
                   sample_size=len(applications))
        summary["metrics"] += 1
    summary["permitting_flow"] = flows

    # --- 7. missingness --------------------------------------------------------
    occurrence_kinds: dict[str, Counter] = defaultdict(Counter)
    for row in observations:
        occurrence_kinds[row.event_type][row.occurred_kind] += 1
    for event_type, kinds in sorted(occurrence_kinds.items()):
        total = sum(kinds.values())
        for kind, count in sorted(kinds.items()):
            _put_value(
                session, snapshot_id, "evidence_missingness",
                {"event_type": event_type, "occurred_kind": kind},
                value=float(count), sample_size=total,
            )
            summary["metrics"] += 1
    dins_stats = _dins_join_stats(session, snapshot.input_runs)
    if dins_stats:
        for name, value in dins_stats.items():
            if isinstance(value, (int, float)):
                _put_value(session, snapshot_id, "evidence_missingness",
                           {"event_type": "dins_join", "occurred_kind": name},
                           value=float(value))
                summary["metrics"] += 1

    # --- independent reconciliation -------------------------------------------
    summary["reconciliations"] = _reconcile(
        session, snapshot_id, snapshot, states, applications
    )
    session.flush()
    return summary


def _kaplan_meier_issuance(
    session: Session,
    snapshot_id: str,
    applications: dict[str, dict],
    cutoff_date: date,
) -> dict:
    durations: list[int] = []
    events: list[int] = []
    excluded_missing_submission = 0
    for entry in applications.values():
        submitted = entry.get("submitted")
        if submitted is None:
            if "submitted_kind" in entry:
                excluded_missing_submission += 1
            continue
        issued = entry.get("issued")
        if issued is not None and issued >= submitted:
            durations.append((issued - submitted).days)
            events.append(1)
        else:
            durations.append(max((cutoff_date - submitted).days, 0))
            events.append(0)

    result: dict = {
        "n": len(durations),
        "events": int(sum(events)),
        "excluded_missing_submission": excluded_missing_submission,
        "values_written": 0,
    }
    if len(durations) < KM_MIN_SAMPLE:
        _put_value(session, snapshot_id, "time_to_issuance_km", {"estimate": "median_days"},
                   value=None, sample_size=len(durations),
                   missing_count=excluded_missing_submission, status="suppressed_small_sample")
        result["values_written"] = 1
        result["status"] = "suppressed_small_sample"
        return result

    from lifelines import KaplanMeierFitter

    km = KaplanMeierFitter()
    km.fit(durations, events)
    median = km.median_survival_time_
    median_value = None if median == float("inf") else float(median)
    try:
        p_issued_180 = float(1.0 - km.predict(180))
    except Exception:  # noqa: BLE001 - beyond follow-up
        p_issued_180 = None
    from lifelines.utils import median_survival_times

    try:
        ci = median_survival_times(km.confidence_interval_)
        ci_low = float(ci.iloc[0, 0]) if median_value is not None else None
        ci_high = float(ci.iloc[0, 1]) if median_value is not None else None
        if ci_low is not None and ci_low == float("inf"):
            ci_low = None
        if ci_high is not None and ci_high == float("inf"):
            ci_high = None
    except Exception:  # noqa: BLE001
        ci_low = ci_high = None

    _put_value(
        session, snapshot_id, "time_to_issuance_km", {"estimate": "median_days"},
        value=median_value, sample_size=len(durations),
        interval=(ci_low, ci_high),
        missing_count=excluded_missing_submission,
        status="computed" if median_value is not None else "median_not_estimable",
        computation={"events": int(sum(events)), "censored": int(len(events) - sum(events))},
    )
    _put_value(
        session, snapshot_id, "time_to_issuance_km", {"estimate": "p_issued_180d"},
        value=p_issued_180, sample_size=len(durations),
        missing_count=excluded_missing_submission,
        status="computed" if p_issued_180 is not None else "beyond_follow_up",
    )
    result.update(
        median_days=median_value, p_issued_180d=p_issued_180, values_written=2,
        status="computed",
    )
    return result


def _dins_join_stats(session: Session, input_runs: list[str]) -> dict | None:
    for run_id in input_runs:
        run = session.execute(
            select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
        ).scalar_one_or_none()
        if run is not None and run.source_id == "calfire_dins":
            return (run.health or {}).get("load", {}).get("join_stats")
    return None


def _reconcile(
    session: Session,
    snapshot_id: str,
    snapshot: CivicSnapshot,
    states: list[SnapshotPropertyState],
    applications: dict[str, dict],
) -> int:
    """Independent reconciliations with PREDECLARED tolerances."""

    written = 0

    def put(metric_id: str, reference_source: str, reference_definition: str,
            reference_value: float | None, our_value: float | None,
            tolerance_pct: float, samples: list | None = None) -> None:
        nonlocal written
        drift = None
        verdict = "unavailable"
        if reference_value not in (None, 0) and our_value is not None:
            drift = round(abs(our_value - reference_value) / reference_value * 100, 2)
            verdict = "pass" if drift <= tolerance_pct else "fail"
        session.execute(
            pg_insert(ReconciliationResult).values(
                snapshot_id=snapshot_id,
                metric_id=metric_id,
                reference_source=reference_source,
                reference_definition=reference_definition,
                reference_value=reference_value,
                our_value=our_value,
                tolerance_pct=tolerance_pct,
                drift_pct=drift,
                verdict=verdict,
                samples=samples or [],
            )
        )
        written += 1

    # (a) universe vs the county server-side count captured at acquisition
    server_count = None
    for run_id in snapshot.input_runs:
        run = session.execute(
            select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
        ).scalar_one_or_none()
        if run is not None and run.source_id == "county_base":
            server_count = (run.health or {}).get("count_before")
    put(
        "universe_destroyed_parcels",
        "county_base server-side count",
        "returnCountOnly under the identical destroyed-universe filter, captured during acquisition",
        float(server_count) if server_count else None,
        float(len(states)),
        tolerance_pct=0.5,
    )

    # (b) our issued qualifying permits present in the INDEPENDENT Socrata portal
    issued_permits = sorted(
        pid for pid, e in applications.items() if e.get("issued") is not None
    )
    if issued_permits:
        socrata_rows = set(
            session.execute(
                select(SourceRecordVersion.native_key).where(
                    SourceRecordVersion.source_id == "socrata_permits",
                    SourceRecordVersion.native_key.in_(issued_permits),
                )
            ).scalars()
        )
        presence = len(socrata_rows) / len(issued_permits) * 100
        put(
            "milestone_prevalence.permit_issued",
            "socrata gwh9-jnip (independent portal)",
            "fraction of our issued qualifying permit numbers present in the Socrata "
            "permit dataset (predeclared floor 90%; portal refreshes weekly)",
            100.0,
            presence,
            tolerance_pct=10.0,
            samples=issued_permits[:10],
        )

    # (c) CofO count vs the CC0 Socrata CofO dataset joined by permit number
    our_cofo_permits = sorted(
        row.subject_id
        for row in _member_observations(session, snapshot_id)
        if row.event_type == "certificate_of_occupancy_issued"
        and row.subject_type == "permit_application"
    )
    if our_cofo_permits:
        cofo_rows = list(
            session.execute(
                select(SourceRecordVersion.payload).where(
                    SourceRecordVersion.source_id == "socrata_cofo",
                )
            ).scalars()
        )
        socrata_permit_numbers = {
            str(r.get("pcis_permit") or "").strip() for r in cofo_rows
        }
        matched = [p for p in our_cofo_permits if p in socrata_permit_numbers]
        presence = len(matched) / len(our_cofo_permits) * 100
        put(
            "milestone_prevalence.cofo_issued",
            "socrata 3f9m-afei (CC0 CofO dataset)",
            "fraction of our CofO permit numbers present in the independent CofO dataset "
            "(predeclared tolerance 30%: dataset refresh lags ~1-2 months)",
            100.0,
            presence,
            tolerance_pct=30.0,
            samples=our_cofo_permits[:10],
        )
    return written
