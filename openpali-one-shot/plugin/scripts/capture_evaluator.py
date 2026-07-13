#!/usr/bin/env python3
"""Capture and attest the fresh evaluator's exact result at a clean candidate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVALUATOR_NAMES = {
    "openpali-independent-evaluator",
    "openpali-one-shot:openpali-independent-evaluator",
}
HEADER_PATTERNS = {
    "verdict": re.compile(r"^VERDICT: (PASS|FAIL)$", re.MULTILINE),
    "commit": re.compile(r"^COMMIT: ([a-f0-9]{40})$", re.MULTILINE),
    "contract_sha256": re.compile(r"^CONTRACT_SHA256: ([a-f0-9]{64})$", re.MULTILINE),
    "confidence": re.compile(r"^CONFIDENCE: (high|medium|low)$", re.MULTILINE),
}
MUST_RESULT = re.compile(r"^- ([A-Z][A-Z0-9-]{2,63}): (PASS|FAIL) — .+$", re.MULTILINE)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def transcript_contains(path: Path, target: str) -> bool:
    def strings(value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if any(candidate.strip() == target for candidate in strings(value)):
                return True
    except OSError:
        return False
    return False


def home_locator(path: Path) -> dict[str, str] | None:
    try:
        relative = path.resolve().relative_to(Path.home().resolve())
    except (OSError, ValueError):
        return None
    return {"base": "HOME", "relative": relative.as_posix()}


def reject(errors: list[str]) -> int:
    print("OpenPali evaluator capture rejected:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 2


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return reject(["malformed SubagentStop input"])

    agent_type = str(event.get("agent_type") or "")
    if agent_type not in EVALUATOR_NAMES:
        return 0
    if event.get("stop_hook_active") is True:
        return 0

    message = str(event.get("last_assistant_message") or "").strip()
    quick_verdict = HEADER_PATTERNS["verdict"].findall(message)
    if quick_verdict == ["FAIL"]:
        # A failed evaluator must return control to the principal without
        # touching protected terminal files or reawakening a read-only agent.
        return 0

    project = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or str(event.get("cwd") or Path.cwd())
    ).resolve()
    task = project / "openpali-one-shot"
    contract_path = task / "contract" / "acceptance.json"
    errors: list[str] = []

    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        expected_ids = {
            item["id"] for item in contract["criteria"] if item.get("priority") == "MUST"
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return reject([f"cannot load acceptance contract: {exc}"])

    head_result = git(project, "rev-parse", "HEAD")
    status_result = git(project, "status", "--porcelain=v1", "--untracked-files=all")
    candidate = head_result.stdout.strip()
    if head_result.returncode or not re.fullmatch(r"[a-f0-9]{40}", candidate):
        errors.append("cannot resolve a full candidate commit")
    if status_result.returncode or status_result.stdout:
        errors.append("evaluator must run against a clean candidate worktree")

    parsed: dict[str, str] = {}
    for field, pattern in HEADER_PATTERNS.items():
        matches = pattern.findall(message)
        if len(matches) != 1:
            errors.append(f"evaluator must report exactly one valid {field} header")
        else:
            parsed[field] = matches[0]
    if parsed.get("commit") != candidate:
        errors.append("evaluator COMMIT does not match clean candidate HEAD")
    contract_sha = digest_file(contract_path)
    if parsed.get("contract_sha256") != contract_sha:
        errors.append("evaluator CONTRACT_SHA256 does not match the immutable contract")

    must_results: dict[str, str] = {}
    for criterion_id, status in MUST_RESULT.findall(message):
        if criterion_id in must_results:
            errors.append(f"duplicate MUST result: {criterion_id}")
        must_results[criterion_id] = status
    if set(must_results) != expected_ids:
        errors.append(
            "evaluator MUST coverage mismatch: missing "
            f"{sorted(expected_ids - set(must_results))}; extra {sorted(set(must_results) - expected_ids)}"
        )
    if parsed.get("verdict") == "PASS" and any(value != "PASS" for value in must_results.values()):
        errors.append("VERDICT PASS requires every technical MUST to pass")
    for heading in (
        "COMPONENT MATRIX",
        "MUST RESULTS",
        "HUMAN GATE",
        "COMMANDS",
        "FAILURES",
        "UNTESTED RISKS",
    ):
        if message.splitlines().count(heading) != 1:
            errors.append(f"evaluator must contain exactly one {heading} heading")

    transcript_raw = str(event.get("agent_transcript_path") or "")
    transcript = Path(transcript_raw).expanduser()
    locator = home_locator(transcript) if transcript_raw else None
    if locator is None or not transcript.is_file() or transcript.is_symlink():
        errors.append("agent transcript is missing, symlinked, or outside HOME")
        transcript_sha = ""
    else:
        transcript_sha = digest_file(transcript)
        if not transcript_contains(transcript, message):
            errors.append("exact evaluator response was not found in its transcript")

    session_id = str(event.get("session_id") or "")
    agent_id = str(event.get("agent_id") or "")
    if not session_id or not agent_id:
        errors.append("SubagentStop omitted session_id or agent_id")
    if errors:
        return reject(errors)
    if parsed.get("verdict") != "PASS":
        # Failed evaluations remain visible in the native agent transcript but
        # must not dirty or lock the candidate's terminal evidence files.
        return 0

    content = (message + "\n").encode("utf-8")
    attestation = {
        "attestation_version": "2.0.0",
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "candidate_commit": candidate,
        "contract_sha256": contract_sha,
        "verdict": parsed.get("verdict"),
        "confidence": parsed.get("confidence"),
        "must_results": must_results,
        "message_sha256": digest_bytes(content),
        "agent_transcript": locator,
        "agent_transcript_sha256": transcript_sha,
    }
    state = task / "state"
    state.mkdir(parents=True, exist_ok=True)
    temporary_output = state / ".evaluator-latest.tmp"
    temporary_attestation = state / ".evaluator-attestation.tmp"
    try:
        temporary_output.write_bytes(content)
        temporary_attestation.write_text(
            json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_output.replace(state / "evaluator-latest.md")
        temporary_attestation.replace(state / "evaluator-attestation.json")
    except OSError as exc:
        return reject([f"could not persist terminal evaluator evidence: {exc}"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
