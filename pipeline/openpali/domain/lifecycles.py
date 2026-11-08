"""Every lifecycle in OpenPali, declared in one place. No I/O.

Status strings used to be scattered across writers (``row.status = "..."``)
with the legal order living only in each author's head. This module is the
single source of truth for which states exist and which moves are legal:

- humans read it as documentation (``python -m openpali.domain.lifecycles``
  prints every machine);
- code calls :meth:`Lifecycle.require` before persisting a move;
- agents and API clients get ``allowed_next`` from the task API instead of
  guessing, and a 409 naming the legal moves when they guess wrong.

A self-transition (``a -> a``) is always legal and means "no change"; writers
use it to make retries idempotent.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class IllegalTransition(ValueError):
    """A writer attempted a move its lifecycle does not declare."""

    def __init__(self, lifecycle: "Lifecycle", current: str | None, target: str):
        self.lifecycle = lifecycle.name
        self.current = current
        self.target = target
        self.allowed = sorted(lifecycle.allowed(current))
        where = f"from {current!r}" if current is not None else "as an initial state"
        super().__init__(
            f"{lifecycle.name}: cannot move {where} to {target!r}; "
            f"allowed: {', '.join(self.allowed) or 'none (terminal)'}"
        )


@dataclass(frozen=True)
class Lifecycle:
    name: str
    description: str
    initial: frozenset[str]
    transitions: dict[str, frozenset[str]] = field(default_factory=dict)

    @property
    def states(self) -> frozenset[str]:
        found = set(self.initial) | set(self.transitions)
        for targets in self.transitions.values():
            found |= targets
        return frozenset(found)

    @property
    def terminal(self) -> frozenset[str]:
        return frozenset(s for s in self.states if not self.transitions.get(s))

    def allowed(self, current: str | None) -> frozenset[str]:
        """Legal next states; ``None`` means the subject has no state yet."""
        if current is None:
            return self.initial
        return self.transitions.get(current, frozenset())

    def can(self, current: str | None, target: str) -> bool:
        return target == current or target in self.allowed(current)

    def require(self, current: str | None, target: str) -> str:
        if current is not None and current not in self.states:
            raise IllegalTransition(self, current, target)
        if not self.can(current, target):
            raise IllegalTransition(self, current, target)
        return target

    def describe(self) -> dict:
        return dict(
            name=self.name,
            description=self.description,
            initial=sorted(self.initial),
            transitions={s: sorted(self.transitions.get(s, ())) for s in sorted(self.states)},
            terminal=sorted(self.terminal),
        )


def _machine(name: str, description: str, initial, transitions) -> Lifecycle:
    return Lifecycle(
        name=name,
        description=description,
        initial=frozenset(initial),
        transitions={k: frozenset(v) for k, v in transitions.items()},
    )


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

    def describe(self) -> dict:
        return dict(name=self.name, description=self.description, order=list(self.order))


# --- evidence workspace (local SQLite drafts; user- and agent-driven) -------

ACQUISITION_TASK = _machine(
    "acquisition_task",
    "An evidence gap on a parcel. Released as 'open'; local workspace events "
    "move it through collection and review. Never changes agency evidence.",
    initial={"open"},
    transitions={
        "open": {"queued", "in_progress"},
        "queued": {"in_progress"},
        "in_progress": {"needs_review"},
        "needs_review": {"in_progress"},
    },
)

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

# --- canonical PostGIS platform ---------------------------------------------

ACQUISITION_RUN = _machine(
    "acquisition_run",
    "One source fetch. A failed run with the same deterministic id is retried in place.",
    initial={"pending", "running"},
    transitions={
        "pending": {"running"},
        "running": {"succeeded", "failed"},
        "failed": {"running"},
    },
)

CIVIC_SNAPSHOT = _machine(
    "civic_snapshot",
    "Frozen membership of acquisition runs at a cutoff.",
    initial={"building"},
    transitions={"building": {"built"}, "built": {"published"}},
)

PUBLICATION = _machine(
    "publication",
    "A release manifest. Only 'published' rows are servable; the CURRENT "
    "pointer is a separate singleton. Rollback swaps current and LKG.",
    initial={"staged", "failed_gates"},
    transitions={
        "staged": {"published"},
        "failed_gates": {"published"},
        "published": {"superseded", "rolled_back"},
        "superseded": {"published"},
        "rolled_back": {"published"},
    },
)

JOB_RUN = _machine(
    "job_run",
    "One orchestrated flow attempt keyed by idempotency key; failures retry in place.",
    initial={"running"},
    transitions={"running": {"succeeded", "failed"}, "failed": {"running"}},
)

LIFECYCLES: dict[str, Lifecycle] = {
    m.name: m for m in (ACQUISITION_TASK, ACQUISITION_RUN, CIVIC_SNAPSHOT, PUBLICATION, JOB_RUN)
}
LADDERS: dict[str, Ladder] = {RECOVERY_STAGE.name: RECOVERY_STAGE}


def catalog() -> dict:
    return dict(
        lifecycles={k: m.describe() for k, m in LIFECYCLES.items()},
        ladders={k: m.describe() for k, m in LADDERS.items()},
    )


if __name__ == "__main__":
    import json

    print(json.dumps(catalog(), indent=2))
