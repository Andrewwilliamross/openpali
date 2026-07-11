#!/usr/bin/env python3
"""Persist a public-data-only run manifest and transcript inside the task silo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = Path(
    os.environ.get("OPENPALI_RUNS_ROOT") or TASK_ROOT / "state" / "runs"
).resolve()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def git(cwd: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def transcript_metrics(path: Path) -> dict[str, Any]:
    models: set[str] = set()
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    observed_costs: list[float] = []
    parse_errors = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            for item in walk(record):
                model = item.get("model")
                if isinstance(model, str) and model.startswith("claude-"):
                    models.add(model)
                item_usage = item.get("usage")
                if isinstance(item_usage, dict):
                    for key in usage:
                        count = item_usage.get(key)
                        if isinstance(count, int) and count >= 0:
                            usage[key] += count
                for key in ("total_cost_usd", "cost_usd", "costUSD"):
                    cost = item.get(key)
                    if isinstance(cost, (int, float)) and cost >= 0:
                        observed_costs.append(float(cost))
    return {
        "actual_models_observed": sorted(models),
        "token_usage_observed_unDeduplicated": usage,
        "cost_values_observed_usd": observed_costs,
        "parse_errors": parse_errors,
    }


def record_launch(session_id: str, mode: str, budget: str | None) -> int:
    repo = TASK_ROOT.parent
    manifest_path = RUNS_ROOT / session_id / "manifest.json"
    manifest = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "mode": mode,
        "requested_model": "claude-fable-5",
        "requested_effort": "xhigh",
        "max_budget_usd": budget,
        "launcher_started_at": now(),
        "launch_repo": str(repo),
        "launch_head": git(repo, "rev-parse", "HEAD"),
        "launch_branch": git(repo, "branch", "--show-current"),
        "launch_remote_default": git(repo, "symbolic-ref", "refs/remotes/origin/HEAD"),
        "launch_remote_head": git(repo, "rev-parse", "refs/remotes/origin/HEAD"),
        "claude_code_version": subprocess.run(
            ["claude", "--version"], text=True, capture_output=True, check=False
        ).stdout.strip(),
        "tool_surface": [
            "Bash", "Edit", "Read", "Write", "Grep", "Glob", "Agent",
            "WebFetch", "WebSearch",
        ],
        "fallback_model": None,
        "lifecycle": [],
    }
    atomic_json(manifest_path, manifest)
    print(f"OPENPALI_SESSION_ID: {session_id}")
    print(f"OPENPALI_RUN_MANIFEST: {manifest_path}")
    return 0


def handle_event(event: dict[str, Any]) -> int:
    session_id = str(event.get("session_id") or "unknown-session")
    event_name = str(event.get("hook_event_name") or "unknown")
    cwd = Path(str(event.get("cwd") or Path.cwd())).resolve()
    top_level = git(cwd, "rev-parse", "--show-toplevel")
    project = Path(top_level).resolve() if top_level else cwd
    run_dir = RUNS_ROOT / session_id
    manifest_path = run_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    manifest.setdefault("schema_version", "1.0.0")
    manifest.setdefault("session_id", session_id)
    manifest.setdefault("requested_model", "claude-fable-5")
    manifest.setdefault("requested_effort", "xhigh")
    lifecycle = manifest.setdefault("lifecycle", [])
    if isinstance(lifecycle, list):
        lifecycle.append({
            "event": event_name,
            "source": event.get("source"),
            "at": now(),
        })

    manifest["event_cwd_latest"] = str(cwd)
    manifest["worktree_path"] = str(project)
    manifest["current_head"] = git(project, "rev-parse", "HEAD")
    manifest["current_branch"] = git(project, "branch", "--show-current")

    if event_name == "SessionStart":
        manifest.setdefault("session_started_at", now())
        manifest["transcript_path_runtime"] = str(event.get("transcript_path") or "")
        atomic_json(manifest_path, manifest)
        return 0

    if event_name != "SessionEnd":
        atomic_json(manifest_path, manifest)
        return 0

    manifest["session_ended_at"] = now()
    manifest["end_reason"] = event.get("reason")
    manifest["final_head"] = git(project, "rev-parse", "HEAD")
    manifest["final_branch"] = git(project, "branch", "--show-current")
    status = git(project, "status", "--porcelain=v1", "--untracked-files=all")
    manifest["final_worktree_clean"] = status == ""
    manifest["final_status_porcelain"] = status
    started = manifest.get("launcher_started_at")
    if isinstance(started, str):
        try:
            beginning = datetime.fromisoformat(started)
            manifest["wall_time_seconds"] = round(
                (datetime.now(timezone.utc) - beginning).total_seconds(), 3
            )
        except ValueError:
            manifest["wall_time_seconds"] = None

    raw_transcript = Path(str(event.get("transcript_path") or "")).expanduser()
    if raw_transcript.is_file():
        run_dir.mkdir(parents=True, exist_ok=True)
        archived = run_dir / "transcript.jsonl"
        shutil.copy2(raw_transcript, archived)
        manifest["transcript_archive"] = str(archived)
        manifest["transcript_bytes"] = archived.stat().st_size
        manifest["transcript_sha256"] = sha256(archived)
        manifest["observability"] = transcript_metrics(archived)
    else:
        manifest["transcript_archive_error"] = "runtime transcript was unavailable"

    atomic_json(manifest_path, manifest)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", nargs=2, metavar=("SESSION_ID", "MODE"))
    parser.add_argument("--budget")
    args = parser.parse_args()
    if args.launch:
        return record_launch(args.launch[0], args.launch[1], args.budget)
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return 0
    return handle_event(event if isinstance(event, dict) else {})


if __name__ == "__main__":
    raise SystemExit(main())
