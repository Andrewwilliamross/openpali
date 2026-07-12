"""Canonical database model (blueprint minimum table matrix).

Schemas: ``source`` (acquisition evidence), ``civic`` (identity + bitemporal
observations + snapshots), ``analytics`` (metrics + reconciliation), ``ml``
(datasets/experiments/models/predictions/promotions), ``spatial`` (assets,
relations, candidates), ``ops`` (jobs, publications, corrections).

Identity rules (DATA-002):
- surrogate integer PKs never enter public contracts or semantic hashes;
- every public ID column stores a deterministic content-derived identifier
  (``openpali.domain``/``openpali.identity`` compute them);
- evidence tables are append-only: revisions/retractions reference, never
  mutate;
- every mutable business row carries UTC ``created_at``/``updated_at``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# source schema — acquisition evidence
# ---------------------------------------------------------------------------


class Source(TimestampMixin, Base):
    __tablename__ = "source"
    __table_args__ = {"schema": "source"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    authority: Mapped[str | None] = mapped_column(Text)
    url_template: Mapped[str | None] = mapped_column(Text)
    terms_reference: Mapped[str | None] = mapped_column(Text)
    expected_cadence: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(Text)
    criticality: Mapped[str] = mapped_column(Text, nullable=False, default="required")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AcquisitionRun(TimestampMixin, Base):
    __tablename__ = "acquisition_run"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_acquisition_run_run_id"),
        Index("ix_acq_source_requested", "source_id", "requested_at"),
        {"schema": "source"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: deterministic public run id (sha256 of source, params, requested time)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(
        Text, ForeignKey("source.source.source_id"), nullable=False
    )
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    online: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upstream_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_count: Mapped[int | None] = mapped_column(Integer)
    record_count: Mapped[int | None] = mapped_column(Integer)
    response_sha256: Mapped[str | None] = mapped_column(Text)
    schema_fingerprint: Mapped[str | None] = mapped_column(Text)
    terms_reference: Mapped[str | None] = mapped_column(Text)
    code_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error_class: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    health: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class RawObject(TimestampMixin, Base):
    __tablename__ = "raw_object"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_raw_object_sha256"),
        {"schema": "source"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    object_uri: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    classification: Mapped[str] = mapped_column(Text, nullable=False, default="public")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AcquisitionPage(Base):
    """Join: which raw objects (pages) one acquisition run retrieved, ordered."""

    __tablename__ = "acquisition_page"
    __table_args__ = (
        UniqueConstraint("acquisition_run_id", "page_index", name="uq_acqpage_run_page"),
        {"schema": "source"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    acquisition_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source.acquisition_run.id"), nullable=False
    )
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_object_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source.raw_object.id"), nullable=False
    )
    request_url: Mapped[str | None] = mapped_column(Text)
    request_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SourceRecordVersion(TimestampMixin, Base):
    __tablename__ = "source_record_version"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "native_key", "payload_sha256",
            name="uq_srv_source_native_payload",
        ),
        Index("ix_srv_source_native", "source_id", "native_key"),
        {"schema": "source"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: deterministic public id: sha256(source_id, native_key, payload_sha256)
    record_version_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_id: Mapped[str] = mapped_column(
        Text, ForeignKey("source.source.source_id"), nullable=False
    )
    native_key: Mapped[str] = mapped_column(Text, nullable=False)
    acquisition_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source.acquisition_run.id"), nullable=False
    )
    raw_object_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source.raw_object.id")
    )
    row_locator: Mapped[str | None] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source.source_record_version.id")
    )


# ---------------------------------------------------------------------------
# civic schema — identity + bitemporal ledger + snapshots
# ---------------------------------------------------------------------------


class PropertyIdentity(TimestampMixin, Base):
    __tablename__ = "property_identity"
    __table_args__ = {"schema": "civic"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: deterministic public property id from the authoritative identity seed
    property_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    identity_seed: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    seed_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False, default="authoritative")
    state: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    merged_into_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("civic.property_identity.id")
    )
    merge_reason: Mapped[str | None] = mapped_column(Text)


class ParcelVersion(TimestampMixin, Base):
    __tablename__ = "parcel_version"
    __table_args__ = (
        UniqueConstraint("apn", "record_version_id", name="uq_parcelver_apn_srv"),
        Index("ix_parcelver_property", "property_identity_id"),
        Index("ix_parcelver_apn", "apn"),
        Index(
            "ix_parcelver_geom", "geometry",
            postgresql_using="gist",
        ),
        {"schema": "civic"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    property_identity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("civic.property_identity.id"), nullable=False
    )
    apn: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    situs_address: Mapped[str | None] = mapped_column(Text)
    neighborhood: Mapped[str | None] = mapped_column(Text)
    struct_type: Mapped[str | None] = mapped_column(Text)
    damage_class: Mapped[str | None] = mapped_column(Text)
    units: Mapped[int | None] = mapped_column(Integer)
    pre_fire: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    center_lon: Mapped[float | None] = mapped_column(Float)
    center_lat: Mapped[float | None] = mapped_column(Float)
    geometry = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False))
    record_version_id: Mapped[str] = mapped_column(
        Text, ForeignKey("source.source_record_version.record_version_id"), nullable=False
    )
    observed_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("civic.parcel_version.id")
    )


class StructureVersion(TimestampMixin, Base):
    __tablename__ = "structure_version"
    __table_args__ = (
        Index("ix_structver_property", "property_identity_id"),
        {"schema": "civic"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    structure_id: Mapped[str] = mapped_column(Text, nullable=False)
    property_identity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("civic.property_identity.id"), nullable=False
    )
    source_native_id: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(Text)
    footprint = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False))
    record_version_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("source.source_record_version.record_version_id")
    )
    observed_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseLink(TimestampMixin, Base):
    __tablename__ = "case_link"
    __table_args__ = (
        UniqueConstraint(
            "subject_type", "subject_id", "object_type", "object_id", "link_type",
            name="uq_caselink_edge",
        ),
        Index("ix_caselink_subject", "subject_type", "subject_id"),
        Index("ix_caselink_object", "object_type", "object_id"),
        {"schema": "civic"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[str] = mapped_column(Text, nullable=False)
    link_type: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False, default="high")
    reviewer_state: Mapped[str] = mapped_column(Text, nullable=False, default="automatic")
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class RecoveryObservationRow(TimestampMixin, Base):
    __tablename__ = "recovery_observation"
    __table_args__ = (
        UniqueConstraint("observation_id", name="uq_observation_id"),
        Index("ix_obs_subject", "subject_type", "subject_id"),
        Index("ix_obs_lane_event", "lane", "event_type"),
        Index("ix_obs_observed_at", "observed_at"),
        CheckConstraint(
            "occurred_kind in ('exact','interval','unknown')",
            name="ck_obs_occurred_kind",
        ),
        {"schema": "civic"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    observation_id: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    lane: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_kind: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_earliest: Mapped[Date | None] = mapped_column(Date)
    occurred_latest: Mapped[Date | None] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_version_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("source.source_record_version.record_version_id")
    )
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    related_subjects: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ObservationRevision(TimestampMixin, Base):
    __tablename__ = "observation_revision"
    __table_args__ = (
        Index("ix_obsrev_target", "target_observation_id"),
        {"schema": "civic"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revision_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    target_observation_id: Mapped[str] = mapped_column(
        Text, ForeignKey("civic.recovery_observation.observation_id"), nullable=False
    )
    revision_type: Mapped[str] = mapped_column(Text, nullable=False)  # retraction|correction|supersession
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    replacement_observation_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("civic.recovery_observation.observation_id")
    )
    source_id: Mapped[str | None] = mapped_column(Text)
    revised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CivicSnapshot(TimestampMixin, Base):
    __tablename__ = "snapshot"
    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_snapshot_id"),
        {"schema": "civic"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: deterministic: sha256(ordered input run ids + policy versions + cutoff)
    snapshot_id: Mapped[str] = mapped_column(Text, nullable=False)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    code_commit: Mapped[str | None] = mapped_column(Text)
    input_runs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    input_runs_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    policy_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="building")
    staged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest_sha256: Mapped[str | None] = mapped_column(Text)


class SnapshotPropertyState(Base):
    """Snapshot-scoped materialization of the parallel-lane projection.

    A cached, policy-versioned VIEW over ``recovery_observation`` (never a
    replacement fact): rebuilding the same snapshot with the same policy
    version reproduces it byte-identically. Serves search, property summary,
    MVT, and community metrics without recomputing projections per request.
    """

    __tablename__ = "snapshot_property_state"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "property_id", name="uq_snapstate_property"),
        Index("ix_snapstate_snapshot", "snapshot_id"),
        Index("ix_snapstate_apn", "apn"),
        {"schema": "civic"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("civic.snapshot.snapshot_id"), nullable=False
    )
    property_id: Mapped[str] = mapped_column(Text, nullable=False)
    apn: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    neighborhood: Mapped[str | None] = mapped_column(Text)
    projection_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    lane_signals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    milestones: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_evidence_date: Mapped[Date | None] = mapped_column(Date)


class SnapshotMember(Base):
    __tablename__ = "snapshot_member"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "member_type", "member_id", name="uq_snapmember"),
        Index("ix_snapmember_snapshot", "snapshot_id"),
        {"schema": "civic"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("civic.snapshot.snapshot_id"), nullable=False
    )
    member_type: Mapped[str] = mapped_column(Text, nullable=False)
    member_id: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------------------
# analytics schema
# ---------------------------------------------------------------------------


class MetricDefinition(TimestampMixin, Base):
    __tablename__ = "metric_definition"
    __table_args__ = (
        UniqueConstraint("metric_id", "version", name="uq_metricdef_id_version"),
        {"schema": "analytics"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    metric_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    population: Mapped[str] = mapped_column(Text, nullable=False)
    numerator: Mapped[str] = mapped_column(Text, nullable=False)
    denominator: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    window: Mapped[str | None] = mapped_column(Text)
    inclusion_rules: Mapped[str | None] = mapped_column(Text)
    missingness_rules: Mapped[str | None] = mapped_column(Text)
    censoring_rules: Mapped[str | None] = mapped_column(Text)
    suppression_rules: Mapped[str | None] = mapped_column(Text)
    validation: Mapped[str | None] = mapped_column(Text)
    comparability_breaks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class MetricValue(TimestampMixin, Base):
    __tablename__ = "metric_value"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "metric_id", "version", "cohort_key",
            name="uq_metricvalue",
        ),
        Index("ix_metricvalue_snapshot", "snapshot_id"),
        {"schema": "analytics"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("civic.snapshot.snapshot_id"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    cohort: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cohort_key: Mapped[str] = mapped_column(Text, nullable=False, default="all")
    value: Mapped[float | None] = mapped_column(Float)
    interval_low: Mapped[float | None] = mapped_column(Float)
    interval_high: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    missing_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="computed")
    computation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ReconciliationResult(TimestampMixin, Base):
    __tablename__ = "reconciliation_result"
    __table_args__ = (
        Index("ix_recon_snapshot", "snapshot_id"),
        {"schema": "analytics"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("civic.snapshot.snapshot_id"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(Text, nullable=False)
    reference_source: Mapped[str] = mapped_column(Text, nullable=False)
    reference_definition: Mapped[str] = mapped_column(Text, nullable=False)
    reference_value: Mapped[float | None] = mapped_column(Float)
    our_value: Mapped[float | None] = mapped_column(Float)
    tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False)
    drift_pct: Mapped[float | None] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    samples: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


# ---------------------------------------------------------------------------
# ml schema
# ---------------------------------------------------------------------------


class DatasetVersion(TimestampMixin, Base):
    __tablename__ = "dataset_version"
    __table_args__ = (
        UniqueConstraint("dataset_id", name="uq_dataset_id"),
        {"schema": "ml"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("civic.snapshot.snapshot_id"), nullable=False
    )
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cohort_policy: Mapped[str] = mapped_column(Text, nullable=False)
    target_policy: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    label_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    split_policy: Mapped[str] = mapped_column(Text, nullable=False)
    object_uri: Mapped[str | None] = mapped_column(Text)
    object_sha256: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    leakage_audit: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sufficiency: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ExperimentRun(TimestampMixin, Base):
    __tablename__ = "experiment_run"
    __table_args__ = (
        UniqueConstraint("experiment_run_id", name="uq_experiment_run_id"),
        {"schema": "ml"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    experiment_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_id: Mapped[str] = mapped_column(
        Text, ForeignKey("ml.dataset_version.dataset_id"), nullable=False
    )
    mlflow_run_id: Mapped[str | None] = mapped_column(Text)
    model_family: Mapped[str] = mapped_column(Text, nullable=False)
    code_commit: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    config_sha256: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[int | None] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    artifacts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")


class ModelVersion(TimestampMixin, Base):
    __tablename__ = "model_version"
    __table_args__ = (
        UniqueConstraint("model_id", name="uq_model_id"),
        {"schema": "ml"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    experiment_run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("ml.experiment_run.experiment_run_id"), nullable=False
    )
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    training_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    horizon_days: Mapped[int | None] = mapped_column(Integer)
    limitations: Mapped[str | None] = mapped_column(Text)
    model_card: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class PredictionSet(TimestampMixin, Base):
    __tablename__ = "prediction_set"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prediction_set_id: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str | None] = mapped_column(Text, ForeignKey("ml.model_version.model_id"))
    insufficiency_reason: Mapped[str | None] = mapped_column(Text)
    dataset_id: Mapped[str | None] = mapped_column(Text, ForeignKey("ml.dataset_version.dataset_id"))
    snapshot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("civic.snapshot.snapshot_id"), nullable=False
    )
    target_signature: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    object_uri: Mapped[str | None] = mapped_column(Text)
    object_sha256: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="staged")

    __table_args__ = (
        UniqueConstraint("prediction_set_id", name="uq_prediction_set_id"),
        CheckConstraint(
            "(model_id is not null) or (insufficiency_reason is not null)",
            name="ck_predset_model_or_insufficiency",
        ),
        {"schema": "ml"},
    )


class PromotionDecision(TimestampMixin, Base):
    __tablename__ = "promotion_decision"
    __table_args__ = {"schema": "ml"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    decision_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    previous_champion_model_id: Mapped[str | None] = mapped_column(Text)
    proposed_model_id: Mapped[str] = mapped_column(
        Text, ForeignKey("ml.model_version.model_id"), nullable=False
    )
    gates: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    gate_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reviewer: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)  # promoted|rejected
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mlflow_run_id: Mapped[str | None] = mapped_column(Text)
    linkage_sha256: Mapped[str | None] = mapped_column(Text)


class Prediction(TimestampMixin, Base):
    __tablename__ = "prediction"
    __table_args__ = (
        UniqueConstraint(
            "prediction_set_id", "subject_type", "subject_id", "target",
            name="uq_prediction_row",
        ),
        Index("ix_prediction_subject", "subject_type", "subject_id"),
        {"schema": "ml"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prediction_set_id: Mapped[str] = mapped_column(
        Text, ForeignKey("ml.prediction_set.prediction_set_id"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    horizon_days: Mapped[int | None] = mapped_column(Integer)
    estimate: Mapped[float | None] = mapped_column(Float)
    interval_low: Mapped[float | None] = mapped_column(Float)
    interval_high: Mapped[float | None] = mapped_column(Float)
    basis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# spatial schema
# ---------------------------------------------------------------------------


class SpatialAsset(TimestampMixin, Base):
    __tablename__ = "spatial_asset"
    __table_args__ = (
        UniqueConstraint("asset_id", "version_id", name="uq_spatial_asset_version"),
        Index("ix_spatialasset_subject", "subject_type", "subject_id"),
        Index("ix_spatialasset_kind_slot", "asset_kind", "vintage_slot"),
        {"schema": "spatial"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    version_id: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_kind: Mapped[str] = mapped_column(Text, nullable=False)
    vintage_slot: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    horizontal_crs: Mapped[str | None] = mapped_column(Text)
    vertical_datum: Mapped[str | None] = mapped_column(Text)
    units: Mapped[str | None] = mapped_column(Text)
    transform: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    registration_residual_m: Mapped[float | None] = mapped_column(Float)
    acquisition_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acquisition_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observation_kind: Mapped[str] = mapped_column(Text, nullable=False)
    extent = mapped_column(Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False))
    resolution_m: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    lineage: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rights_state: Mapped[str] = mapped_column(Text, nullable=False, default="unresolved")
    object_uri: Mapped[str | None] = mapped_column(Text)
    object_sha256: Mapped[str | None] = mapped_column(Text)
    format_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="registered")


class AssetRelation(TimestampMixin, Base):
    __tablename__ = "asset_relation"
    __table_args__ = (
        UniqueConstraint(
            "from_asset_id", "from_version_id", "to_asset_id", "to_version_id", "relation",
            name="uq_asset_relation",
        ),
        {"schema": "spatial"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    from_asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    from_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    to_asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    to_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ObservationCandidate(TimestampMixin, Base):
    __tablename__ = "observation_candidate"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_candidate_id"),
        CheckConstraint(
            "review_state in ('pending','accepted','rejected','retracted')",
            name="ck_candidate_review_state",
        ),
        {"schema": "spatial"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(Text, nullable=False)
    proposing_run_id: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_version_id: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    region = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False))
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_event_type: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_occurred: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float)
    confidence_method: Mapped[str | None] = mapped_column(Text)
    coverage_fraction: Mapped[float | None] = mapped_column(Float)
    occlusion: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    registration_residual_m: Mapped[float | None] = mapped_column(Float)
    process_version: Mapped[str | None] = mapped_column(Text)
    rights_state: Mapped[str] = mapped_column(Text, nullable=False, default="unresolved")
    privacy_state: Mapped[str] = mapped_column(Text, nullable=False, default="unreviewed")
    review_state: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    reviewer: Mapped[str | None] = mapped_column(Text)
    review_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_observation_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("civic.recovery_observation.observation_id")
    )


# ---------------------------------------------------------------------------
# ops schema
# ---------------------------------------------------------------------------


class JobRun(TimestampMixin, Base):
    __tablename__ = "job_run"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_jobrun_idempotency"),
        Index("ix_jobrun_flow", "flow_name", "status"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_run_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    flow_name: Mapped[str] = mapped_column(Text, nullable=False)
    deployment_name: Mapped[str | None] = mapped_column(Text)
    prefect_flow_run_id: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    outputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    snapshot_id: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    failure_class: Mapped[str | None] = mapped_column(Text)
    log_uri: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Publication(TimestampMixin, Base):
    __tablename__ = "publication"
    __table_args__ = (
        UniqueConstraint("release_id", name="uq_publication_release"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: deterministic public release id from canonical manifest content
    release_id: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("civic.snapshot.snapshot_id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="fixture")
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    gate_results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="staged")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_by: Mapped[str | None] = mapped_column(Text)
    rolled_back_from_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ops.publication.id")
    )


class CurrentRelease(TimestampMixin, Base):
    """Single-row authority table for the current and last-known-good release.

    PostgreSQL is the SOLE visibility authority; the object-store pointer is a
    non-authoritative mirror repaired after commit (PUB-001).
    """

    __tablename__ = "current_release"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_current_release_singleton"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    current_release_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ops.publication.release_id")
    )
    lkg_release_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ops.publication.release_id")
    )


class CorrectionSubmission(TimestampMixin, Base):
    __tablename__ = "correction_submission"
    __table_args__ = (
        Index("ix_correction_state", "moderation_state"),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    release_id: Mapped[str] = mapped_column(Text, nullable=False)
    property_id: Mapped[str] = mapped_column(Text, nullable=False)
    claim_ref: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    moderation_state: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    moderation_reason: Mapped[str | None] = mapped_column(Text)
    moderated_by: Mapped[str | None] = mapped_column(Text)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resulting_revision_id: Mapped[str | None] = mapped_column(Text)


class CorrectionContact(TimestampMixin, Base):
    """Optional contact stored separately under restricted retention; never
    exported to public artifacts or model features."""

    __tablename__ = "correction_contact"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[str] = mapped_column(
        Text, ForeignKey("ops.correction_submission.submission_id"),
        unique=True, nullable=False,
    )
    contact: Mapped[str] = mapped_column(Text, nullable=False)
    retention_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


SCHEMAS = ("source", "civic", "analytics", "ml", "spatial", "ops")
