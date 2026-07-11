#!/usr/bin/env python3
"""Shared, deterministic parsing and hashing for evaluator attestations."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


FULL_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
MUST_RESULT_RE = re.compile(r"^- ([A-Z][A-Z0-9-]{2,63}): (PASS|FAIL) — (.+)$")
HEADINGS = ("MUST RESULTS", "COMMANDS", "FAILURES", "UNTESTED RISKS")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_evaluator_message(message: str, expected_ids: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Parse the evaluator's exact final protocol and return all defects."""

    errors: list[str] = []
    normalized = message.strip()
    lines = normalized.splitlines()
    parsed: dict[str, Any] = {"must_results": {}}

    if "```" in normalized:
        errors.append("evaluator output must not be wrapped in a code fence")
    if len(lines) < 12:
        errors.append("evaluator output is too short for the required protocol")
        return parsed, errors

    header_patterns = (
        ("verdict", re.compile(r"^VERDICT: (PASS|FAIL)$")),
        ("commit", re.compile(r"^COMMIT: ([a-f0-9]{40})$")),
        ("contract_sha256", re.compile(r"^CONTRACT_SHA256: ([a-f0-9]{64})$")),
        ("confidence", re.compile(r"^CONFIDENCE: (high|medium|low)$")),
    )
    for index, (key, pattern) in enumerate(header_patterns):
        if index >= len(lines):
            errors.append(f"missing evaluator header {key}")
            continue
        match = pattern.fullmatch(lines[index])
        if not match:
            errors.append(f"invalid evaluator header line {index + 1}: expected {key}")
        else:
            parsed[key] = match.group(1)

    heading_positions: list[int] = []
    for heading in HEADINGS:
        positions = [index for index, line in enumerate(lines) if line == heading]
        if len(positions) != 1:
            errors.append(f"expected exactly one {heading!r} heading")
            heading_positions.append(-1)
        else:
            heading_positions.append(positions[0])
    if -1 in heading_positions or heading_positions != sorted(heading_positions):
        errors.append("evaluator sections are missing or out of order")
        return parsed, errors
    if heading_positions[0] != 5 or lines[4] != "":
        errors.append("MUST RESULTS must follow the four headers and one blank line")

    sections: dict[str, list[str]] = {}
    for offset, heading in enumerate(HEADINGS):
        start = heading_positions[offset] + 1
        end = heading_positions[offset + 1] if offset + 1 < len(HEADINGS) else len(lines)
        content = [line for line in lines[start:end] if line.strip()]
        sections[heading] = content
        if not content:
            errors.append(f"{heading} section must contain at least one evidence line")
        for line in content:
            if not line.startswith("- "):
                errors.append(f"{heading} contains a non-bullet line")

    must_results: dict[str, str] = {}
    for line in sections.get("MUST RESULTS", []):
        match = MUST_RESULT_RE.fullmatch(line)
        if not match:
            errors.append(f"malformed MUST result: {line[:120]}")
            continue
        criterion_id, status, _evidence = match.groups()
        if criterion_id in must_results:
            errors.append(f"duplicate evaluator MUST result: {criterion_id}")
        must_results[criterion_id] = status

    expected = set(expected_ids)
    observed = set(must_results)
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing:
        errors.append(f"evaluator omitted MUST criteria: {', '.join(missing)}")
    if extra:
        errors.append(f"evaluator reported unknown MUST criteria: {', '.join(extra)}")
    parsed["must_results"] = must_results

    verdict = parsed.get("verdict")
    statuses = list(must_results.values())
    if verdict == "PASS" and (len(statuses) != len(expected_ids) or any(value != "PASS" for value in statuses)):
        errors.append("VERDICT PASS requires every supplied MUST result to be PASS")
    if verdict == "FAIL" and statuses and all(value == "PASS" for value in statuses):
        errors.append("VERDICT FAIL must identify at least one failing MUST result")

    return parsed, errors


def transcript_contains_message(path: Path, message: str) -> bool:
    """Require the exact final response to occur as a string in the JSONL transcript."""

    target = message.strip()

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
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if any(candidate.strip() == target for candidate in strings(value)):
                    return True
    except OSError:
        return False
    return False


def home_relative_locator(path: Path) -> dict[str, str] | None:
    """Avoid committing an absolute username-bearing transcript path."""

    resolved = path.expanduser().resolve(strict=False)
    try:
        relative = resolved.relative_to(Path.home().resolve())
    except ValueError:
        return None
    return {"base": "HOME", "relative": relative.as_posix()}


def resolve_locator(locator: object) -> Path | None:
    if not isinstance(locator, dict):
        return None
    if locator.get("base") != "HOME":
        return None
    relative = locator.get("relative")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        return None
    return (Path.home() / relative).resolve(strict=False)
