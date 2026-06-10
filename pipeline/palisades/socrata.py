"""Socrata SODA API helpers (data.lacity.org, data.lacounty.gov)."""

from __future__ import annotations

from typing import Any

from .http import cached_get_json


def fetch_all(
    domain: str,
    dataset_id: str,
    *,
    where: str | None = None,
    select: str | None = None,
    order: str | None = ":id",
    page_size: int = 5000,
    max_rows: int = 500_000,
    ttl_hours: float = 12.0,
) -> list[dict[str, Any]]:
    """Fetch all rows of a SODA dataset matching $where, paging with $offset."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while offset < max_rows:
        params: dict[str, Any] = {"$limit": page_size, "$offset": offset}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
        if order:
            params["$order"] = order
        batch = cached_get_json(
            f"https://{domain}/resource/{dataset_id}.json", params, ttl_hours=ttl_hours
        )
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def count(domain: str, dataset_id: str, where: str | None = None, *, ttl_hours: float = 12.0) -> int:
    params: dict[str, Any] = {"$select": "count(*) as n"}
    if where:
        params["$where"] = where
    data = cached_get_json(
        f"https://{domain}/resource/{dataset_id}.json", params, ttl_hours=ttl_hours
    )
    return int(data[0]["n"]) if data else 0
