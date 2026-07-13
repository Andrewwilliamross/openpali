"""ops.job_run: OpenPali's idempotent, product-visible projection of Prefect
flow runs (OPS-002).

Prefect owns scheduling/retries/flow history; each flow upserts one job_run
row keyed by an explicit idempotency key, links the Prefect flow-run ID, and
records the persisted output artifact IDs that downstream stages consume."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from openpali.storage.models import JobRun


def _now() -> datetime:
    return datetime.now(timezone.utc)


def job_run_id(flow_name: str, idempotency_key: str) -> str:
    return "job-" + hashlib.sha256(f"{flow_name}:{idempotency_key}".encode()).hexdigest()[:20]


def prefect_flow_run_id() -> str | None:
    try:
        from prefect.context import get_run_context

        context = get_run_context()
        return str(context.flow_run.id)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 - callable outside a flow run
        return None


def start_job(
    session: Session,
    *,
    flow_name: str,
    idempotency_key: str,
    inputs: dict,
    deployment_name: str | None = None,
) -> JobRun:
    """Get-or-create the job row. A completed row short-circuits reruns."""

    existing = session.execute(
        select(JobRun).where(JobRun.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status == "succeeded":
            return existing
        existing.attempt += 1
        existing.status = "running"
        existing.prefect_flow_run_id = prefect_flow_run_id() or existing.prefect_flow_run_id
        session.flush()
        return existing
    job = JobRun(
        job_run_id=job_run_id(flow_name, idempotency_key),
        flow_name=flow_name,
        deployment_name=deployment_name,
        prefect_flow_run_id=prefect_flow_run_id(),
        idempotency_key=idempotency_key,
        inputs=inputs,
        started_at=_now(),
        status="running",
    )
    session.add(job)
    session.flush()
    return job


def finish_job(
    session: Session,
    job: JobRun,
    *,
    status: str,
    outputs: dict | None = None,
    failure_class: str | None = None,
    snapshot_id: str | None = None,
) -> None:
    job.status = status
    job.outputs = outputs or {}
    job.failure_class = failure_class
    job.snapshot_id = snapshot_id
    job.finished_at = _now()
    session.flush()
