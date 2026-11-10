"""The recovery ladder: the stages a parcel's rebuild moves through, and where
each sits on the map's colour ramp. No I/O."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ladder:
    """A monotonic progression: a subject only ever moves up the ladder.

    Recovery stages are projected from many independent agency sources; the
    strongest evidence wins and weaker later evidence never moves a parcel
    backwards.
    """

    name: str
    description: str
    order: tuple[str, ...]

    @property
    def states(self) -> frozenset[str]:
        return frozenset(self.order)

    def rank(self, state: str) -> int:
        return self.order.index(state)

    def advance(self, current: str, candidate: str) -> str:
        return candidate if self.rank(candidate) > self.rank(current) else current


RECOVERY_STAGE = Ladder(
    "recovery_stage",
    "Highest agency-reported recovery milestone for a parcel's primary home.",
    (
        "unknown",
        "cleanup",
        "application",
        "design",
        "permit",
        "construction",
        "construction_complete",
        "occupancy",
    ),
)

#: Where each rung of the recovery ladder sits on the map's 0-100 colour ramp.
#: A display position for an evidenced milestone, not a prediction or a
#: quality judgment: it carries no information the stage does not. Only
#: parcels with a destroyed-structure assessment are scored (see
#: ``rebuild_score``); "no score" is different from a score of 0.
REBUILD_SCORE: dict[str, int] = {
    "unknown": 0,
    "cleanup": 8,
    "application": 15,
    "design": 30,
    "permit": 40,
    "construction": 60,
    "construction_complete": 92,
    "occupancy": 100,
}


def rebuild_score(stage: str, damage: str) -> int | None:
    if damage != "destroyed":
        return None
    return REBUILD_SCORE.get(stage, REBUILD_SCORE["unknown"])
