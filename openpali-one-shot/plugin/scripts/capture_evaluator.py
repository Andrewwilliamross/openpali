#!/usr/bin/env python3
"""Capture a transcript-bound evaluator result and a fail-closed attestation."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from evaluator_protocol import (
    home_relative_locator,
    parse_evaluator_message,
    sha256_bytes,
    sha256_file,
    transcript_contains_message,
)


EVALUATOR = "openpali-independent-evaluator"


def is_evaluator(agent_type: str) -> bool:
    return agent_type in {EVALUATOR, f"openpali-one-shot:{EVALUATOR}"}


def git(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        print("Evaluator capture rejected malformed hook input", file=sys.stderr)
        return 2

    if event.get("hook_event_name") not in (None, "SubagentStop"):
        return 0
    agent_type = str(event.get("agent_type") or "")
    if not is_evaluator(agent_type):
        return 0

    project = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or str(event.get("cwd") or Path.cwd())
    ).resolve()
    state = project / "openpali-one-shot" / "state"
    evaluator_archive = state / "evaluator"
    contract_path = project / "openpali-one-shot" / "contract" / "acceptance.json"
    capture_errors: list[str] = []

    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        expected_ids = [
            item["id"]
            for item in contract["criteria"]
            if item.get("priority") == "MUST"
        ]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"Evaluator capture cannot load acceptance contract: {exc}", file=sys.stderr)
        return 2

    root_result = git(project, "rev-parse", "--show-toplevel")
    head_result = git(project, "rev-parse", "HEAD")
    status_result = git(project, "status", "--porcelain=v1", "--untracked-files=all")
    if root_result.returncode or Path(root_result.stdout.strip()).resolve() != project:
        capture_errors.append("CLAUDE_PROJECT_DIR is not the Git worktree root")
    release_commit = head_result.stdout.strip()
    if head_result.returncode or not re.fullmatch(r"[a-f0-9]{40}", release_commit):
        capture_errors.append("could not resolve a full release-candidate commit")
    if status_result.returncode or status_result.stdout:
        capture_errors.append("evaluator must run against a clean release-candidate worktree")

    message = str(event.get("last_assistant_message") or "").strip()
    parsed, protocol_errors = parse_evaluator_message(message, expected_ids)
    capture_errors.extend(protocol_errors)
    contract_sha256 = sha256_file(contract_path)
    if parsed.get("commit") != release_commit:
        capture_errors.append("evaluator COMMIT does not equal the clean checked-out HEAD")
    if parsed.get("contract_sha256") != contract_sha256:
        capture_errors.append("evaluator CONTRACT_SHA256 does not equal the immutable contract")

    session_id = str(event.get("session_id") or "")
    agent_id = str(event.get("agent_id") or "")
    if not session_id:
        capture_errors.append("SubagentStop omitted session_id")
    if not agent_id:
        capture_errors.append("SubagentStop omitted agent_id")

    parent_transcript_raw = str(event.get("transcript_path") or "")
    parent_transcript = Path(parent_transcript_raw)
    agent_transcript = Path(str(event.get("agent_transcript_path") or ""))
    parent_locator = home_relative_locator(parent_transcript) if parent_transcript_raw else None
    agent_locator = home_relative_locator(agent_transcript) if str(agent_transcript) else None
    if parent_locator is None:
        capture_errors.append("parent transcript is absent or outside HOME")
    elif not parent_transcript.is_file() or parent_transcript.is_symlink():
        capture_errors.append("parent transcript does not exist as a regular file")
    if agent_locator is None:
        capture_errors.append("agent transcript is absent or outside HOME")
    if not agent_transcript.is_file() or agent_transcript.is_symlink():
        capture_errors.append("agent transcript does not exist as a regular file")
        agent_transcript_sha256 = ""
        agent_transcript_size = 0
    else:
        agent_transcript_sha256 = sha256_file(agent_transcript)
        agent_transcript_size = agent_transcript.stat().st_size
        if not transcript_contains_message(agent_transcript, message):
            capture_errors.append("exact evaluator response was not found in the agent transcript")

    # SubagentStop exit 2 asks the evaluator to correct its final response. Do
    # not dirty the release candidate on a rejected attempt, or a correct retry
    # could never satisfy the clean-at-capture invariant.
    if capture_errors:
        print("Evaluator capture rejected:", file=sys.stderr)
        for error in capture_errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    state.mkdir(parents=True, exist_ok=True)
    evaluator_archive.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_agent_id = re.sub(r"[^A-Za-z0-9_-]", "_", agent_id or "unknown")[:80]
    archive_relative = f"openpali-one-shot/state/evaluator/evaluator-{stamp}-{safe_agent_id}.md"
    archive_attestation_relative = (
        f"openpali-one-shot/state/evaluator/evaluator-{stamp}-{safe_agent_id}.attestation.json"
    )
    output_relative = "openpali-one-shot/state/evaluator-latest.md"
    content = (message + "\n").encode("utf-8")
    attestation = {
        "attestation_version": "1.0.0",
        "valid": True,
        "capture_errors": [],
        "captured_at": captured_at,
        "parent_session_id": session_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "parent_transcript": parent_locator,
        "agent_transcript": agent_locator,
        "agent_transcript_sha256": agent_transcript_sha256,
        "agent_transcript_size": agent_transcript_size,
        "release_candidate_commit": release_commit,
        "contract_sha256": contract_sha256,
        "verdict": parsed.get("verdict"),
        "confidence": parsed.get("confidence"),
        "must_results": parsed.get("must_results", {}),
        "message_sha256": sha256_bytes(content),
        "output_path": output_relative,
        "archive_path": archive_relative,
        "archive_attestation_path": archive_attestation_relative,
    }
    attestation_bytes = (json.dumps(attestation, indent=2, sort_keys=True) + "\n").encode("utf-8")

    atomic_write(project / output_relative, content)
    atomic_write(project / archive_relative, content)
    atomic_write(state / "evaluator-attestation.json", attestation_bytes)
    atomic_write(project / archive_attestation_relative, attestation_bytes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
