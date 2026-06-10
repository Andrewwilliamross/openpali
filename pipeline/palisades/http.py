"""Cached, retrying HTTP fetch layer.

Every upstream request flows through cached_get_json so that:
- re-runs during development don't hammer public agency APIs
- the pipeline can run fully offline against the cache
- each artifact records when its source data was actually fetched
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
USER_AGENT = "PalisadesRebuildTracker/0.1 (open-source civic project; respring.ai)"

_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(60.0, connect=20.0),
            follow_redirects=True,
        )
    return _client


def _cache_path(url: str, params: dict[str, Any] | None) -> Path:
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return RAW_DIR / f"{digest}.json"


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, max=30))
def _get(url: str, params: dict[str, Any] | None) -> Any:
    resp = client().get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def cached_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    ttl_hours: float = 12.0,
    sleep: float = 0.2,
) -> Any:
    """GET JSON with an on-disk cache. ttl_hours<=0 forces a refetch."""
    path = _cache_path(url, params)
    if path.exists() and ttl_hours > 0:
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if age_hours < ttl_hours:
            return json.loads(path.read_text())
    data = _get(url, params)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    time.sleep(sleep)  # be polite to public agency servers
    return data
