"""Pydantic response models — the typed public contract."""

from __future__ import annotations

from datetime import date, datetime
from datetime import date as DateType

from pydantic import BaseModel, Field


class ReleaseInfo(BaseModel):
    release_id: str
    snapshot_id: str
    kind: str
    status: str
    published_at: datetime | None
    manifest_sha256: str
    schema_versions: dict[str, str] = Field(default_factory=dict)
    policy_versions: dict[str, str] = Field(default_factory=dict)
    coverage: dict[str, int] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    lkg_release_id: str | None = None


class PropertySummary(BaseModel):
    property_id: str
    apn: str
    address: str | None
    neighborhood: str | None
    jurisdiction: str | None
    lane_signals: dict[str, str]
    milestones: dict[str, bool]
    last_evidence_date: date | None
    conflict_count: int


class PropertyPage(BaseModel):
    release_id: str
    items: list[PropertySummary]
    next_cursor: str | None
    total: int | None = None


class PropertyDetail(BaseModel):
    property_id: str
    apn: str
    address: str | None
    neighborhood: str | None
    jurisdiction: str | None
    identity: dict
    pre_fire: dict
    lane_signals: dict[str, str]
    milestones: dict[str, bool]
    projection_policy_version: str
    observation_count: int
    conflict_count: int
    last_evidence_date: date | None
    center: list[float] | None
    release_id: str
    snapshot_id: str


class OccurrenceModel(BaseModel):
    kind: str
    date: DateType | None = None
    earliest: DateType | None = None
    latest: DateType | None = None


class ObservationModel(BaseModel):
    observation_id: str
    subject_type: str
    subject_id: str
    lane: str | None
    event_type: str
    status: str
    occurred: OccurrenceModel
    observed_at: datetime
    source_id: str
    record_version_id: str | None
    policy_version: str
    label: str
    related_subjects: list[dict]
    detail: dict
    retracted: bool = False
    retraction_reason: str | None = None


class ObservationPage(BaseModel):
    release_id: str
    property_id: str
    items: list[ObservationModel]
    next_cursor: str | None


class SourceHealthModel(BaseModel):
    source_id: str
    title: str | None = None
    ok: bool
    records: int | None = None
    retrieved_at: datetime | None = None
    upstream_edited_at: datetime | None = None
    schema_fingerprint: str | None = None
    response_sha256: str | None = None
    notes: dict = Field(default_factory=dict)


class SourcesResponse(BaseModel):
    release_id: str
    snapshot_id: str
    sources: list[SourceHealthModel]


class LiveSourceStatus(BaseModel):
    source_id: str
    last_run_status: str | None
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    error_class: str | None


class LiveStatusResponse(BaseModel):
    sources: list[LiveSourceStatus]
    current_release_id: str | None
    lkg_release_id: str | None
