"""Temporal truth primitives.

Core invariant (openpali-one-shot/SYSTEM.md, "Truth and safety invariants"):
missing time is never replaced by the fire date, run date, or today.

``occurred``  — when the real-world event happened, as asserted by a source.
``observed_at`` — when OpenPali first acquired that assertion.
``source_updated_at`` / ``retrieved_at`` / ``processed_at`` stay separate and
live on acquisition-run records, not here.

An unknown occurrence time stays :class:`UnknownDate`. A partially known one is
an :class:`DateInterval` (interval censoring). There are deliberately no
constructors that default to "now", the fire date, or an acquisition time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Union


@dataclass(frozen=True, slots=True)
class ExactDate:
    """The source asserts the event occurred on this calendar date."""

    value: date

    def earliest(self) -> date:
        return self.value

    def latest(self) -> date:
        return self.value

    def to_json(self) -> dict:
        return {"kind": "exact", "date": self.value.isoformat()}


@dataclass(frozen=True, slots=True)
class DateInterval:
    """The event occurred inside [earliest_date, latest_date] (inclusive).

    ``latest_date`` may be ``None`` for a right-open bound ("on or after
    earliest"), which is how "we first saw the completed state on date D but do
    not know when it was reached" must be represented when a source gives a
    lower bound only. ``earliest_date`` may be ``None`` for "on or before
    latest". At least one bound must be present.
    """

    earliest_date: date | None
    latest_date: date | None

    def __post_init__(self) -> None:
        if self.earliest_date is None and self.latest_date is None:
            raise ValueError("DateInterval requires at least one bound; use UnknownDate")
        if (
            self.earliest_date is not None
            and self.latest_date is not None
            and self.earliest_date > self.latest_date
        ):
            raise ValueError("DateInterval earliest_date is after latest_date")

    def earliest(self) -> date | None:
        return self.earliest_date

    def latest(self) -> date | None:
        return self.latest_date

    def to_json(self) -> dict:
        return {
            "kind": "interval",
            "earliest": self.earliest_date.isoformat() if self.earliest_date else None,
            "latest": self.latest_date.isoformat() if self.latest_date else None,
        }


@dataclass(frozen=True, slots=True)
class UnknownDate:
    """The source asserts the event but supplies no usable occurrence time."""

    def earliest(self) -> None:
        return None

    def latest(self) -> None:
        return None

    def to_json(self) -> dict:
        return {"kind": "unknown"}


OccurrenceTime = Union[ExactDate, DateInterval, UnknownDate]


def occurrence_from_source_date(value: date | None) -> OccurrenceTime:
    """Standard mapping from an optional source-supplied date.

    ``None`` maps to :class:`UnknownDate` — never to a fabricated constant.
    """

    return ExactDate(value) if value is not None else UnknownDate()


def occurrence_to_json(value: OccurrenceTime) -> dict:
    return value.to_json()


def occurrence_from_json(payload: dict) -> OccurrenceTime:
    kind = payload.get("kind")
    if kind == "exact":
        return ExactDate(date.fromisoformat(payload["date"]))
    if kind == "interval":
        raw_earliest = payload.get("earliest")
        raw_latest = payload.get("latest")
        return DateInterval(
            date.fromisoformat(raw_earliest) if raw_earliest else None,
            date.fromisoformat(raw_latest) if raw_latest else None,
        )
    if kind == "unknown":
        return UnknownDate()
    raise ValueError(f"unknown occurrence encoding: {payload!r}")
