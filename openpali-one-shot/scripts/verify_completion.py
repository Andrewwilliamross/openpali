#!/usr/bin/env python3
"""Verify that one evidence-only child follows the evaluated OpenPali candidate."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "openpali-one-shot"
STATE = TASK / "state"
TERMINAL_FILES = {
    "openpali-one-shot/state/evaluator-latest.md",
    "openpali-one-shot/state/evaluator-attestation.json",
}
COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
MUST_RESULT = re.compile(r"^- ([A-Z][A-Z0-9-]{2,63}): (PASS|FAIL) — .+$", re.MULTILINE)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], text=True, capture_output=True, check=False
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)}: top level must be an object")
        return {}
    return value


def main() -> int:
    required = [
        STATE / "evaluator-latest.md",
        STATE / "evaluator-attestation.json",
        STATE / "FINAL_REPORT.md",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        print("COMPLETION: FAIL")
        print(f"- terminal evidence files are missing: {missing}")
        return 1

    errors: list[str] = []
    contract_path = TASK / "contract/acceptance.json"
    contract = load_object(contract_path, errors)
    attestation = load_object(STATE / "evaluator-attestation.json", errors)
    must_ids = {
        item["id"]
        for item in contract.get("criteria", [])
        if isinstance(item, dict) and item.get("priority") == "MUST"
    }
    if len(must_ids) != 20:
        errors.append(f"acceptance contract must contain 20 technical MUSTs, got {len(must_ids)}")

    head_result = git("rev-parse", "HEAD")
    parent_result = git("rev-parse", "HEAD^")
    parents_result = git("rev-list", "--parents", "-n", "1", "HEAD")
    status_result = git("status", "--porcelain=v1", "--untracked-files=all")
    head = head_result.stdout.strip()
    candidate = parent_result.stdout.strip()
    if (
        head_result.returncode
        or parent_result.returncode
        or not COMMIT_RE.fullmatch(head)
        or not COMMIT_RE.fullmatch(candidate)
    ):
        errors.append("cannot resolve terminal HEAD and its candidate parent")
    if len(parents_result.stdout.split()) != 2:
        errors.append("terminal evidence commit must have exactly one parent")
    if status_result.returncode or status_result.stdout:
        errors.append("terminal verification requires a clean worktree")
    diff_result = git("diff", "--name-only", f"{candidate}..{head}")
    changed = set(diff_result.stdout.splitlines()) if not diff_result.returncode else set()
    if changed != TERMINAL_FILES:
        errors.append(
            "terminal child must contain exactly the two hook-owned evidence files; "
            f"missing {sorted(TERMINAL_FILES - changed)}, extra {sorted(changed - TERMINAL_FILES)}"
        )

    contract_sha = sha256(contract_path)
    if attestation.get("attestation_version") != "2.0.0":
        errors.append("evaluator attestation version must be 2.0.0")
    if attestation.get("candidate_commit") != candidate:
        errors.append("evaluator attestation is not bound to the candidate parent")
    if attestation.get("contract_sha256") != contract_sha:
        errors.append("evaluator attestation contract hash mismatch")
    if attestation.get("verdict") != "PASS":
        errors.append("fresh evaluator verdict is not PASS")
    if attestation.get("confidence") not in {"high", "medium", "low"}:
        errors.append("evaluator confidence is invalid")
    results = attestation.get("must_results")
    if not isinstance(results, dict) or set(results) != must_ids or any(
        value != "PASS" for value in results.values()
    ):
        errors.append("evaluator attestation does not pass every technical MUST")

    evaluator_path = STATE / "evaluator-latest.md"
    evaluator_text = evaluator_path.read_text(encoding="utf-8")
    if attestation.get("message_sha256") != sha256(evaluator_path):
        errors.append("captured evaluator message hash mismatch")
    for expected in (
        "VERDICT: PASS",
        f"COMMIT: {candidate}",
        f"CONTRACT_SHA256: {contract_sha}",
        "COMPONENT MATRIX",
        "MUST RESULTS",
        "HUMAN GATE",
        "COMMANDS",
        "FAILURES",
        "UNTESTED RISKS",
    ):
        if evaluator_text.splitlines().count(expected) != 1:
            errors.append(f"captured evaluator output must contain exactly one {expected!r}")
    parsed_results = dict(MUST_RESULT.findall(evaluator_text))
    if set(parsed_results) != must_ids or any(value != "PASS" for value in parsed_results.values()):
        errors.append("captured evaluator output does not pass every technical MUST")

    transcript = attestation.get("agent_transcript")
    if isinstance(transcript, dict) and transcript.get("base") == "HOME":
        relative = Path(str(transcript.get("relative") or ""))
        transcript_path = (Path.home() / relative).resolve()
        try:
            transcript_path.relative_to(Path.home().resolve())
        except ValueError:
            errors.append("evaluator transcript locator escapes HOME")
        else:
            if not transcript_path.is_file() or transcript_path.is_symlink():
                errors.append("attested evaluator transcript is unavailable")
            elif attestation.get("agent_transcript_sha256") != sha256(transcript_path):
                errors.append("evaluator transcript hash mismatch")
    else:
        errors.append("invalid evaluator transcript locator")

    report = (STATE / "FINAL_REPORT.md").read_text(encoding="utf-8").strip()
    if git("cat-file", "-e", f"{candidate}:openpali-one-shot/state/FINAL_REPORT.md").returncode:
        errors.append("FINAL_REPORT.md was not committed in the evaluated candidate")
    if len(report) < 400:
        errors.append("FINAL_REPORT.md is missing substantive founder-readable content")
    for section in ("demonstrated", "measured", "limitations", "human release", "next"):
        if section not in report.lower():
            errors.append(f"FINAL_REPORT.md is missing the {section!r} section")

    if errors:
        print("COMPLETION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("COMPLETION: PASS")
    print(f"CANDIDATE_COMMIT: {candidate}")
    print(f"EVIDENCE_COMMIT: {head}")
    print(f"TECHNICAL_MUSTS: {len(must_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
