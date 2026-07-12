"""Prefect flows: source refresh, civic snapshot, analytics, and release.

Retry policy is TYPED (OPS-002): only transient acquisition failures retry;
schema drift, source mutation, rights, and semantic validation failures fail
the run immediately. Domain state lives in PostgreSQL — Prefect never becomes
the domain database.
"""

from __future__ import annotations

from datetime import datetime, timezone

from prefect import flow, get_run_logger, task

from openpali.adapters.base import AcquisitionError
from openpali.ingestion.pipeline import (
    FULL_REFRESH_ORDER,
    RELEASE_BLOCKING_SOURCES,
    full_refresh,
    refresh_source,
)
from openpali.ingestion.snapshot import build_snapshot
from openpali.orchestration.jobs import finish_job, start_job
from openpali.publication.release import PublicationGateError, publish_release
from openpali.storage.db import session_scope
from openpali.storage.objects import ObjectStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _retry_transient(task_, task_run, state) -> bool:
    """Prefect retry_condition_fn: retry ONLY typed transient failures."""

    try:
        exception = state.result(raise_on_failure=False)
    except Exception:  # noqa: BLE001
        return False
    if isinstance(exception, AcquisitionError):
        return exception.failure_class == "transient"
    return False


@task(retries=2, retry_delay_seconds=30, retry_condition_fn=_retry_transient)
def refresh_source_task(source_id: str, online: bool, requested_at_iso: str) -> dict:
    requested_at = datetime.fromisoformat(requested_at_iso)
    store = ObjectStore()
    with session_scope() as session:
        job = start_job(
            session,
            flow_name="source-refresh",
            idempotency_key=f"refresh:{source_id}:{requested_at_iso}",
            inputs={"source_id": source_id, "online": online,
                    "requested_at": requested_at_iso},
        )
        if job.status == "succeeded" and job.outputs.get("run_id"):
            return dict(job.outputs)
        result = refresh_source(
            session, store, source_id, online=online, requested_at=requested_at
        )
        outputs = {
            "run_id": result.run_id,
            "status": result.status,
            "record_count": result.record_count,
            "undocumented": result.load.undocumented if result.load else [],
        }
        finish_job(
            session,
            job,
            status="succeeded" if result.status == "succeeded" else "failed",
            outputs=outputs,
            failure_class=None if result.status == "succeeded" else "acquisition",
        )
        if result.status != "succeeded":
            raise RuntimeError(f"{source_id} acquisition failed: {result.error}")
        return outputs


@flow(name="source-refresh")
def source_refresh_flow(source_id: str, online: bool = True,
                        requested_at_iso: str | None = None) -> dict:
    requested_at_iso = requested_at_iso or _utcnow().isoformat()
    return refresh_source_task(source_id, online, requested_at_iso)


@flow(name="civic-snapshot")
def civic_snapshot_flow(run_ids: list[str], cutoff_iso: str) -> dict:
    logger = get_run_logger()
    cutoff = datetime.fromisoformat(cutoff_iso)
    with session_scope() as session:
        job = start_job(
            session,
            flow_name="civic-snapshot",
            idempotency_key=f"snapshot:{','.join(sorted(run_ids))}:{cutoff_iso}",
            inputs={"run_ids": sorted(run_ids), "cutoff": cutoff_iso},
        )
        result = build_snapshot(session, run_ids, cutoff)
        outputs = {
            "snapshot_id": result.snapshot_id,
            "properties": result.properties,
            "observations": result.observations,
            "conflicts": result.conflicts,
        }
        finish_job(session, job, status="succeeded", outputs=outputs,
                   snapshot_id=result.snapshot_id)
    logger.info("snapshot %s", outputs)
    return outputs


@flow(name="analytics-snapshot")
def analytics_snapshot_flow(snapshot_id: str) -> dict:
    from openpali.metrics.compute import compute_all

    with session_scope() as session:
        job = start_job(
            session,
            flow_name="analytics-snapshot",
            idempotency_key=f"analytics:{snapshot_id}",
            inputs={"snapshot_id": snapshot_id},
        )
        outcome = compute_all(session, snapshot_id)
        finish_job(session, job, status="succeeded", outputs=outcome,
                   snapshot_id=snapshot_id)
    return outcome


def _undocumented_from_runs(session, snapshot_id: str) -> list[str]:
    """Frozen undocumented-taxonomy values from the snapshot's input runs —
    derived from acquisition-run health, never trusted from a caller."""

    from sqlalchemy import select as _select

    from openpali.storage.models import AcquisitionRun, CivicSnapshot

    snapshot = session.execute(
        _select(CivicSnapshot).where(CivicSnapshot.snapshot_id == snapshot_id)
    ).scalar_one()
    values: set[str] = set()
    for run_id in snapshot.input_runs:
        run_row = session.execute(
            _select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
        ).scalar_one()
        values.update((run_row.health or {}).get("load", {}).get("undocumented", []))
    return sorted(values)


