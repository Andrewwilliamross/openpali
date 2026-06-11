"""Run provenance: which source fetched what, when, and what shape it had.

Every upstream request (via http.cached_get_json) lands here as a FetchRecord
tagged with the logical source that made it (see sources.py). At emit time the
registry is summarized into meta.json so every published number can be traced
to the exact raw bytes (sha256), query, and fetch time that produced it.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping

UNATTRIBUTED = "unattributed"


@dataclass
class FetchRecord:
    source: str
    url: str
    params: dict[str, Any] | None
    sha256: str
    bytes: int
    fetched_at: str  # ISO-8601 UTC; for cache hits this is the cache file's mtime
    cache_hit: bool


_records: list[FetchRecord] = []
_stats: dict[str, dict[str, Any]] = {}
_current_source = UNATTRIBUTED


def reset() -> None:
    _records.clear()
    _stats.clear()
    global _current_source
    _current_source = UNATTRIBUTED


@contextmanager
def source(name: str) -> Iterator[None]:
    """Tag every fetch inside the block with the logical source `name`."""
    global _current_source
    prev = _current_source
    _current_source = name
    try:
        yield
    finally:
        _current_source = prev


def add(url: str, params: dict[str, Any] | None, text: str, *,
        fetched_at: str, cache_hit: bool) -> None:
    _records.append(FetchRecord(
        source=_current_source,
        url=url,
        params=params,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        bytes=len(text),
        fetched_at=fetched_at,
        cache_hit=cache_hit,
    ))


def records(source_id: str | None = None) -> list[FetchRecord]:
    return [r for r in _records if source_id is None or r.source == source_id]


def set_stats(source_id: str, **kv: Any) -> None:
    """Merge source-level facts (row counts, parse stats, schema fingerprint…)."""
    _stats.setdefault(source_id, {}).update(kv)


def get_stats(source_id: str) -> dict[str, Any]:
    return dict(_stats.get(source_id, {}))


def latest_fetch(source_id: str | None = None) -> str | None:
    recs = records(source_id)
    return max((r.fetched_at for r in recs), default=None)


def summarize(source_id: str) -> dict[str, Any]:
    """Aggregate the per-request records of one source into meta.json fields.

    The combined sha256 hashes the sorted set of page hashes, so it is stable
    across pagination order and identical for byte-identical re-fetches.
    """
    recs = records(source_id)
    combined = hashlib.sha256("\n".join(sorted(r.sha256 for r in recs)).encode()).hexdigest()
    return {
        "requests": len(recs),
        "bytes": sum(r.bytes for r in recs),
        "cache_hits": sum(1 for r in recs if r.cache_hit),
        "sha256": combined if recs else None,
        "first_fetch": min((r.fetched_at for r in recs), default=None),
        "last_fetch": max((r.fetched_at for r in recs), default=None),
    }


_JSON_TYPES: list[tuple[type, str]] = [
    (bool, "bool"),  # before int — bool is an int subclass
    (int, "int"),
    (float, "float"),
    (str, "str"),
    (list, "list"),
    (dict, "dict"),
]


def _json_type(v: Any) -> str:
    if v is None:
        return "null"
    for t, name in _JSON_TYPES:
        if isinstance(v, t):
            return name
    return type(v).__name__


def schema_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str | None:
    """Order-insensitive hash of the field set + observed value types.

    Changes when upstream adds/removes/renames fields or shifts a field's type
    — the early-warning signal for silent schema drift.
    """
    fields: dict[str, set[str]] = {}
    n = 0
    for row in rows:
        n += 1
        for k, v in row.items():
            fields.setdefault(k, set()).add(_json_type(v))
    if n == 0:
        return None
    canon = json.dumps(sorted((k, "|".join(sorted(ts))) for k, ts in fields.items()))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]
