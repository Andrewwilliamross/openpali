"""Champion registry: predeclared gates + append-only manual promotion (ML-003)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from openpali.storage.models import (
    DatasetVersion,
    ExperimentRun,
    ModelVersion,
    PromotionDecision,
)

#: PREDECLARED promotion gates (frozen before any final evaluation):
#: (1) both runs are evaluated on the untouched final holdout — a fold-based
#:     dev metric can NEVER support promotion; (2) the challenger beats the
#:     censoring-aware KM baseline on IPCW Brier at 180 days; (3) decile
#:     calibration error not >20% worse (missing calibration FAILS CLOSED);
#:     (4) no submission-month cohort with n>=30 regresses >20% vs KM;
#:     (5) the dataset's leakage audit exists and its precommitted
#:     point-in-time-history gate passed; (6) a named independent reviewer
#:     approves. No automatic promotion exists.
GATES = {
    "final_holdout_only": "challenger AND KM comparator evaluated on final_holdout",
    "beats_km_ipcw_brier_180": "challenger ipcw_brier_180 < km ipcw_brier_180",
    "calibration_not_worse_20pct": "challenger calibration_abs_error <= 1.2 * km (fail closed on missing)",
    "no_cohort_regression": "no cohort with n>=30 has challenger brier > 1.2 * km brier",
    "dataset_contracts": "dataset leakage audit present and history gate passed",
    "independent_review": "a named reviewer other than the proposing process approves",
}

MIN_COHORT_N_FOR_GATE = 30
_FORBIDDEN_REVIEWERS = {"", "system", "openpali", "pipeline", "auto", "unknown"}


def evaluate_gates(session: Session, challenger_run_id: str) -> dict:
    challenger = session.execute(
        select(ExperimentRun).where(ExperimentRun.experiment_run_id == challenger_run_id)
    ).scalar_one()
    results: dict = {"gates": dict(GATES), "checks": {}}
    checks = results["checks"]

    def fail(name: str, detail: str) -> None:
        checks[name] = f"FAIL: {detail}"

    def ok(name: str, detail: str) -> None:
        checks[name] = f"PASS: {detail}"

    # gate 1: final holdout only — for the challenger AND the KM comparator
    challenger_split = (challenger.config or {}).get("eval_split")
    if challenger_split != "final_holdout":
        fail("final_holdout_only",
             f"challenger evaluated on '{challenger_split}', not final_holdout")
    km = None
    for candidate in session.execute(
        select(ExperimentRun).where(
            ExperimentRun.dataset_id == challenger.dataset_id,
            ExperimentRun.model_family == "baseline-km",
        ).order_by(ExperimentRun.created_at.desc())
    ).scalars():
        if (candidate.config or {}).get("eval_split") == "final_holdout":
            km = candidate
            break
    if km is None:
        fail("beats_km_ipcw_brier_180", "no KM baseline run on final_holdout")
        results["passed"] = False
        return results
    if challenger_split == "final_holdout":
        ok("final_holdout_only", "both runs evaluated on final_holdout")

    # gate 2: IPCW Brier
    challenger_brier = challenger.metrics.get("ipcw_brier_180")
    km_brier = km.metrics.get("ipcw_brier_180")
    if challenger_brier is not None and km_brier is not None and challenger_brier < km_brier:
        ok("beats_km_ipcw_brier_180", f"challenger={challenger_brier} km={km_brier}")
    else:
        fail("beats_km_ipcw_brier_180", f"challenger={challenger_brier} km={km_brier}")

    # gate 3: calibration — FAIL CLOSED on missing values
    challenger_cal = challenger.metrics.get("calibration_abs_error")
    km_cal = km.metrics.get("calibration_abs_error")
    if challenger_cal is None or km_cal is None:
        fail("calibration_not_worse_20pct",
             f"missing calibration (challenger={challenger_cal} km={km_cal})")
    elif challenger_cal <= 1.2 * max(km_cal, 1e-9):
        ok("calibration_not_worse_20pct", f"challenger={challenger_cal} km={km_cal}")
    else:
        fail("calibration_not_worse_20pct", f"challenger={challenger_cal} km={km_cal}")

    # gate 4: cohort regressions (persisted per-run cohort metrics)
    challenger_cohorts = challenger.metrics.get("cohorts") or {}
    km_cohorts = km.metrics.get("cohorts") or {}
    regressions: list[str] = []
    considered = 0
    for name, entry in challenger_cohorts.items():
        if (entry.get("n") or 0) < MIN_COHORT_N_FOR_GATE:
            continue
        km_entry = km_cohorts.get(name) or {}
        c_brier = entry.get("ipcw_brier_180")
        k_brier = km_entry.get("ipcw_brier_180")
        if c_brier is None or k_brier is None:
            regressions.append(f"{name}: missing brier (fail closed)")
            continue
        considered += 1
        if c_brier > 1.2 * max(k_brier, 1e-9):
            regressions.append(f"{name}: challenger={c_brier} km={k_brier}")
    if regressions:
        fail("no_cohort_regression", "; ".join(regressions))
    else:
        ok("no_cohort_regression",
           f"{considered} cohorts with n>={MIN_COHORT_N_FOR_GATE} checked, none regressed")

    # gate 5: dataset contracts — actually read the dataset row
    dataset = session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == challenger.dataset_id)
    ).scalar_one_or_none()
    if dataset is None:
        fail("dataset_contracts", "dataset row missing")
    elif not dataset.leakage_audit:
        fail("dataset_contracts", "no leakage audit recorded")
    elif not (dataset.sufficiency or {}).get("gate", {}).get("passed"):
        fail("dataset_contracts", "precommitted history gate did not pass")
    else:
        ok("dataset_contracts", "leakage audit present; history gate passed")

    results["passed"] = all(str(v).startswith("PASS") for v in checks.values())
    return results


def record_promotion(
    session: Session,
    *,
    model_id: str,
    reviewer: str,
    decision: str,
    reason: str,
) -> PromotionDecision:
    """Append a manual promotion decision. Champion state lives ONLY in this
    append-only history; changing it never rewrites an existing release."""

    if reviewer.strip().lower() in _FORBIDDEN_REVIEWERS or len(reviewer.strip()) < 3:
        raise ValueError(
            f"independent_review gate: '{reviewer}' is not an acceptable named reviewer"
        )
    model = session.execute(
        select(ModelVersion).where(ModelVersion.model_id == model_id)
    ).scalar_one()
    gates = evaluate_gates(session, model.experiment_run_id)
    if decision == "promoted" and not gates.get("passed"):
        raise ValueError(
            f"predeclared gates failed; promotion refused: {gates['checks']}"
        )
    previous = session.execute(
        select(PromotionDecision)
        .where(PromotionDecision.decision == "promoted")
        .order_by(PromotionDecision.decided_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    experiment = session.execute(
        select(ExperimentRun).where(
            ExperimentRun.experiment_run_id == model.experiment_run_id
        )
    ).scalar_one()
    linkage = hashlib.sha256(
        f"{model.model_id}:{model.artifact_sha256}:{experiment.mlflow_run_id}".encode()
    ).hexdigest()
    row = PromotionDecision(
        decision_id="dec-" + hashlib.sha256(
            f"{model_id}:{reviewer}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:20],
        previous_champion_model_id=previous.proposed_model_id if previous else None,
        proposed_model_id=model_id,
        gates=gates["gates"],
        gate_metrics=gates["checks"],
        reviewer=reviewer,
        decision=decision,
        reason=reason,
        decided_at=datetime.now(timezone.utc),
        mlflow_run_id=experiment.mlflow_run_id,
        linkage_sha256=linkage,
    )
    session.add(row)
    session.flush()

    # MLflow alias mirrors (never owns) champion state.
    if decision == "promoted":
        try:
            import mlflow
            from mlflow import MlflowClient

            client = MlflowClient()
            name = "openpali-issuance-champion"
            try:
                client.create_registered_model(name)
            except Exception:  # noqa: BLE001 - already exists
                pass
            version = client.create_model_version(
                name=name,
                source=model.artifact_uri,
                run_id=experiment.mlflow_run_id,
            )
            client.set_registered_model_alias(name, "champion", version.version)
        except Exception:  # noqa: BLE001 - alias mirror is non-authoritative
            pass
    return row
