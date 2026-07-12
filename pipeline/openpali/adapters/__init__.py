"""Source adapters behind one narrow acquisition contract (DATA-001)."""

from .base import (
    AcquisitionError,
    AcquisitionRequest,
    RawAcquisition,
    RawPage,
    SchemaDriftError,
    SourceAdapter,
    SourceMutationError,
    SourceRecord,
)

__all__ = [
    "AcquisitionError",
    "AcquisitionRequest",
    "RawAcquisition",
    "RawPage",
    "SchemaDriftError",
    "SourceAdapter",
    "SourceMutationError",
    "SourceRecord",
]
