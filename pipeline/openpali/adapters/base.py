"""The narrow source-adapter contract.

``online=False`` prohibits constructing or invoking any network client: the
offline path replays exact raw bytes (hash-verified) and fails immediately on
missing input. Source errors are typed — they are never converted into empty
successful datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Protocol


class AcquisitionError(Exception):
    """Typed acquisition failure. ``failure_class`` drives retry policy:
    only ``transient`` may be retried; semantic/schema/rights failures fail
    the run immediately."""

    failure_class = "semantic"


class TransientAcquisitionError(AcquisitionError):
    failure_class = "transient"


class SchemaDriftError(AcquisitionError):
    failure_class = "schema_drift"


class SourceMutationError(AcquisitionError):
    """The source changed while paging (count/page instability)."""

    failure_class = "mutation_during_acquisition"


class OfflineInputError(AcquisitionError):
    failure_class = "offline_input_missing"


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    online: bool
    parameters: dict = field(default_factory=dict)
    #: offline replay inputs: ordered (sha256, byte_size) of raw page objects
    raw_page_hashes: tuple[tuple[str, int], ...] = ()
    expected_schema_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class RawPage:
    index: int
    url: str
    params: dict
    body: bytes
    sha256: str
    retrieved_at: datetime


@dataclass(slots=True)
class RawAcquisition:
    source_id: str
    request: AcquisitionRequest
    pages: list[RawPage]
    requested_at: datetime
    retrieved_at: datetime | None
    upstream_edited_at: datetime | None
    record_count: int
    schema_fingerprint: str | None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceRecord:
    native_key: str
    payload: dict
    page_index: int


class SourceAdapter(Protocol):
    source_id: str
    title: str
    jurisdiction: str
    terms_reference: str

    def acquire(self, request: AcquisitionRequest) -> RawAcquisition: ...

    def normalize(self, raw: RawAcquisition) -> Iterable[SourceRecord]: ...

    def health(self, raw: RawAcquisition) -> dict: ...
