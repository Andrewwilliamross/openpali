"""Durable run + data-quality records (a lakehouse table) and alerting.

ADR 0001, Decision 4: the oracle reconciliation and spatial anomalies — the most
valuable signals in the pipeline — used to `print()` to stdout and vanish. This module
appends them as rows to a date-partitioned Parquet table under `data/runs/`, queryable
with DuckDB, and fires an alert when something drifts.

    SELECT ts, n_failing, metrics
    FROM read_parquet('data/runs/reconciliation/**/*.parquet')
    ORDER BY ts DESC;

Kept dependency-light on purpose: pyarrow (already a pipeline dep) for the table, httpx
(already a dep) for an optional Slack webhook. No always-on infra (ADR 0001, Decision 2).
"""

from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

RUNS_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "runs"

_SCALAR = (int, float, str, bool)


def record(table: str, row: dict[str, Any], *, runs_dir: pathlib.Path | None = None) -> pathlib.Path:
    """Append one row to data/runs/<table>/dt=<YYYY-MM-DD>/<ts>.parquet.

    Non-scalar values are stored as JSON strings so the table keeps a stable, flat
    schema across runs (DuckDB reads the partitioned dataset transparently).
    """
    now = datetime.now(timezone.utc)
    base = (runs_dir or RUNS_DIR) / table / f"dt={now.date().isoformat()}"
    base.mkdir(parents=True, exist_ok=True)
    flat = {"ts": now.isoformat()}
    for k, v in row.items():
        flat[k] = v if (v is None or isinstance(v, _SCALAR)) else json.dumps(v, default=str)
    path = base / f"{now.strftime('%Y%m%dT%H%M%S%f')}-{os.getpid()}.parquet"
    pq.write_table(pa.Table.from_pylist([flat]), path, compression="zstd")
    return path


def alert(message: str, *, severity: str = "warning", context: dict[str, Any] | None = None) -> None:
    """Surface a data-quality event. Always logs; posts to Slack if OPENPALI_SLACK_WEBHOOK is set.

    Alerting must never break a run — every failure path is swallowed.
    """
    line = f"[openpali:{severity}] {message}"
    print(line)
    webhook = os.environ.get("OPENPALI_SLACK_WEBHOOK")
    if not webhook:
        return
    try:
        import httpx

        text = line
        if context:
            text += "\n```" + json.dumps(context, indent=1, default=str)[:3500] + "```"
        httpx.post(webhook, json={"text": text}, timeout=10.0)
    except Exception as e:  # noqa: BLE001 - alerting is best-effort
        print(f"[openpali:alert-failed] {e}")
