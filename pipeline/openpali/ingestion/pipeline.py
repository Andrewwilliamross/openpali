"""Composed ingestion services shared by the CLI and the Prefect flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from openpali.adapters.base import AcquisitionRequest
from openpali.adapters.registry import ADAPTERS
from openpali.ingestion.acquire import rehydrate, run_acquisition
from openpali.ingestion.load import (
    LoadResult,
    load_county_records,
    load_dins_structures,
    load_ladbs_inspections,
    load_ladbs_permits,
    load_malibu_markers,
    load_socrata_crosscheck,
)
from openpali.storage.models import AcquisitionRun
from openpali.storage.objects import ObjectStore

#: Dependency-ordered source list for a full refresh. County first (defines
#: the identity universe), then permits (inspection joins), then the rest.
FULL_REFRESH_ORDER = (
    "county_base",
    "ladbs_permits",
    "ladbs_inspections",
    "malibu_dash",
    "calfire_dins",
    "socrata_permits",
    "socrata_cofo",
)

LOADERS = {
    "county_base": load_county_records,
    "ladbs_permits": load_ladbs_permits,
    "ladbs_inspections": load_ladbs_inspections,
    "malibu_dash": load_malibu_markers,
    "calfire_dins": load_dins_structures,
    "socrata_permits": load_socrata_crosscheck,
    "socrata_cofo": load_socrata_crosscheck,
}

#: Sources whose failure blocks a new release outright (frozen source policy).
RELEASE_BLOCKING_SOURCES = frozenset(
    {"county_base", "ladbs_permits", "ladbs_inspections", "calfire_dins"}
)


@dataclass(slots=True)
class SourceRefreshResult:
    source_id: str
    run_id: str
    status: str
    record_count: int
    load: LoadResult | None
    error: str | None = None


def refresh_source(
    session: Session,
    store: ObjectStore,
    source_id: str,
    *,
    online: bool,
    requested_at: datetime | None = None,
    replay_run_id: str | None = None,
) -> SourceRefreshResult:
    """Acquire (or replay) one source and load it into the ledger."""

    adapter = ADAPTERS[source_id]()
    if replay_run_id:
        raw = rehydrate(session, store, adapter, replay_run_id)
        run_id = replay_run_id
    else:
        request = AcquisitionRequest(online=online, parameters=_parameters(adapter))
        acquisition = run_acquisition(
            session, store, adapter, request, requested_at=requested_at
        )
        if acquisition.status != "succeeded":
            return SourceRefreshResult(
                source_id=source_id,
                run_id=acquisition.run_id,
                status="failed",
                record_count=0,
                load=None,
                error=acquisition.error,
            )
        run_id = acquisition.run_id
        raw = acquisition.raw or rehydrate(session, store, adapter, run_id)

    observed_at = raw.retrieved_at or raw.requested_at
    records = list(adapter.normalize(raw))
    loader = LOADERS[source_id]
    load_result = loader(session, records, run_id, observed_at=observed_at)

    run_row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    health = dict(run_row.health or {})
    health["load"] = {
        "records_seen": load_result.records_seen,
        "record_versions_new": load_result.record_versions_new,
        "observations_new": load_result.observations_new,
        "undocumented": load_result.undocumented,
        **({"join_stats": load_result.join_stats} if load_result.join_stats else {}),
    }
    run_row.health = health
    session.flush()
    return SourceRefreshResult(
        source_id=source_id,
        run_id=run_id,
        status="succeeded",
        record_count=raw.record_count,
        load=load_result,
    )


def _parameters(adapter) -> dict:
    parameters = {}
    for attr in ("where", "out_fields", "select"):
        value = getattr(adapter, attr, None)
        if value:
            parameters[attr] = value
    parameters["layer_url"] = getattr(adapter, "layer_url", "")
    return parameters


@dataclass(slots=True)
class FullRefreshResult:
    results: list[SourceRefreshResult] = field(default_factory=list)

    @property
    def run_ids(self) -> list[str]:
        return [r.run_id for r in self.results if r.status == "succeeded"]

    @property
    def undocumented(self) -> list[str]:
        values: set[str] = set()
        for result in self.results:
            if result.load is not None:
                values.update(result.load.undocumented)
        return sorted(values)

    @property
    def blocking_failures(self) -> list[str]:
        return [
            r.source_id
            for r in self.results
            if r.status != "succeeded" and r.source_id in RELEASE_BLOCKING_SOURCES
        ]


def full_refresh(
    session: Session,
    store: ObjectStore,
    *,
    online: bool,
    requested_at: datetime | None = None,
    sources: tuple[str, ...] = FULL_REFRESH_ORDER,
) -> FullRefreshResult:
    outcome = FullRefreshResult()
    for source_id in sources:
        result = refresh_source(
            session, store, source_id, online=online, requested_at=requested_at
        )
        outcome.results.append(result)
        session.commit()
    return outcome
