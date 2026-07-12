"""Typed domain errors. Publication paths fail closed on these."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for semantic failures that must block publication."""


class UndocumentedDomainValue(DomainError):
    """A source field carried a value outside the documented, evidence-backed
    domain. Never guess a meaning; surface and fail closed."""

    def __init__(self, source_id: str, field: str, value: object) -> None:
        self.source_id = source_id
        self.field = field
        self.value = value
        super().__init__(
            f"undocumented value for {source_id}.{field}: {value!r} — "
            "publication must fail closed until the taxonomy documents it"
        )


class FabricatedTimeError(DomainError):
    """Guard rail: a code path attempted to substitute a fabricated constant
    (fire date, run date, today) for a missing occurrence time."""
