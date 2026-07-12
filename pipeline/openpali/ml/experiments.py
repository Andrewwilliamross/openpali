"""Executed baseline + challenger experiments (ML-002).

Ladder (one interface, one tracker):
1. naive cohort baseline — empirical issuance fraction within the horizon
   among fully-followed applications;
2. censoring-aware baseline — Kaplan-Meier;
3. interpretable challenger — regularized Cox PH on calendar covariates
   (submission timing), fit ONLY when the dataset's precommitted
   point-in-time-history gate passed; otherwise the challenger emits
   ``INSUFFICIENT_POINT_IN_TIME_HISTORY`` while baselines still run.

Every run records dataset/code/config/seed, time-dependent IPCW Brier scores,
calibration bins, cohort metrics, and artifacts in MLflow; OpenPali keeps its
own immutable ``ml.experiment_run``/``ml.model_version`` rows with verified
artifact hashes (lifecycle ownership split per the blueprint).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import pickle
import subprocess
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from openpali.identity.ids import canonical_json
from openpali.ml.dataset import HORIZON_DAYS, load_dataset_rows
from openpali.storage.models import DatasetVersion, ExperimentRun, ModelVersion
from openpali.storage.objects import ARTIFACT_BUCKET, ObjectStore

SEED = 20260712
EXPERIMENT_NAME = "openpali-issuance-180d"
INSUFFICIENT = "INSUFFICIENT_POINT_IN_TIME_HISTORY"

COX_FEATURES = ["submission_days_since_fire"]
COX_PENALIZER = 0.1


def _code_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
            text=True, timeout=5,
        ).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


@dataclass(slots=True)
class RunRecord:
    name: str
    experiment_run_id: str
    mlflow_run_id: str | None
    metrics: dict
    artifact_uri: str | None = None
    artifact_sha256: str | None = None
    status: str = "completed"


@dataclass(slots=True)
class ExperimentOutcome:
    dataset_id: str
    gate_passed: bool
    runs: list[RunRecord] = field(default_factory=list)
    challenger_status: str = "not_run"
    model_id: str | None = None


# ---------------------------------------------------------------------------
# evaluation helpers
# ---------------------------------------------------------------------------


def _ipcw_brier(rows: list[dict], horizon: int, survival_at) -> tuple[float | None, int]:
    """IPCW Brier score at ``horizon`` days.

    ``survival_at(row) -> S_hat(horizon | x)``. Censoring distribution G is a
    KM fit on (duration, 1-event). Standard Graf et al. weighting:
    event before t: w = 1/G(T_i); survivor past t: w = 1/G(t).
    """

    from lifelines import KaplanMeierFitter

    durations = [r["duration_days"] for r in rows]
    events = [r["event_issued"] for r in rows]
    if not rows:
        return None, 0
    censor_km = KaplanMeierFitter()
    censor_km.fit(durations, [1 - e for e in events])

    def g(t: float) -> float:
        value = float(censor_km.predict(t))
        return max(value, 1e-4)

    total = 0.0
    n = 0
    for row in rows:
        t_i, d_i = row["duration_days"], row["event_issued"]
        s_hat = survival_at(row)
        if d_i == 1 and t_i <= horizon:
            weight = 1.0 / g(t_i)
            total += weight * (s_hat - 0.0) ** 2
            n += 1
        elif t_i > horizon:
            weight = 1.0 / g(horizon)
            total += weight * (s_hat - 1.0) ** 2
            n += 1
        # censored before horizon: contributes 0 (weight handled by IPCW)
    denominator = len(rows)
    return (total / denominator if denominator else None), n


def _calibration_bins(rows: list[dict], horizon: int, risk_at) -> list[dict]:
    """Decile calibration of predicted P(issued<=horizon) vs observed outcome
    among rows with definitive horizon status."""

    definitive = [
        r for r in rows
        if (r["event_issued"] == 1 and r["duration_days"] <= horizon)
        or r["duration_days"] > horizon
    ]
    scored = sorted(
        ((risk_at(r), 1 if (r["event_issued"] == 1 and r["duration_days"] <= horizon) else 0)
         for r in definitive),
        key=lambda pair: pair[0],
    )
    bins = []
    if not scored:
        return bins
    size = max(len(scored) // 10, 1)
    for start in range(0, len(scored), size):
        chunk = scored[start:start + size]
        bins.append(
            {
                "n": len(chunk),
                "mean_predicted": sum(p for p, _ in chunk) / len(chunk),
                "observed_rate": sum(o for _, o in chunk) / len(chunk),
            }
        )
    return bins


def _cohort_metrics(rows: list[dict], horizon: int, risk_at) -> dict:
    """Brier by submission-month cohort (sufficient-sample cohorts only)."""

    cohorts: dict[str, list[dict]] = {}
    for row in rows:
        cohorts.setdefault(f"month_{row['submission_month']:02d}", []).append(row)
    out = {}
    for name, cohort_rows in sorted(cohorts.items()):
        if len(cohort_rows) < 15:
            continue
        brier, evaluable = _ipcw_brier(cohort_rows, horizon, lambda r: 1 - risk_at(r))
        out[name] = {"n": len(cohort_rows), "ipcw_brier_180": brier,
                     "evaluable": evaluable}
    return out


# ---------------------------------------------------------------------------
# model wrappers (typed signature: fit / predict survival / serialize)
# ---------------------------------------------------------------------------


class KMBaseline:
    name = "baseline-km"

    def fit(self, rows: list[dict]) -> None:
        from lifelines import KaplanMeierFitter

        self.km = KaplanMeierFitter()
        self.km.fit([r["duration_days"] for r in rows],
                    [r["event_issued"] for r in rows])

    def survival(self, row: dict, t: int) -> float:
        return float(self.km.predict(t))

    def risk(self, row: dict, t: int) -> float:
        return 1.0 - self.survival(row, t)


class NaiveBaseline:
    """Empirical horizon fraction among fully-followed applications."""

    name = "baseline-naive"

    def fit(self, rows: list[dict]) -> None:
        followed = [
            r for r in rows
            if (r["event_issued"] == 1 and r["duration_days"] <= HORIZON_DAYS)
            or r["duration_days"] > HORIZON_DAYS
        ]
        issued = sum(
            1 for r in followed
            if r["event_issued"] == 1 and r["duration_days"] <= HORIZON_DAYS
        )
        self.rate = issued / len(followed) if followed else None
        self.n_followed = len(followed)

    def survival(self, row: dict, t: int) -> float:
        return 1.0 - (self.rate or 0.0)

    def risk(self, row: dict, t: int) -> float:
        return self.rate or 0.0


class CoxChallenger:
    """Regularized Cox PH on calendar covariates; interpretable by design."""

    name = "challenger-cox"

    def fit(self, rows: list[dict]) -> None:
        import pandas as pd
        from lifelines import CoxPHFitter

        frame = pd.DataFrame(
            [
                {
                    "duration": max(r["duration_days"], 0.5),
                    "event": r["event_issued"],
                    **{f: float(r[f]) for f in COX_FEATURES},
                }
                for r in rows
            ]
        )
        self.cox = CoxPHFitter(penalizer=COX_PENALIZER)
        self.cox.fit(frame, duration_col="duration", event_col="event")

    def survival(self, row: dict, t: int) -> float:
        import pandas as pd

        x = pd.DataFrame([{f: float(row[f]) for f in COX_FEATURES}])
        return float(self.cox.predict_survival_function(x, times=[t]).iloc[0, 0])

    def risk(self, row: dict, t: int) -> float:
        return 1.0 - self.survival(row, t)

    def coefficients(self) -> dict:
        return {k: float(v) for k, v in self.cox.params_.items()}


# ---------------------------------------------------------------------------
# experiment execution
# ---------------------------------------------------------------------------


def _mlflow():
    import mlflow

    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if uri:
        mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(EXPERIMENT_NAME)
    return mlflow


def run_experiments(
    session: Session,
    store: ObjectStore,
    dataset_id: str,
    *,
    include_final_holdout: bool = False,
) -> ExperimentOutcome:
    dataset = session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
    ).scalar_one()
    rows = load_dataset_rows(store, dataset)
    gate = (dataset.sufficiency or {}).get("gate", {})
    gate_passed = bool(gate.get("passed"))
    outcome = ExperimentOutcome(dataset_id=dataset_id, gate_passed=gate_passed)
    if not rows:
        outcome.challenger_status = "no_rows"
        return outcome

    train = [r for r in rows if r["split"] != "final_holdout"]
    evaluation = (
        [r for r in rows if r["split"] == "final_holdout"]
        if include_final_holdout
        else [r for r in train if r["split"] == "fold_0"]
    )
    eval_label = "final_holdout" if include_final_holdout else "fold_0"
    fit_rows = (
        train if include_final_holdout
        else [r for r in train if r["split"] != "fold_0"]
    )

    mlflow = _mlflow()
    commit = _code_commit()

    def execute(model, extra_params: dict | None = None) -> RunRecord:
        with mlflow.start_run(run_name=f"{model.name}:{dataset_id[:12]}") as active:
            model.fit(fit_rows)
            brier180, evaluable = _ipcw_brier(
                evaluation, HORIZON_DAYS, lambda r: model.survival(r, HORIZON_DAYS)
            )
            brier90, _ = _ipcw_brier(
                evaluation, 90, lambda r: model.survival(r, 90)
            )
            calibration = _calibration_bins(
                evaluation, HORIZON_DAYS, lambda r: model.risk(r, HORIZON_DAYS)
            )
            calibration_error = (
                sum(abs(b["mean_predicted"] - b["observed_rate"]) * b["n"] for b in calibration)
                / max(sum(b["n"] for b in calibration), 1)
                if calibration else None
            )
            cohorts = _cohort_metrics(
                evaluation, HORIZON_DAYS, lambda r: model.risk(r, HORIZON_DAYS)
            )
            metrics = {
                "ipcw_brier_180": brier180,
                "ipcw_brier_90": brier90,
                "calibration_abs_error": calibration_error,
                "n_fit": len(fit_rows),
                "n_eval": len(evaluation),
                "n_eval_definitive": evaluable,
                "events_fit": sum(r["event_issued"] for r in fit_rows),
            }
            config = {
                "model": model.name,
                "seed": SEED,
                "eval_split": eval_label,
                "horizon_days": HORIZON_DAYS,
                "features": COX_FEATURES if isinstance(model, CoxChallenger) else [],
                "penalizer": COX_PENALIZER if isinstance(model, CoxChallenger) else None,
            }
            mlflow.log_params({**config, "dataset_id": dataset_id, "commit": commit})
            for key, value in metrics.items():
                if value is not None:
                    mlflow.log_metric(key, float(value))
            mlflow.log_dict({"bins": calibration}, "calibration.json")
            mlflow.log_dict(cohorts, "cohorts.json")

            artifact_uri = artifact_sha = None
            payload = pickle.dumps(model)
            artifact_sha = hashlib.sha256(payload).hexdigest()
            key = f"models/{dataset_id}/{model.name}/{artifact_sha}/model.pkl"
            store.ensure_bucket(ARTIFACT_BUCKET)
            stored = store.put_content(ARTIFACT_BUCKET, key, payload, sha256=artifact_sha)
            artifact_uri = stored.uri
            mlflow.log_dict(
                {"artifact_uri": artifact_uri, "sha256": artifact_sha}, "artifact.json"
            )

            config_sha = hashlib.sha256(canonical_json(config).encode()).hexdigest()
            experiment_run_id = "exp-" + hashlib.sha256(
                f"{dataset_id}:{model.name}:{config_sha}:{eval_label}".encode()
            ).hexdigest()[:20]
            session.execute(
                pg_insert(ExperimentRun)
                .values(
                    experiment_run_id=experiment_run_id,
                    dataset_id=dataset_id,
                    mlflow_run_id=active.info.run_id,
                    model_family=model.name,
                    code_commit=commit,
                    config=config,
                    config_sha256=config_sha,
                    seed=SEED,
                    metrics={k: v for k, v in metrics.items() if v is not None},
                    artifacts={"model": artifact_uri, "model_sha256": artifact_sha},
                    status="completed",
                )
                .on_conflict_do_update(
                    index_elements=["experiment_run_id"],
                    set_={"metrics": {k: v for k, v in metrics.items() if v is not None},
                          "mlflow_run_id": active.info.run_id, "status": "completed"},
                )
            )
            session.flush()
            return RunRecord(
                name=model.name,
                experiment_run_id=experiment_run_id,
                mlflow_run_id=active.info.run_id,
                metrics=metrics,
                artifact_uri=artifact_uri,
                artifact_sha256=artifact_sha,
            )

    outcome.runs.append(execute(NaiveBaseline()))
    outcome.runs.append(execute(KMBaseline()))

    if gate_passed:
        challenger_record = execute(CoxChallenger())
        outcome.runs.append(challenger_record)
        outcome.challenger_status = "completed"
        model_id = "model-" + hashlib.sha256(
            f"{dataset_id}:{challenger_record.artifact_sha256}".encode()
        ).hexdigest()[:20]
        session.execute(
            pg_insert(ModelVersion)
            .values(
                model_id=model_id,
                experiment_run_id=challenger_record.experiment_run_id,
                artifact_uri=challenger_record.artifact_uri,
                artifact_sha256=challenger_record.artifact_sha256,
                signature={
                    "inputs": COX_FEATURES,
                    "output": "P(issued within 180 days of submission)",
                },
                training_cutoff=dataset.cutoff,
                target=dataset.target_policy,
                horizon_days=HORIZON_DAYS,
                limitations=(
                    "Origin estimate at submission time; never a current ETA. "
                    "Calendar covariates only; no parcel covariates until the "
                    "point-in-time history gate covers them."
                ),
                model_card={
                    "metrics": {k: v for k, v in challenger_record.metrics.items() if v is not None},
                    "dataset_id": dataset_id,
                    "gate": gate,
                },
            )
            .on_conflict_do_nothing(index_elements=["model_id"])
        )
        session.flush()
        outcome.model_id = model_id
    else:
        outcome.challenger_status = INSUFFICIENT
        # A typed insufficiency record still lands in MLflow for auditability.
        with mlflow.start_run(run_name=f"challenger-gated:{dataset_id[:12]}"):
            mlflow.log_params({"dataset_id": dataset_id, "status": INSUFFICIENT})
            mlflow.log_dict(gate, "gate.json")
    return outcome


def reload_model(store: ObjectStore, model: ModelVersion):
    """Fresh-process deserialization of the immutable model artifact."""

    key = model.artifact_uri.split("/", 3)[3]
    payload = store.get_verified(ARTIFACT_BUCKET, key, model.artifact_sha256)
    return pickle.loads(payload)
