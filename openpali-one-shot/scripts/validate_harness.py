#!/usr/bin/env python3
"""Static validation for the siloed OpenPali one-shot control plane."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    ".gitignore",
    "README.md",
    "GOAL_PROMPT.txt",
    "SYSTEM.md",
    "MISSION.md",
    "BASELINE.md",
    "settings.json",
    "mcp.json",
    "research/BRIEF.md",
    "contract/acceptance.json",
    "contract/evidence.schema.json",
    "state/STATUS.md",
    "state/PLAN.md",
    "state/evaluator-latest.md",
    "state/evaluator/.gitkeep",
    "plugin/.claude-plugin/plugin.json",
    "plugin/hooks/hooks.json",
    "plugin/agents/repository-auditor.md",
    "plugin/agents/source-researcher.md",
    "plugin/agents/methods-reviewer.md",
    "plugin/agents/spatial-reviewer.md",
    "plugin/agents/independent-evaluator.md",
    "plugin/scripts/inject_context.py",
    "plugin/scripts/guardrails.py",
    "plugin/scripts/evaluator_protocol.py",
    "plugin/scripts/capture_evaluator.py",
    "plugin/scripts/terminal_gate.py",
    "plugin/scripts/run_observer.py",
    "scripts/preflight.sh",
    "scripts/launch.sh",
    "scripts/launch_headless.sh",
    "scripts/resume.sh",
    "scripts/resume_headless.sh",
    "scripts/test_controls.py",
    "scripts/test_observer.py",
    "state/.gitignore",
    "state/runs/.gitkeep",
)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_json(errors: list[str], relative: str) -> dict:
    path = ROOT / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"{relative}: invalid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        fail(errors, f"{relative}: top level must be an object")
        return {}
    return value


def validate_markdown_links(errors: list[str]) -> None:
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in ROOT.rglob("*.md"):
        for target in link_re.findall(path.read_text(encoding="utf-8")):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                fail(errors, f"{path.relative_to(ROOT)}: missing local link target {target}")


def validate_agents(errors: list[str]) -> None:
    names: set[str] = set()
    for path in (ROOT / "plugin" / "agents").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            fail(errors, f"{path.relative_to(ROOT)}: missing frontmatter")
            continue
        frontmatter = text.split("---", 2)[1]
        fields: dict[str, str] = {}
        for line in frontmatter.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        for key in ("name", "description", "model", "effort", "tools"):
            if not fields.get(key):
                fail(errors, f"{path.relative_to(ROOT)}: missing {key}")
        name = fields.get("name", "")
        if name in names:
            fail(errors, f"duplicate agent name: {name}")
        names.add(name)
    expected = {
        "openpali-repository-auditor",
        "openpali-source-researcher",
        "openpali-methods-reviewer",
        "openpali-spatial-reviewer",
        "openpali-independent-evaluator",
    }
    if names != expected:
        fail(errors, f"agent set mismatch: expected {sorted(expected)}, got {sorted(names)}")


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            fail(errors, f"missing required file: {relative}")

    for path in (ROOT / "scripts").glob("*.sh"):
        if not os.access(path, os.X_OK):
            fail(errors, f"{path.relative_to(ROOT)}: launch/control script must be executable")

    acceptance = load_json(errors, "contract/acceptance.json")
    evidence_schema = load_json(errors, "contract/evidence.schema.json")
    settings = load_json(errors, "settings.json")
    mcp = load_json(errors, "mcp.json")
    plugin = load_json(errors, "plugin/.claude-plugin/plugin.json")
    hooks = load_json(errors, "plugin/hooks/hooks.json")

    if acceptance:
        if acceptance.get("immutable") is not True:
            fail(errors, "acceptance contract must be immutable")
        criteria = acceptance.get("criteria")
        if not isinstance(criteria, list) or len(criteria) < 15:
            fail(errors, "acceptance contract must contain at least 15 criteria")
            criteria = []
        ids: list[str] = []
        for item in criteria:
            if not isinstance(item, dict):
                fail(errors, "acceptance criterion is not an object")
                continue
            criterion_id = str(item.get("id") or "")
            ids.append(criterion_id)
            if item.get("priority") != "MUST":
                fail(errors, f"{criterion_id}: supplied criterion must be MUST")
            if item.get("status") != "FAIL":
                fail(errors, f"{criterion_id}: initial status must be FAIL")
            if not item.get("proof") or not item.get("fail_if"):
                fail(errors, f"{criterion_id}: proof and fail_if are required")
        if len(ids) != len(set(ids)):
            fail(errors, "acceptance criterion IDs must be unique")
        schema_covered_ids: set[str] = set()
        for clause in evidence_schema.get("allOf", []) if evidence_schema else []:
            try:
                criterion_id = clause["properties"]["criteria"]["contains"]["properties"]["id"]["const"]
            except (KeyError, TypeError):
                continue
            if isinstance(criterion_id, str):
                schema_covered_ids.add(criterion_id)
        missing_schema_ids = sorted(set(ids) - schema_covered_ids)
        if missing_schema_ids:
            fail(
                errors,
                "evidence schema must require every supplied criterion exactly once; missing "
                + ", ".join(missing_schema_ids),
            )
        try:
            schema_version = evidence_schema["properties"]["schema_version"]["const"]
        except (KeyError, TypeError):
            schema_version = None
        if schema_version != "2.0.0":
            fail(errors, "evidence schema must require schema_version 2.0.0")

    goal = (ROOT / "GOAL_PROMPT.txt").read_text(encoding="utf-8").strip()
    if not goal.startswith("/goal "):
        fail(errors, "GOAL_PROMPT.txt must be a single /goal prompt")
    if len(goal) > 4000:
        fail(errors, f"GOAL_PROMPT.txt exceeds Claude Code's 4,000-character goal limit: {len(goal)}")

    sandbox = settings.get("sandbox") if settings else None
    if not isinstance(sandbox, dict) or sandbox.get("enabled") is not True:
        fail(errors, "settings must enable sandboxing")
    elif sandbox.get("failIfUnavailable") is not True or sandbox.get("allowUnsandboxedCommands") is not False:
        fail(errors, "sandbox must fail closed and disallow the escape hatch")

    worktree = settings.get("worktree") if settings else None
    if not isinstance(worktree, dict) or worktree.get("baseRef") != "head":
        fail(errors, "settings must pin worktree.baseRef to local head")

    environment = settings.get("env") if settings else None
    if not isinstance(environment, dict) or environment.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") != "1":
        fail(errors, "settings must scrub credentials from subprocess environments")
    else:
        try:
            stop_cap = int(environment.get("CLAUDE_CODE_STOP_HOOK_BLOCK_CAP", "0"))
        except (TypeError, ValueError):
            stop_cap = 0
        if stop_cap < 1000:
            fail(errors, "settings must raise Claude Code's Stop-hook override cap")

    filesystem = sandbox.get("filesystem") if isinstance(sandbox, dict) else None
    deny_write = filesystem.get("denyWrite") if isinstance(filesystem, dict) else None
    required_deny_write = {
        "./.claude",
        "./openpali-one-shot/contract",
        "./openpali-one-shot/plugin",
        "./openpali-one-shot/scripts",
        "./openpali-one-shot/state/evaluator-latest.md",
        "./openpali-one-shot/state/evaluator-attestation.json",
        "./openpali-one-shot/state/evaluator",
    }
    if not isinstance(deny_write, list) or not required_deny_write.issubset(set(deny_write)):
        fail(errors, "sandbox must deny subprocess writes to immutable/evaluator controls")

    permissions = settings.get("permissions") if settings else None
    permission_denies = permissions.get("deny") if isinstance(permissions, dict) else None
    required_edit_denies = {
        "Edit(/openpali-one-shot/contract/**)",
        "Edit(/openpali-one-shot/plugin/**)",
        "Edit(/openpali-one-shot/scripts/**)",
        "Edit(/openpali-one-shot/state/evaluator-latest.md)",
        "Edit(/openpali-one-shot/state/evaluator-attestation.json)",
        "Edit(/openpali-one-shot/state/evaluator/**)",
    }
    if not isinstance(permission_denies, list) or not required_edit_denies.issubset(set(permission_denies)):
        fail(errors, "permissions must deny built-in edits to immutable/evaluator controls")

    network = sandbox.get("network") if isinstance(sandbox, dict) else None
    allowed_domains = network.get("allowedDomains") if isinstance(network, dict) else None
    if not isinstance(network, dict) or network.get("allowLocalBinding") is not True:
        fail(errors, "sandbox must allow local dev/E2E server binding")
    required_source_domains = {
        "services.arcgis.com",
        "services5.arcgis.com",
        "tiles.arcgis.com",
        "maps.lacity.org",
        "data.lacity.org",
        "mlb-pptsrv.ci.malibu.ca.us",
        "svc.pictometry.com",
    }
    if not isinstance(allowed_domains, list) or not required_source_domains.issubset(set(allowed_domains)):
        fail(errors, "sandbox network allowlist omits a current source adapter host")

    if mcp.get("mcpServers") != {}:
        fail(errors, "mcp.json must declare an explicit empty MCP surface")

    required_cli_controls = (
        "--model fable",
        "--effort xhigh",
        "--no-chrome",
        "--strict-mcp-config",
        "--mcp-config",
        "--setting-sources project",
        "--tools \"Bash,Edit,Read,Write,Grep,Glob,Agent,WebFetch,WebSearch\"",
        "--plugin-dir",
        "--settings",
    )
    for relative in ("scripts/launch.sh", "scripts/launch_headless.sh", "scripts/resume.sh", "scripts/resume_headless.sh"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for control in required_cli_controls:
            if control not in text:
                fail(errors, f"{relative}: missing CLI isolation control {control}")
    for relative in ("scripts/launch_headless.sh", "scripts/resume_headless.sh"):
        if "math.isfinite" not in (ROOT / relative).read_text(encoding="utf-8"):
            fail(errors, f"{relative}: spend cap must reject NaN and infinity")

    if plugin.get("name") != "openpali-one-shot":
        fail(errors, "plugin name mismatch")
    hook_groups = hooks.get("hooks") if hooks else None
    if not isinstance(hook_groups, dict):
        fail(errors, "plugin hooks missing")
    else:
        for event in ("SessionStart", "PreToolUse", "SubagentStop", "Stop", "SessionEnd"):
            if event not in hook_groups:
                fail(errors, f"plugin hook missing {event}")
        expected_hook_scripts = {
            "SessionStart": {"inject_context.py", "run_observer.py"},
            "PreToolUse": {"guardrails.py"},
            "SubagentStop": {"capture_evaluator.py"},
            "Stop": {"terminal_gate.py"},
            "SessionEnd": {"run_observer.py"},
        }
        for event, expected_scripts in expected_hook_scripts.items():
            groups = hook_groups.get(event)
            observed_scripts: set[str] = set()
            if isinstance(groups, list):
                for group in groups:
                    if not isinstance(group, dict):
                        continue
                    handlers = group.get("hooks")
                    if not isinstance(handlers, list):
                        continue
                    for handler in handlers:
                        if not isinstance(handler, dict):
                            continue
                        arguments = handler.get("args")
                        command = " ".join(
                            [str(handler.get("command") or "")]
                            + ([str(item) for item in arguments] if isinstance(arguments, list) else [])
                        )
                        observed_scripts.update(
                            re.findall(r"/scripts/([A-Za-z0-9_.-]+\.py)", command)
                        )
            if observed_scripts != expected_scripts:
                fail(
                    errors,
                    f"plugin {event} binding mismatch: expected {sorted(expected_scripts)}, "
                    f"got {sorted(observed_scripts)}",
                )

    for path in (ROOT / "plugin" / "scripts").glob("*.py"):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            fail(errors, f"{path.relative_to(ROOT)}: Python syntax error: {exc}")

    try:
        ast.parse(
            (ROOT / "scripts" / "test_controls.py").read_text(encoding="utf-8"),
            filename="scripts/test_controls.py",
        )
    except SyntaxError as exc:
        fail(errors, f"scripts/test_controls.py: Python syntax error: {exc}")
    try:
        ast.parse(
            (ROOT / "scripts" / "test_observer.py").read_text(encoding="utf-8"),
            filename="scripts/test_observer.py",
        )
    except SyntaxError as exc:
        fail(errors, f"scripts/test_observer.py: Python syntax error: {exc}")

    validate_agents(errors)
    validate_markdown_links(errors)

    if errors:
        print("HARNESS: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    contract = ROOT / "contract" / "acceptance.json"
    digest = hashlib.sha256(contract.read_bytes()).hexdigest()
    print("HARNESS: PASS")
    print(f"GOAL_CHARS: {len(goal)}")
    print(f"CRITERIA: {len(acceptance['criteria'])}")
    print(f"CONTRACT_SHA256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