@flow(name="release-candidate")
def release_candidate_flow(
    snapshot_id: str,
    kind: str = "fixture",
    undocumented: list[str] | None = None,
) -> dict:
    store = ObjectStore()
    with session_scope() as session:
        if undocumented is None:
            undocumented = _undocumented_from_runs(session, snapshot_id)
        job = start_job(
            session,
            flow_name="release-candidate",
            idempotency_key=f"release:{snapshot_id}:{kind}",
            inputs={"snapshot_id": snapshot_id, "kind": kind},
        )
        try:
            result = publish_release(
                session, store, snapshot_id, kind=kind,
                undocumented_values=undocumented or [],
                promoted_by="prefect-worker",
            )
        except PublicationGateError as exc:
            finish_job(session, job, status="failed", failure_class="gate",
                       outputs={"error": str(exc)}, snapshot_id=snapshot_id)
            raise
        outputs = {
            "release_id": result.release_id,
            "status": result.status,
            "mirror_ok": result.mirror_ok,
            "gates": result.gate_results,
        }
        # publish_release committed; re-open unit of work for the job row.
        job = start_job(
            session,
            flow_name="release-candidate",
            idempotency_key=f"release:{snapshot_id}:{kind}",
            inputs={"snapshot_id": snapshot_id, "kind": kind},
        )
        finish_job(session, job, status="succeeded", outputs=outputs,
                   snapshot_id=snapshot_id)
    return outputs


@flow(name="full-refresh-release")
def full_refresh_release_flow(
    online: bool = True,
    kind: str = "representative",
    requested_at_iso: str | None = None,
    sources: list[str] | None = None,
) -> dict:
    """End-to-end: every applicable source -> snapshot -> analytics -> release."""

    logger = get_run_logger()
    requested_at_iso = requested_at_iso or _utcnow().isoformat()
    requested_at = datetime.fromisoformat(requested_at_iso)
    store = ObjectStore()

    with session_scope() as session:
        job = start_job(
            session,
            flow_name="full-refresh-release",
            idempotency_key=f"full:{kind}:{requested_at_iso}",
            inputs={"kind": kind, "online": online, "requested_at": requested_at_iso},
        )
        outcome = full_refresh(
            session, store, online=online, requested_at=requested_at,
            sources=tuple(sources) if sources else FULL_REFRESH_ORDER,
        )
        for result in outcome.results:
            logger.info(
                "source %s: %s (%s records)",
                result.source_id, result.status, result.record_count,
            )
        if outcome.blocking_failures:
            finish_job(
                session, job, status="failed", failure_class="required_source",
                outputs={"blocking_failures": outcome.blocking_failures},
            )
            raise RuntimeError(
                f"release-blocking sources failed: {outcome.blocking_failures}"
            )
        run_ids = outcome.run_ids
        cutoff = _utcnow()
        snapshot = build_snapshot(session, run_ids, cutoff)
        session.commit()

        from openpali.metrics.compute import compute_all

        analytics = compute_all(session, snapshot.snapshot_id)
        session.commit()

        try:
            release = publish_release(
                session, store, snapshot.snapshot_id, kind=kind,
                undocumented_values=outcome.undocumented,
                promoted_by="prefect-worker",
            )
        except PublicationGateError as exc:
            job = start_job(
                session, flow_name="full-refresh-release",
                idempotency_key=f"full:{kind}:{requested_at_iso}",
                inputs={"kind": kind},
            )
            finish_job(session, job, status="failed", failure_class="gate",
                       outputs={"error": str(exc)}, snapshot_id=snapshot.snapshot_id)
            raise
        outputs = {
            "release_id": release.release_id,
            "snapshot_id": snapshot.snapshot_id,
            "run_ids": run_ids,
            "analytics": analytics,
            "mirror_ok": release.mirror_ok,
        }
        job = start_job(
            session, flow_name="full-refresh-release",
            idempotency_key=f"full:{kind}:{requested_at_iso}",
            inputs={"kind": kind},
        )
        finish_job(session, job, status="succeeded", outputs=outputs,
                   snapshot_id=snapshot.snapshot_id)
    logger.info("release %s", outputs["release_id"])
    return outputs


ALL_FLOWS = {
    "source-refresh": source_refresh_flow,
    "civic-snapshot": civic_snapshot_flow,
    "analytics-snapshot": analytics_snapshot_flow,
    "release-candidate": release_candidate_flow,
    "full-refresh-release": full_refresh_release_flow,
}


@flow(name="spatial-refresh")
def spatial_refresh_flow(online: bool = True) -> dict:
    """USGS AOI acquisition -> raw asset registration -> derived products."""

    from openpali.spatial.derive import derive_usgs_products
    from openpali.spatial.usgs import refresh_usgs

    store = ObjectStore()
    with session_scope() as session:
        job = start_job(
            session,
            flow_name="spatial-refresh",
            idempotency_key=f"spatial:{_utcnow().date().isoformat()}",
            inputs={"online": online},
        )
        acquisition = refresh_usgs(session, store, online=online)
        if acquisition.status != "succeeded":
            finish_job(session, job, status="failed", failure_class="acquisition",
                       outputs={"run_id": acquisition.run_id})
            raise RuntimeError(f"usgs acquisition failed: {acquisition.run_id}")
        derived = derive_usgs_products(session, store)
        outputs = {
            "run_id": acquisition.run_id,
            "tiles": acquisition.tiles,
            "version_id": derived["version_id"],
            "surfels": derived["surfels"],
            "reconciliation": derived["reconciliation"],
        }
        finish_job(session, job, status="succeeded", outputs=outputs)
    return outputs
