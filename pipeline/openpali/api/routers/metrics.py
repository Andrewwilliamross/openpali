"""Release-qualified community metrics, bottlenecks, and research export."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from openpali.storage.models import (
    MetricDefinition,
    MetricValue,
    Publication,
    ReconciliationResult,
)

from .releases import IMMUTABLE_CACHE, _etag, _maybe_304, get_release, get_session

router = APIRouter(prefix="/v1", tags=["metrics"])


def _definitions(session: Session) -> dict[tuple[str, str], MetricDefinition]:
    rows = session.execute(select(MetricDefinition)).scalars()
    return {(d.metric_id, d.version): d for d in rows}


def _values(session: Session, snapshot_id: str, metric_ids: list[str] | None = None):
    query = select(MetricValue).where(MetricValue.snapshot_id == snapshot_id)
    if metric_ids:
        query = query.where(MetricValue.metric_id.in_(metric_ids))
    return list(session.execute(query.order_by(MetricValue.metric_id, MetricValue.cohort_key)).scalars())


def _definition_payload(definition: MetricDefinition) -> dict:
    return {
        "metric_id": definition.metric_id,
        "version": definition.version,
        "title": definition.title,
        "unit": definition.unit,
        "population": definition.population,
        "numerator": definition.numerator,
        "denominator": definition.denominator,
        "jurisdiction": definition.jurisdiction,
        "window": definition.window,
        "inclusion": definition.inclusion_rules,
        "missingness": definition.missingness_rules,
        "censoring": definition.censoring_rules,
        "suppression": definition.suppression_rules,
        "validation": definition.validation,
    }


def _value_payload(value: MetricValue) -> dict:
    return {
        "metric_id": value.metric_id,
        "version": value.version,
        "cohort": value.cohort,
        "value": value.value,
        "interval_low": value.interval_low,
        "interval_high": value.interval_high,
        "sample_size": value.sample_size,
        "missing_count": value.missing_count,
        "status": value.status,
        "computation": value.computation,
    }


@router.get("/releases/{release_id}/metrics/community")
def community_metrics(
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
) -> dict:
    etag = _etag(publication.release_id, "metrics-community")
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    values = _values(
        session, publication.snapshot_id,
        ["universe_destroyed_parcels", "lane_signal_prevalence",
         "milestone_prevalence", "weekly_transition_incidence",
         "evidence_missingness"],
    )
    definitions = _definitions(session)
    used = sorted({(v.metric_id, v.version) for v in values})
    reconciliations = list(
        session.execute(
            select(ReconciliationResult).where(
                ReconciliationResult.snapshot_id == publication.snapshot_id
            )
        ).scalars()
    )
    return {
        "release_id": publication.release_id,
        "snapshot_id": publication.snapshot_id,
        "definitions": [
            _definition_payload(definitions[key]) for key in used if key in definitions
        ],
        "values": [_value_payload(v) for v in values],
        "reconciliations": [
            {
                "metric_id": r.metric_id,
                "reference_source": r.reference_source,
                "reference_definition": r.reference_definition,
                "reference_value": r.reference_value,
                "our_value": r.our_value,
                "tolerance_pct": r.tolerance_pct,
                "drift_pct": r.drift_pct,
                "verdict": r.verdict,
            }
            for r in reconciliations
        ],
        "causal_disclaimer": (
            "All values are observational descriptions of public records. "
            "None measures resident effort, contractor quality, agency "
            "performance, or the causal effect of any policy."
        ),
    }


@router.get("/releases/{release_id}/metrics/bottlenecks")
def bottleneck_metrics(
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
) -> dict:
    etag = _etag(publication.release_id, "metrics-bottlenecks")
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    values = _values(
        session, publication.snapshot_id,
        ["permitting_backlog_flow", "time_to_issuance_km"],
    )
    definitions = _definitions(session)
    used = sorted({(v.metric_id, v.version) for v in values})
    return {
        "release_id": publication.release_id,
        "snapshot_id": publication.snapshot_id,
        "definitions": [
            _definition_payload(definitions[key]) for key in used if key in definitions
        ],
        "values": [_value_payload(v) for v in values],
        "bottleneck_note": (
            "A 'bottleneck' here is the disclosed conjunction of backlog, "
            "inflow, outflow, and censoring-aware time-in-lane — never merely "
            "the largest stage count. Right-censoring metadata is included."
        ),
    }


@router.get("/releases/{release_id}/metrics/export.csv")
def metrics_export(
    request: Request,
    response: Response,
    publication: Publication = Depends(get_release),
    session: Session = Depends(get_session),
) -> Response:
    etag = _etag(publication.release_id, "metrics-export")
    _maybe_304(request, response, etag, IMMUTABLE_CACHE)
    values = _values(session, publication.snapshot_id)
    sink = io.StringIO()
    writer = csv.writer(sink)
    writer.writerow(
        ["release_id", "snapshot_id", "metric_id", "version", "cohort",
         "value", "interval_low", "interval_high", "sample_size",
         "missing_count", "status"]
    )
    for v in values:
        writer.writerow(
            [publication.release_id, publication.snapshot_id, v.metric_id,
             v.version, v.cohort_key, v.value, v.interval_low, v.interval_high,
             v.sample_size, v.missing_count, v.status]
        )
    return Response(
        content=sink.getvalue(),
        media_type="text/csv",
        headers={
            "ETag": etag,
            "Cache-Control": IMMUTABLE_CACHE,
            "Content-Disposition": (
                f"attachment; filename=openpali-metrics-{publication.release_id}.csv"
            ),
        },
    )
