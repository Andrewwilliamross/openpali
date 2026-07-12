"""Corrections and retractions.

Evidence is append-only: a correction never mutates or deletes the original
observation. A :class:`Retraction` targets one observation ID; applying
retractions yields the active set for projection while the full audit trail
(original + retraction) remains available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .observations import RecoveryObservation


@dataclass(frozen=True, slots=True)
class Retraction:
    target_observation_id: str
    reason: str
    retracted_at: datetime
    source: str

    def to_json(self) -> dict:
        return {
            "target_observation_id": self.target_observation_id,
            "reason": self.reason,
            "retracted_at": self.retracted_at.isoformat(),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class RevisionResult:
    active: tuple[RecoveryObservation, ...]
    retracted: tuple[RecoveryObservation, ...]
    dangling_retractions: tuple[Retraction, ...]


def apply_retractions(
    observations: list[RecoveryObservation],
    retractions: list[Retraction],
) -> RevisionResult:
    """Split observations into active and retracted sets.

    A retraction that targets no known observation is *dangling* and must be
    surfaced (it may indicate a mixed snapshot); it never fails silently.
    """

    targets = {r.target_observation_id for r in retractions}
    active: list[RecoveryObservation] = []
    retracted: list[RecoveryObservation] = []
    seen: set[str] = set()
    for observation in observations:
        seen.add(observation.observation_id)
        if observation.observation_id in targets:
            retracted.append(observation)
        else:
            active.append(observation)
    dangling = tuple(r for r in retractions if r.target_observation_id not in seen)
    return RevisionResult(
        active=tuple(active),
        retracted=tuple(retracted),
        dangling_retractions=dangling,
    )
