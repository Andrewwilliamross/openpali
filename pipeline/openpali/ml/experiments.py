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
from openpali.ml.dataset import HORIZON_DAYS, ROLLING_FOLDS, load_dataset_rows
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


def _ipcw_brier(rows: list[dict], horizon: int, survival_at) -> tuple[float | None, int, int]:
    """IPCW Brier score at ``horizon`` days.

    ``survival_at(row) -> S_hat(horizon | x)``. Censoring distribution G is a
    KM fit on (duration, 1-event). Graf et al. weighting with the LEFT LIMIT
    G(T_i-) for events (durations are integer days, so t - 0.5 is exact):
    event before t: w = 1/G(T_i-); survivor past t: w = 1/G(t).

    Returns (score, evaluable_n, floor_hits) — floor_hits counts weights that
    hit the 1e-4 G floor, a visible instability signal instead of a silent cap.
    """

    from lifelines import KaplanMeierFitter

    durations = [r["duration_days"] for r in rows]
    events = [r["event_issued"] for r in rows]
    if not rows:
        return None, 0, 0
    censor_km = KaplanMeierFitter()
    censor_km.fit(durations, [1 - e for e in events])

    floor_hits = 0

    def g(t: float) -> float:
        nonlocal floor_hits
        value = float(censor_km.predict(t))
        if value < 1e-4:
            floor_hits += 1
        return max(value, 1e-4)

    total = 0.0
    n = 0
    for row in rows:
        t_i, d_i = row["duration_days"], row["event_issued"]
        s_hat = survival_at(row)
        if d_i == 1 and t_i <= horizon:
            weight = 1.0 / g(t_i - 0.5)  # left limit: G just BEFORE the event
            total += weight * (s_hat - 0.0) ** 2
            n += 1
        elif t_i > horizon:
            weight = 1.0 / g(horizon)
            total += weight * (s_hat - 1.0) ** 2
            n += 1
        # censored before horizon: contributes 0 (weight handled by IPCW)
    denominator = len(rows)
    return (total / denominator if denominator else None), n, floor_hits


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
    # minimum bin mass (methods review): single-digit bins feeding a binary
    # promotion gate are noise, not calibration evidence
    size = max(len(scored) // 10, 15)
    for start in range(0, len(scored), size):
        chunk = scored[start:start + size]
        if len(chunk) < 15:
            continue  # tail remainder too small to be evidence
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
        brier, evaluable, _ = _ipcw_brier(cohort_rows, horizon, lambda r: 1 - risk_at(r))
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
    """Empirical horizon fraction among fully-followed applications.

    Deliberately weak (complete-case conditioning is a textbook length bias)
    but at least TIME-HONEST: the rate is fit per queried horizon, so a
    90-day query never silently reuses the 180-day rate.
    """

    name = "baseline-naive"

    def fit(self, rows: list[dict]) -> None:
        self._rates: dict[int, float | None] = {}
        for horizon in (90, HORIZON_DAYS):
            followed = [
                r for r in rows
                if (r["event_issued"] == 1 and r["duration_days"] <= horizon)
                or r["duration_days"] > horizon
            ]
            issued = sum(
                1 for r in followed
                if r["event_issued"] == 1 and r["duration_days"] <= horizon
            )
            self._rates[horizon] = issued / len(followed) if followed else None
        self.rate = self._rates[HORIZON_DAYS]
        self.n_followed = None

    def survival(self, row: dict, t: int) -> float:
        if t not in self._rates:
            raise ValueError(f"naive baseline was not fit for horizon {t}")
        return 1.0 - (self._rates[t] or 0.0)

    def risk(self, row: dict, t: int) -> float:
        return 1.0 - self.survival(row, t)


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
        # training covariate range: persisted so serving can flag
        # extrapolation beyond what the model ever saw
        self.training_range = {
            f: [float(frame[f].min()), float(frame[f].max())] for f in COX_FEATURES
        }
        # PH diagnostic for the human reviewer (gate 4): Schoenfeld-residual
        # test p-values. Low p = evidence AGAINST proportional hazards.
        try:
            from lifelines.statistics import proportional_hazard_test

            test = proportional_hazard_test(self.cox, frame, time_transform="rank")
            self.ph_test_p = {
                str(idx): float(p) for idx, p in test.summary["p"].items()
            }
        except Exception:  # noqa: BLE001 - diagnostic must not break training
            self.ph_test_p = None

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

    # FORWARD evaluation always: dev runs fit on the two EARLIEST
    # chronological blocks and evaluate on the LATEST (fold_2); the final run
    # fits on all train blocks and evaluates once on the untouched holdout.
    train = [r for r in rows if r["split"] != "final_holdout"]
    dev_eval_fold = f"fold_{ROLLING_FOLDS - 1}"
    evaluation = (
        [r for r in rows if r["split"] == "final_holdout"]
        if include_final_holdout
        else [r for r in train if r["split"] == dev_eval_fold]
    )
    eval_label = "final_holdout" if include_final_holdout else dev_eval_fold
    fit_rows = (
        train if include_final_holdout
        else [r for r in train if r["split"] != dev_eval_fold]
    )

    mlflow = _mlflow()
    commit = _code_commit()

    def execute(model, extra_params: dict | None = None) -> RunRecord:
        with mlflow.start_run(run_name=f"{model.name}:{dataset_id[:12]}") as active:
            model.fit(fit_rows)
            brier180, evaluable, floor180 = _ipcw_brier(
                evaluation, HORIZON_DAYS, lambda r: model.survival(r, HORIZON_DAYS)
            )
            brier90, _, _ = _ipcw_brier(
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
                "ipcw_g_floor_hits_180": floor180,
                "calibration_abs_error": calibration_error,
                "n_fit": len(fit_rows),
                "n_eval": len(evaluation),
                "n_eval_definitive": evaluable,
                "events_fit": sum(r["event_issued"] for r in fit_rows),
                # persisted (not just MLflow) so the promotion gate can check
                # per-cohort regressions
                "cohorts": cohorts,
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
                if value is not None and not isinstance(value, dict):
                    mlflow.log_metric(key, float(value))
            mlflow.log_dict({"bins": calibration}, "calibration.json")
            mlflow.log_dict(cohorts, "cohorts.json")
            if isinstance(model, CoxChallenger):
                mlflow.log_dict(
                    {
                        # association, not a causal effect (claim boundary)
                        "coefficients_log_hazard_ratio": model.coefficients(),
                        "ph_schoenfeld_p": model.ph_test_p,
                        "training_range": model.training_range,
                    },
                    "cox-diagnostics.json",
                )

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
        challenger_model = CoxChallenger()
        challenger_record = execute(challenger_model)
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
                    # serving flags rows whose covariates fall outside this
                    "training_range": getattr(
                        challenger_model, "training_range", None
                    ),
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
