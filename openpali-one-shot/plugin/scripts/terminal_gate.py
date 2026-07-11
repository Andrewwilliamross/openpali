#!/usr/bin/env python3
"""Deterministically block a terminal response until the evidence contract holds."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluator_protocol import (
    FULL_COMMIT_RE,
    SHA256_RE,
    home_relative_locator,
    parse_evaluator_message,
    resolve_locator,
    sha256_bytes,
    sha256_file,
    transcript_contains_message,
)


EVALUATOR = "openpali-independent-evaluator"
RESULTS_RELATIVE = "openpali-one-shot/state/acceptance-results.json"
ATTESTATION_RELATIVE = "openpali-one-shot/state/evaluator-attestation.json"
LATEST_RELATIVE = "openpali-one-shot/state/evaluator-latest.md"
ALLOWED_EVIDENCE_COMMIT_EXACT = {
    RESULTS_RELATIVE,
    ATTESTATION_RELATIVE,
    LATEST_RELATIVE,
    "openpali-one-shot/state/PLAN.md",
    "openpali-one-shot/state/STATUS.md",
    "openpali-one-shot/state/FINAL_REPORT.md",
}
EVALUATOR_ARCHIVE_RE = re.compile(
    r"^openpali-one-shot/state/evaluator/evaluator-[A-Za-z0-9_-]+(?:\.attestation)?\.(?:md|json)$"
)
EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
CRITERION_ID_RE = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")
ALLOWED_KINDS = {"command", "report", "browser", "source", "decision", "review"}
ALLOWED_BLOCKER_CATEGORIES = {
    "license_or_right",
    "credential",
    "private_input",
    "material_spend",
    "destructive_action",
    "scope_decision",
}
UNSAFE_RESUME = re.compile(
    r"\bgit\s+(?:push|reset|clean)\b|\brm\s+-[^\n]*r[^\n]*f\b|"
    r"\b(?:deploy|terraform\s+apply|pulumi\s+up)\b|"
    r"\bcurl\b[^\n]*(?:-X|--request)\s*(?:POST|PUT|PATCH|DELETE)\b",
    re.IGNORECASE,
)


def git(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def add(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def utc_time(value: object, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return None
    return parsed.astimezone(timezone.utc)


def read_object(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is absent or invalid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} top level must be an object")
        return {}
    return value


def resolve_evidence_artifact(project: Path, relative: object, errors: list[str], label: str) -> Path | None:
    ordinary = isinstance(relative, str) and bool(re.fullmatch(
        r"openpali-one-shot/state/evidence/[A-Za-z0-9][A-Za-z0-9._/-]*", relative
    ))
    evaluator_owned = isinstance(relative, str) and bool(EVALUATOR_ARCHIVE_RE.fullmatch(relative))
    if not ordinary and not evaluator_owned:
        errors.append(f"{label}.artifact must be ordinary evidence or a hook-owned evaluator archive")
        return None
    path = project / relative
    expected_root = (
        project / "openpali-one-shot" / "state" / ("evidence" if ordinary else "evaluator")
    ).resolve()
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(expected_root)
    except (OSError, ValueError):
        errors.append(f"{label}.artifact is missing or escapes its evidence root: {relative}")
        return None
    if path.is_symlink() or not resolved.is_file():
        errors.append(f"{label}.artifact must be a non-symlink regular file: {relative}")
        return None
    return resolved


def validate_evidence_catalog(
    project: Path,
    candidate: str,
    value: object,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        errors.append("evidence must be a non-empty array")
        return {}
    records: dict[str, dict[str, Any]] = {}
    allowed_fields = {
        "id", "kind", "command", "exit_code", "observed_at", "commit", "result", "artifact", "sha256"
    }
    for index, record in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label} must be an object")
            continue
        extra = sorted(set(record) - allowed_fields)
        if extra:
            errors.append(f"{label} has unsupported fields: {', '.join(extra)}")
        evidence_id = record.get("id")
        if not isinstance(evidence_id, str) or not EVIDENCE_ID_RE.fullmatch(evidence_id):
            errors.append(f"{label}.id is invalid")
            continue
        if evidence_id in records:
            errors.append(f"duplicate evidence id: {evidence_id}")
            continue
        records[evidence_id] = record
        kind = record.get("kind")
        add(errors, kind in ALLOWED_KINDS, f"{label}.kind is invalid")
        add(errors, record.get("commit") == candidate, f"{label}.commit must equal release_candidate_commit")
        add(errors, isinstance(record.get("result"), str) and len(record["result"].strip()) >= 3,
            f"{label}.result is too short")
        utc_time(record.get("observed_at"), f"{label}.observed_at", errors)
        if kind == "command":
            add(errors, isinstance(record.get("command"), str) and bool(record["command"].strip()),
                f"{label} command evidence requires command")
            add(errors, isinstance(record.get("exit_code"), int) and not isinstance(record.get("exit_code"), bool),
                f"{label} command evidence requires integer exit_code")
        artifact = resolve_evidence_artifact(project, record.get("artifact"), errors, label)
        claimed_hash = record.get("sha256")
        add(errors, isinstance(claimed_hash, str) and bool(SHA256_RE.fullmatch(claimed_hash)),
            f"{label}.sha256 is invalid")
        if artifact is not None and isinstance(claimed_hash, str):
            add(errors, sha256_file(artifact) == claimed_hash, f"{label}.sha256 does not match artifact bytes")
            relative = str(record.get("artifact"))
            at_candidate = git(project, "cat-file", "-e", f"{candidate}:{relative}")
            if at_candidate.returncode and not EVALUATOR_ARCHIVE_RE.fullmatch(relative):
                errors.append(f"{label}.artifact was not committed in the evaluated candidate")
    return records


def validate_refs(
    refs: object,
    evidence: dict[str, dict[str, Any]],
    errors: list[str],
    label: str,
    referenced: set[str],
    *,
    require_success: bool,
) -> None:
    if not isinstance(refs, list) or not refs:
        errors.append(f"{label} must contain at least one evidence id")
        return
    if len(refs) != len(set(str(item) for item in refs)):
        errors.append(f"{label} contains duplicate evidence ids")
    for item in refs:
        if not isinstance(item, str) or item not in evidence:
            errors.append(f"{label} references unknown evidence id: {item!r}")
            continue
        referenced.add(item)
        if require_success:
            record = evidence[item]
            if record.get("kind") == "command" and record.get("exit_code") != 0:
                errors.append(f"{label} cites failing command evidence {item} for a passing assertion")


def validate_criteria(
    contract_criteria: list[dict[str, Any]],
    value: object,
    evidence: dict[str, dict[str, Any]],
    errors: list[str],
    referenced: set[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        errors.append("criteria must be an array")
        return {}
    supplied = {item["id"]: item for item in contract_criteria}
    results: dict[str, dict[str, Any]] = {}
    allowed = {"id", "status", "notes", "proof_results", "fail_if_results"}
    for position, result in enumerate(value):
        label = f"criteria[{position}]"
        if not isinstance(result, dict):
            errors.append(f"{label} must be an object")
            continue
        extra = sorted(set(result) - allowed)
        if extra:
            errors.append(f"{label} has unsupported fields: {', '.join(extra)}")
        criterion_id = result.get("id")
        if not isinstance(criterion_id, str) or not CRITERION_ID_RE.fullmatch(criterion_id):
            errors.append(f"{label}.id is invalid")
            continue
        if criterion_id in results:
            errors.append(f"duplicate criterion result: {criterion_id}")
            continue
        results[criterion_id] = result
        status = result.get("status")
        add(errors, status in {"PASS", "FAIL", "BLOCKED"}, f"{criterion_id}.status is invalid")

        proof_results = result.get("proof_results")
        fail_results = result.get("fail_if_results")
        if not isinstance(proof_results, list) or not proof_results:
            errors.append(f"{criterion_id}.proof_results must be non-empty")
            proof_results = []
        if not isinstance(fail_results, list) or not fail_results:
            errors.append(f"{criterion_id}.fail_if_results must be non-empty")
            fail_results = []

        expected_proofs = range(len(supplied[criterion_id]["proof"])) if criterion_id in supplied else None
        expected_failures = range(len(supplied[criterion_id]["fail_if"])) if criterion_id in supplied else None
        observed_proofs: set[int] = set()
        observed_failures: set[int] = set()
        proof_statuses: list[str] = []
        fail_triggers: list[bool] = []
        for offset, proof in enumerate(proof_results):
            proof_label = f"{criterion_id}.proof_results[{offset}]"
            if not isinstance(proof, dict) or set(proof) != {"index", "status", "evidence_ids"}:
                errors.append(f"{proof_label} must contain only index, status, evidence_ids")
                continue
            proof_index = proof.get("index")
            if not isinstance(proof_index, int) or isinstance(proof_index, bool) or proof_index < 0:
                errors.append(f"{proof_label}.index is invalid")
            elif proof_index in observed_proofs:
                errors.append(f"{criterion_id} has duplicate proof index {proof_index}")
            else:
                observed_proofs.add(proof_index)
            proof_status = proof.get("status")
            if proof_status not in {"PASS", "FAIL", "BLOCKED"}:
                errors.append(f"{proof_label}.status is invalid")
            else:
                proof_statuses.append(proof_status)
            validate_refs(
                proof.get("evidence_ids"), evidence, errors, f"{proof_label}.evidence_ids", referenced,
                require_success=proof_status == "PASS",
            )
        for offset, fail_result in enumerate(fail_results):
            fail_label = f"{criterion_id}.fail_if_results[{offset}]"
            if not isinstance(fail_result, dict) or set(fail_result) != {"index", "triggered", "evidence_ids"}:
                errors.append(f"{fail_label} must contain only index, triggered, evidence_ids")
                continue
            fail_index = fail_result.get("index")
            if not isinstance(fail_index, int) or isinstance(fail_index, bool) or fail_index < 0:
                errors.append(f"{fail_label}.index is invalid")
            elif fail_index in observed_failures:
                errors.append(f"{criterion_id} has duplicate fail_if index {fail_index}")
            else:
                observed_failures.add(fail_index)
            triggered = fail_result.get("triggered")
            if not isinstance(triggered, bool):
                errors.append(f"{fail_label}.triggered must be boolean")
            else:
                fail_triggers.append(triggered)
            validate_refs(
                fail_result.get("evidence_ids"), evidence, errors, f"{fail_label}.evidence_ids", referenced,
                require_success=triggered is False,
            )

        if expected_proofs is not None and observed_proofs != set(expected_proofs):
            errors.append(f"{criterion_id} must cover every supplied proof index exactly once")
        if expected_failures is not None and observed_failures != set(expected_failures):
            errors.append(f"{criterion_id} must cover every supplied fail_if index exactly once")
        if status == "PASS" and (any(item != "PASS" for item in proof_statuses) or any(fail_triggers)):
            errors.append(f"{criterion_id} PASS conflicts with proof/fail_if results")
        if status == "BLOCKED" and (
            "BLOCKED" not in proof_statuses or "FAIL" in proof_statuses or any(fail_triggers)
        ):
            errors.append(f"{criterion_id} BLOCKED requires a blocked proof and no failure trigger")
        if status == "FAIL" and "FAIL" not in proof_statuses and not any(fail_triggers):
            errors.append(f"{criterion_id} FAIL lacks a failed proof or triggered fail_if")

    missing = sorted(set(supplied) - set(results))
    if missing:
        errors.append(f"criteria omitted supplied MUST ids: {', '.join(missing)}")
    return results


def validate_attestation(
    project: Path,
    event: dict[str, Any],
    expected_ids: list[str],
    candidate: str,
    contract_hash: str,
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = project / ATTESTATION_RELATIVE
    attestation = read_object(path, "evaluator attestation", errors)
    if not attestation:
        return {}, {}
    add(errors, attestation.get("attestation_version") == "1.0.0", "evaluator attestation version mismatch")
    add(errors, attestation.get("valid") is True and attestation.get("capture_errors") == [],
        "evaluator attestation was not valid at capture")
    add(errors, attestation.get("agent_type") in {EVALUATOR, f"openpali-one-shot:{EVALUATOR}"},
        "evaluator attestation agent type mismatch")
    add(errors, attestation.get("parent_session_id") == event.get("session_id"),
        "evaluator attestation is stale: session id differs")
    add(errors, attestation.get("release_candidate_commit") == candidate,
        "evaluator attestation evaluated a different commit")
    add(errors, attestation.get("contract_sha256") == contract_hash,
        "evaluator attestation used a different acceptance contract")

    current_parent_locator = home_relative_locator(Path(str(event.get("transcript_path") or "")))
    add(errors, current_parent_locator is not None and attestation.get("parent_transcript") == current_parent_locator,
        "evaluator attestation is not bound to this parent transcript")
    agent_transcript = resolve_locator(attestation.get("agent_transcript"))
    if agent_transcript is None or not agent_transcript.is_file():
        errors.append("attested evaluator transcript is unavailable")
    else:
        add(errors, not agent_transcript.is_symlink(), "attested evaluator transcript must not be a symlink")
        add(errors, sha256_file(agent_transcript) == attestation.get("agent_transcript_sha256"),
            "attested evaluator transcript hash changed")
        add(errors, agent_transcript.stat().st_size == attestation.get("agent_transcript_size"),
            "attested evaluator transcript size changed")

    output_relative = attestation.get("output_path")
    archive_relative = attestation.get("archive_path")
    archive_attestation_relative = attestation.get("archive_attestation_path")
    add(errors, output_relative == LATEST_RELATIVE, "evaluator output path mismatch")
    add(errors, isinstance(archive_relative, str) and bool(EVALUATOR_ARCHIVE_RE.fullmatch(archive_relative)),
        "evaluator archive path is invalid")
    add(errors, isinstance(archive_attestation_relative, str) and
        bool(EVALUATOR_ARCHIVE_RE.fullmatch(archive_attestation_relative)),
        "evaluator attestation archive path is invalid")
    try:
        output_bytes = (project / str(output_relative)).read_bytes()
        archive_bytes = (project / str(archive_relative)).read_bytes()
    except OSError as exc:
        errors.append(f"evaluator output/archive is missing: {exc}")
        return attestation, {}
    add(errors, output_bytes == archive_bytes, "latest evaluator output differs from its archive")
    add(errors, sha256_bytes(output_bytes) == attestation.get("message_sha256"),
        "evaluator output hash differs from attestation")
    try:
        archive_attestation = json.loads((project / str(archive_attestation_relative)).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"evaluator attestation archive is missing/invalid: {exc}")
    else:
        add(errors, archive_attestation == attestation, "latest evaluator attestation differs from archive")

    message = output_bytes.decode("utf-8", errors="replace").strip()
    parsed, protocol_errors = parse_evaluator_message(message, expected_ids)
    errors.extend(f"evaluator protocol: {item}" for item in protocol_errors)
    add(errors, parsed.get("commit") == candidate, "evaluator output names a different candidate commit")
    add(errors, parsed.get("contract_sha256") == contract_hash, "evaluator output names a different contract hash")
    add(errors, parsed.get("verdict") == attestation.get("verdict"), "evaluator verdict differs from attestation")
    add(errors, parsed.get("must_results") == attestation.get("must_results"),
        "evaluator MUST results differ from attestation")
    if agent_transcript is not None and agent_transcript.is_file():
        add(errors, transcript_contains_message(agent_transcript, message),
            "exact evaluator output is absent from the attested transcript")
    return attestation, parsed


def validate_git_terminal(project: Path, candidate: str, errors: list[str]) -> str:
    head_result = git(project, "rev-parse", "HEAD")
    head = head_result.stdout.strip()
    if head_result.returncode or not FULL_COMMIT_RE.fullmatch(head):
        errors.append("cannot resolve terminal HEAD")
        return ""
    status = git(project, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode or status.stdout:
        errors.append("terminal worktree must be clean, including untracked files")
    commit_check = git(project, "cat-file", "-e", f"{candidate}^{{commit}}")
    if commit_check.returncode:
        errors.append("release_candidate_commit does not exist")
        return head
    parents = git(project, "rev-list", "--parents", "-n", "1", head)
    parts = parents.stdout.strip().split()
    if parents.returncode or len(parts) != 2 or parts[1] != candidate:
        errors.append("terminal HEAD must be one non-merge evidence-only child of release_candidate_commit")
    changed = git(project, "diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{candidate}..{head}")
    changed_paths = {line for line in changed.stdout.splitlines() if line}
    if changed.returncode:
        errors.append("could not inspect candidate-to-terminal diff")
    for path in sorted(changed_paths):
        if path not in ALLOWED_EVIDENCE_COMMIT_EXACT and not EVALUATOR_ARCHIVE_RE.fullmatch(path):
            errors.append(f"terminal commit changes non-evidence path: {path}")
    required = {RESULTS_RELATIVE, ATTESTATION_RELATIVE, LATEST_RELATIVE}
    missing = sorted(required - changed_paths)
    if missing:
        errors.append(f"evidence-only terminal commit omitted required files: {', '.join(missing)}")
    return head


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        print(json.dumps({"decision": "block", "reason": "Terminal gate received malformed hook input."}))
        return 0
    if event.get("hook_event_name") not in (None, "Stop"):
        return 0

    project = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or str(event.get("cwd") or Path.cwd())
    ).resolve()
    errors: list[str] = []
    contract = read_object(project / "openpali-one-shot" / "contract" / "acceptance.json", "contract", errors)
    results = read_object(project / RESULTS_RELATIVE, "acceptance results", errors)
    if not contract or not results:
        reason = "Terminal evidence is incomplete. " + " ".join(errors[:6])
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0

    contract_path = project / "openpali-one-shot" / "contract" / "acceptance.json"
    contract_hash = sha256_file(contract_path)
    contract_criteria = [
        item for item in contract.get("criteria", [])
        if isinstance(item, dict) and item.get("priority") == "MUST"
    ]
    expected_ids = [str(item.get("id")) for item in contract_criteria]
    add(errors, len(expected_ids) >= 15 and len(expected_ids) == len(set(expected_ids)),
        "acceptance contract MUST ids are invalid")

    allowed_top = {
        "schema_version", "contract_version", "contract_sha256", "release_candidate_commit",
        "generated_at", "terminal_state", "summary", "criteria", "evidence",
        "external_blockers", "stall_cycles",
    }
    extra_top = sorted(set(results) - allowed_top)
    if extra_top:
        errors.append(f"acceptance results has unsupported fields: {', '.join(extra_top)}")
    add(errors, results.get("schema_version") == "2.0.0", "acceptance results schema_version must be 2.0.0")
    add(errors, results.get("contract_version") == contract.get("contract_version"),
        "acceptance results contract_version mismatch")
    add(errors, results.get("contract_sha256") == contract_hash,
        "acceptance results contract_sha256 mismatch")
    candidate = str(results.get("release_candidate_commit") or "")
    add(errors, bool(FULL_COMMIT_RE.fullmatch(candidate)), "release_candidate_commit must be a full hash")
    generated_at = utc_time(results.get("generated_at"), "generated_at", errors)
    add(errors, isinstance(results.get("summary"), str) and len(results["summary"].strip()) >= 20,
        "acceptance results summary is too short")

    evidence = validate_evidence_catalog(project, candidate, results.get("evidence"), errors)
    referenced: set[str] = set()
    criteria = validate_criteria(contract_criteria, results.get("criteria"), evidence, errors, referenced)
    attestation, evaluated = validate_attestation(
        project, event, expected_ids, candidate, contract_hash, errors
    )
    release_result = criteria.get("RELEASE-001", {})
    release_proofs = release_result.get("proof_results") if isinstance(release_result, dict) else None
    final_output_evidence: set[str] = set()
    if isinstance(release_proofs, list):
        for proof in release_proofs:
            if isinstance(proof, dict) and proof.get("index") == 0:
                refs = proof.get("evidence_ids")
                if isinstance(refs, list):
                    final_output_evidence.update(str(item) for item in refs)
    add(
        errors,
        any(
            evidence.get(evidence_id, {}).get("artifact") == attestation.get("archive_path")
            for evidence_id in final_output_evidence
        ),
        "RELEASE-001 proof 0 must cite the hook-owned final evaluator output archive",
    )
    terminal_head = validate_git_terminal(project, candidate, errors)
    if generated_at is not None:
        captured_at = utc_time(attestation.get("captured_at"), "evaluator captured_at", errors)
        if captured_at is not None and generated_at < captured_at:
            errors.append("acceptance results must be generated after the final evaluator capture")
        if generated_at > datetime.now(timezone.utc).replace(microsecond=0) and (
            generated_at - datetime.now(timezone.utc)
        ).total_seconds() > 300:
            errors.append("acceptance results generated_at is implausibly in the future")

    evaluator_statuses = evaluated.get("must_results", {}) if isinstance(evaluated, dict) else {}
    terminal_state = results.get("terminal_state")
    supplied_results = {criterion_id: criteria.get(criterion_id, {}) for criterion_id in expected_ids}
    blockers = results.get("external_blockers")
    cycles = results.get("stall_cycles")
    if not isinstance(blockers, list):
        errors.append("external_blockers must be an array")
        blockers = []
    if not isinstance(cycles, list):
        errors.append("stall_cycles must be an array")
        cycles = []

    blocked_ids: set[str] = set()
    allowed_blocker_fields = {
        "criterion_ids", "category", "decision_owner", "decision_needed", "safe_default",
        "evidence_ids", "resume_command",
    }
    for index, blocker in enumerate(blockers):
        label = f"external_blockers[{index}]"
        if not isinstance(blocker, dict) or set(blocker) != allowed_blocker_fields:
            errors.append(f"{label} has an invalid shape")
            continue
        ids = blocker.get("criterion_ids")
        if not isinstance(ids, list) or not ids or len(ids) != len(set(str(item) for item in ids)):
            errors.append(f"{label}.criterion_ids must be non-empty and unique")
            ids = []
        for criterion_id in ids:
            if criterion_id not in criteria:
                errors.append(f"{label} references unknown criterion {criterion_id!r}")
            elif str(criterion_id) in blocked_ids:
                errors.append(f"{label} duplicates blocked criterion {criterion_id!r}")
            else:
                blocked_ids.add(str(criterion_id))
        add(errors, blocker.get("category") in ALLOWED_BLOCKER_CATEGORIES,
            f"{label}.category is not a permitted human/external gate")
        for field, minimum in (("decision_owner", 2), ("decision_needed", 10), ("safe_default", 10)):
            add(errors, isinstance(blocker.get(field), str) and len(blocker[field].strip()) >= minimum,
                f"{label}.{field} is too short")
        resume = blocker.get("resume_command")
        add(errors, isinstance(resume, str) and len(resume.strip()) >= 3 and not UNSAFE_RESUME.search(resume),
            f"{label}.resume_command is absent or unsafe")
        validate_refs(blocker.get("evidence_ids"), evidence, errors, f"{label}.evidence_ids", referenced,
                      require_success=False)

    allowed_cycle_fields = {
        "cycle", "commit", "started_at", "ended_at", "repair_or_replan", "observed_result", "evidence_ids"
    }
    cycle_numbers: list[int] = []
    for index, cycle in enumerate(cycles):
        label = f"stall_cycles[{index}]"
        if not isinstance(cycle, dict) or set(cycle) != allowed_cycle_fields:
            errors.append(f"{label} has an invalid shape")
            continue
        number = cycle.get("cycle")
        if isinstance(number, int) and not isinstance(number, bool) and number > 0:
            cycle_numbers.append(number)
        else:
            errors.append(f"{label}.cycle is invalid")
        add(errors, isinstance(cycle.get("commit"), str) and bool(FULL_COMMIT_RE.fullmatch(cycle["commit"])),
            f"{label}.commit must be a full hash")
        started = utc_time(cycle.get("started_at"), f"{label}.started_at", errors)
        ended = utc_time(cycle.get("ended_at"), f"{label}.ended_at", errors)
        if started is not None and ended is not None and ended < started:
            errors.append(f"{label} ended before it started")
        for field in ("repair_or_replan", "observed_result"):
            add(errors, isinstance(cycle.get(field), str) and len(cycle[field].strip()) >= 10,
                f"{label}.{field} is too short")
        validate_refs(cycle.get("evidence_ids"), evidence, errors, f"{label}.evidence_ids", referenced,
                      require_success=False)

    if terminal_state == "PASS":
        add(errors, not blockers and not cycles, "PASS cannot carry blockers or stall cycles")
        add(errors, evaluated.get("verdict") == "PASS", "PASS requires fresh evaluator VERDICT PASS")
        for criterion_id, result in criteria.items():
            add(errors, result.get("status") == "PASS", f"PASS requires {criterion_id} result PASS")
        for criterion_id, result in supplied_results.items():
            add(errors, evaluator_statuses.get(criterion_id) == "PASS",
                f"PASS requires evaluator {criterion_id} PASS")
    elif terminal_state == "BLOCKED_EXTERNAL":
        add(errors, bool(blockers) and not cycles, "BLOCKED_EXTERNAL requires blockers and no stall cycles")
        add(errors, evaluated.get("verdict") == "FAIL", "BLOCKED_EXTERNAL requires a fresh evaluator FAIL")
        actual_blocked = {
            criterion_id for criterion_id, result in criteria.items()
            if result.get("status") == "BLOCKED"
        }
        add(errors, bool(actual_blocked), "BLOCKED_EXTERNAL requires at least one blocked MUST criterion")
        add(errors, actual_blocked == blocked_ids,
            "external blockers must map exactly to BLOCKED criterion results")
        for criterion_id, result in criteria.items():
            add(errors, result.get("status") in {"PASS", "BLOCKED"},
                f"BLOCKED_EXTERNAL cannot contain failed non-external criterion {criterion_id}")
        for criterion_id, result in supplied_results.items():
            expected = "FAIL" if result.get("status") == "BLOCKED" else "PASS"
            add(errors, evaluator_statuses.get(criterion_id) == expected,
                f"evaluator status for {criterion_id} must agree with BLOCKED_EXTERNAL mapping")
    elif terminal_state == "STALLED":
        errors.append("STALLED is a reportable recovery state, never permission to terminate the one-shot")
    elif terminal_state in {"IN_PROGRESS", "BUDGET_EXHAUSTED"}:
        errors.append(f"{terminal_state} is reportable state, not permission to terminate the one-shot")
    else:
        errors.append("terminal_state is invalid")

    orphaned = sorted(set(evidence) - referenced)
    if orphaned:
        errors.append(f"unreferenced evidence records are forbidden: {', '.join(orphaned[:10])}")
    # Terminal-head is intentionally not stored in acceptance-results: putting a
    # commit's own hash inside that commit is circular. Git parentage above is
    # the attestation that HEAD is the one evidence-only child.
    if terminal_head and candidate == terminal_head:
        errors.append("terminal evidence must be sealed in one child commit, not left at the evaluated commit")

    if errors:
        unique_errors = list(dict.fromkeys(errors))
        reason = "Terminal gate failed; continue from the release candidate and repair these facts:\n- " + "\n- ".join(
            unique_errors[:16]
        )
        if len(unique_errors) > 16:
            reason += f"\n- ... plus {len(unique_errors) - 16} more; run terminal_gate.py with the same Stop payload for detail."
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0

    print(json.dumps({"systemMessage": f"OpenPali terminal gate accepted {terminal_state} at {terminal_head}."}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
