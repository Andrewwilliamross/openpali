#!/usr/bin/env python3
"""Static integrity checks for the product-directed OpenPali one-shot."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    ".gitignore", "README.md", "GOAL_PROMPT.txt", "SYSTEM.md", "MISSION.md",
    "BASELINE.md", "settings.json", "mcp.json", "research/BRIEF.md",
    "research/production-mvp-architecture.md", "contract/acceptance.json",
    "state/README.md", "state/STATUS.md", "state/PLAN.md",
    "state/evaluator-latest.md", "state/evidence/.gitkeep",
    "state/failures/.gitkeep", "state/handoffs/.gitkeep",
    "state/memory/.gitkeep", "state/runs/.gitkeep",
    "plugin/.claude-plugin/plugin.json", "plugin/hooks/hooks.json",
    "plugin/scripts/inject_context.py", "plugin/scripts/guardrails.py",
    "plugin/scripts/capture_evaluator.py", "scripts/preflight.sh",
    "scripts/docker_safe.py", "scripts/test_harness.py",
    "scripts/validate_harness.py", "scripts/verify_completion.py",
    "scripts/launch.sh", "scripts/launch_headless.sh", "scripts/resume.sh",
    "scripts/resume_headless.sh",
}
COMPONENTS = {
    "environment", "domain_truth", "acquisition", "canonical_store",
    "publication", "backend", "analytics", "ml_data", "ml_experiments",
    "ml_operations", "spatial_pipeline", "renderer_3d",
    "multimodal_observations", "property_product", "community_product",
    "cross_stack", "ci_release", "operations", "governance_security",
    "independent_evaluation", "human_release_gate",
}
AGENTS = {
    "openpali-repository-auditor", "openpali-source-researcher",
    "openpali-platform-researcher", "openpali-methods-reviewer",
    "openpali-spatial-reviewer", "openpali-multimodal-researcher",
    "openpali-independent-evaluator",
}
OBSOLETE = {
    "plugin/scripts/terminal_gate.py", "plugin/scripts/evaluator_protocol.py",
    "plugin/scripts/run_observer.py", "scripts/test_controls.py",
    "scripts/test_observer.py",
}
ENTRYPOINTS = {
    "scripts/preflight.sh", "scripts/docker_safe.py", "scripts/test_harness.py",
    "scripts/validate_harness.py", "scripts/verify_completion.py",
    "scripts/launch.sh", "scripts/launch_headless.sh", "scripts/resume.sh",
    "scripts/resume_headless.sh",
}


def load(relative: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{relative}: invalid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{relative}: top level must be an object")
        return {}
    return value


def validate_contract(contract: dict[str, Any], errors: list[str]) -> tuple[int, int]:
    if contract.get("immutable") is not True or contract.get("contract_version") != "2.0.0":
        errors.append("acceptance contract must be immutable version 2.0.0")
    if "outside openpali-one-shot" not in str(contract.get("implementation_rule") or ""):
        errors.append("acceptance contract must require product implementation outside the task folder")
    kinds = contract.get("evidence_kinds")
    evidence_kinds = set(kinds) if isinstance(kinds, list) else set()
    criteria = contract.get("criteria")
    if not isinstance(criteria, list):
        errors.append("acceptance criteria must be an array")
        return 0, 0

    ids: list[str] = []
    components: set[str] = set()
    must = human = implementations = 0
    for item in criteria:
        if not isinstance(item, dict):
            errors.append("acceptance criterion is not an object")
            continue
        criterion_id = str(item.get("id") or "")
        ids.append(criterion_id)
        components.add(str(item.get("component") or ""))
        priority = item.get("priority")
        if priority == "MUST":
            must += 1
            implementations += item.get("implementation_required") is True
            release_exception = (
                criterion_id == "RELEASE-001"
                and item.get("component") == "independent_evaluation"
                and item.get("implementation_required") is False
            )
            if item.get("status") != "FAIL" or item.get("external_blockable") is not False:
                errors.append(f"{criterion_id}: technical criterion must begin FAIL and be non-blockable")
            if item.get("implementation_required") is not True and not release_exception:
                errors.append(f"{criterion_id}: invalid implementation flag")
        elif priority == "HUMAN_GATE":
            human += 1
            if (
                item.get("status") != "UNRESOLVED"
                or item.get("implementation_required") is not False
                or item.get("external_blockable") is not True
            ):
                errors.append(f"{criterion_id}: malformed human gate")
        else:
            errors.append(f"{criterion_id}: unsupported priority")
        required_kinds = item.get("required_evidence_kinds")
        if not isinstance(required_kinds, list) or not required_kinds or not set(required_kinds).issubset(evidence_kinds):
            errors.append(f"{criterion_id}: invalid evidence kinds")
        if any(not item.get(key) for key in ("title", "requirement", "proof", "fail_if")):
            errors.append(f"{criterion_id}: incomplete criterion")

    if len(ids) != len(set(ids)):
        errors.append("acceptance IDs must be unique")
    if (must, implementations, human) != (20, 19, 1) or "APPROVAL-001" not in ids:
        errors.append(f"acceptance counts must be 20 MUST/19 implementation/1 human, got {must}/{implementations}/{human}")
    if components != COMPONENTS:
        errors.append(f"acceptance component mismatch: missing {sorted(COMPONENTS-components)}, extra {sorted(components-COMPONENTS)}")
    serialized = json.dumps(contract)
    for phrase in (
        "time-to-issuance", "Prefect", "representative Palisades release",
        "USGS 2025 post-wildfire 3DEP", "/v1/releases/{release_id}/", "N to N+1",
    ):
        if phrase not in serialized:
            errors.append(f"acceptance contract is missing frozen product depth: {phrase}")
    return must, human


def validate_agents(errors: list[str]) -> None:
    names: set[str] = set()
    for path in (ROOT / "plugin/agents").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            errors.append(f"{path.relative_to(ROOT)}: invalid frontmatter")
            continue
        fields = {}
        for line in text.split("---", 2)[1].splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        if any(not fields.get(key) for key in ("name", "description", "model", "effort", "tools")):
            errors.append(f"{path.relative_to(ROOT)}: incomplete agent frontmatter")
        names.add(fields.get("name", ""))
    if names != AGENTS:
        errors.append(f"agent set mismatch: expected {sorted(AGENTS)}, got {sorted(names)}")


def count_lines(paths: list[Path]) -> int:
    return sum(len(path.read_text(encoding="utf-8").splitlines()) for path in paths if path.is_file())


def main() -> int:
    errors: list[str] = []
    for relative in sorted(REQUIRED):
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")
    for relative in sorted(ENTRYPOINTS):
        if (ROOT / relative).is_file() and not os.access(ROOT / relative, os.X_OK):
            errors.append(f"{relative}: entrypoint must be executable")
    for relative in sorted(OBSOLETE):
        if (ROOT / relative).exists():
            errors.append(f"obsolete control remains: {relative}")

    contract = load("contract/acceptance.json", errors)
    settings = load("settings.json", errors)
    mcp = load("mcp.json", errors)
    plugin = load("plugin/.claude-plugin/plugin.json", errors)
    hooks = load("plugin/hooks/hooks.json", errors)
    must, human = validate_contract(contract, errors) if contract else (0, 0)
    if mcp.get("mcpServers") != {}:
        errors.append("strict task MCP must contain no ambient connectors")

    goal = (ROOT / "GOAL_PROMPT.txt").read_text(encoding="utf-8").strip()
    if not goal.startswith("/goal ") or "\n" in goal or len(goal) > 4000:
        errors.append(f"GOAL_PROMPT.txt must be one /goal line at most 4,000 characters, got {len(goal)}")
    for phrase in ("backend", "learning system", "spatial", "exact current local", "cannot be deferred"):
        if phrase not in goal.lower():
            errors.append(f"GOAL_PROMPT.txt is missing: {phrase}")

    sandbox = settings.get("sandbox")
    if not isinstance(sandbox, dict):
        sandbox = {}
    if (
        sandbox.get("enabled") is not True
        or sandbox.get("failIfUnavailable") is not True
        or sandbox.get("allowUnsandboxedCommands") is not False
    ):
        errors.append("sandbox must be enabled and fail closed")
    wrappers = {
        "python3 openpali-one-shot/scripts/docker_safe.py *",
        "./openpali-one-shot/scripts/docker_safe.py *",
    }
    excluded = sandbox.get("excludedCommands")
    if not isinstance(excluded, list) or not wrappers.issubset(set(excluded)) or "docker *" in excluded:
        errors.append("only the validated Docker wrapper may bypass the Bash sandbox")
    if "worktree" in settings:
        errors.append("settings must use the exact checkout, not a worktree")
    if (settings.get("env") or {}).get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") != "1":
        errors.append("subprocess credential scrubbing must be enabled")
    deny = (settings.get("permissions") or {}).get("deny")
    if not isinstance(deny, list) or "Bash(docker *)" not in deny:
        errors.append("settings must deny raw Docker")
    filesystem = sandbox.get("filesystem") or {}
    deny_write = set(filesystem.get("denyWrite") or [])
    protected = {
        "./openpali-one-shot/GOAL_PROMPT.txt", "./openpali-one-shot/MISSION.md",
        "./openpali-one-shot/research", "./openpali-one-shot/contract",
        "./openpali-one-shot/plugin", "./openpali-one-shot/scripts",
    }
    if not protected.issubset(deny_write):
        errors.append("immutable mission/contract/plugin/scripts are not protected")
    network = sandbox.get("network") or {}
    domains = set(network.get("allowedDomains") or [])
    if network.get("allowLocalBinding") is not True:
        errors.append("sandbox must permit local service/browser binding")
    for domain in ("services.arcgis.com", "pypi.org", "registry.npmjs.org", "docs.prefect.io", "mlflow.org", "postgis.net"):
        if domain not in domains:
            errors.append(f"sandbox network allowlist is missing {domain}")

    cli_required = (
        "--model fable", "--effort xhigh", "--permission-mode auto",
        "--strict-mcp-config", "--mcp-config", "--plugin-dir", "--settings",
        "--append-system-prompt",
    )
    for relative in ("scripts/launch.sh", "scripts/launch_headless.sh", "scripts/resume.sh", "scripts/resume_headless.sh"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for flag in cli_required:
            if flag not in text:
                errors.append(f"{relative}: missing {flag}")
        if any(flag in text for flag in ("--worktree", "--no-chrome", "--setting-sources")):
            errors.append(f"{relative}: improperly isolates the local environment")
    for relative in ("scripts/launch_headless.sh", "scripts/resume_headless.sh"):
        if "math.isfinite" not in (ROOT / relative).read_text(encoding="utf-8"):
            errors.append(f"{relative}: finite budget check is missing")
    for relative in ("scripts/resume.sh", "scripts/resume_headless.sh"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        if any(phrase not in text for phrase in ("OPENPALI_SESSION_ID", "launcher.json", "branch", "start_commit", "merge-base --is-ancestor")):
            errors.append(f"{relative}: resume lineage checks are incomplete")

    if plugin.get("name") != "openpali-one-shot":
        errors.append("plugin name mismatch")
    hook_groups = hooks.get("hooks")
    expected_hooks = {"SessionStart", "PreToolUse", "SubagentStop"}
    if not isinstance(hook_groups, dict) or set(hook_groups) != expected_hooks:
        errors.append("plugin hook set mismatch")
    else:
        serialized = json.dumps(hook_groups)
        for script in ("inject_context.py", "guardrails.py", "capture_evaluator.py"):
            if script not in serialized:
                errors.append(f"plugin hook is missing {script}")
    validate_agents(errors)

    python_paths = list((ROOT / "plugin/scripts").glob("*.py")) + list((ROOT / "scripts").glob("*.py"))
    for path in python_paths:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")

    controls = (
        list((ROOT / "scripts").glob("*"))
        + list((ROOT / "plugin/scripts").glob("*.py"))
        + [ROOT / "plugin/hooks/hooks.json", ROOT / "settings.json"]
    )
    product = (
        [ROOT / "MISSION.md", ROOT / "BASELINE.md", ROOT / "contract/acceptance.json"]
        + list((ROOT / "research").glob("*.md"))
        + list((ROOT / "plugin/agents").glob("*.md"))
    )
    control_lines, product_lines = count_lines(controls), count_lines(product)
    if control_lines >= product_lines:
        errors.append(f"control plane must remain smaller than product direction ({control_lines} >= {product_lines})")

    if errors:
        print("HARNESS: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    digest = hashlib.sha256((ROOT / "contract/acceptance.json").read_bytes()).hexdigest()
    print("HARNESS: PASS")
    print(f"GOAL_CHARS: {len(goal)}")
    print(f"TECHNICAL_MUSTS: {must}")
    print(f"HUMAN_GATES: {human}")
    print(f"CONTROL_LINES: {control_lines}")
    print(f"PRODUCT_DIRECTION_LINES: {product_lines}")
    print(f"CONTROL_TO_PRODUCT_RATIO: {control_lines / product_lines:.2f}")
    print(f"CONTRACT_SHA256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
