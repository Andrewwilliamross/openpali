#!/usr/bin/env python3
"""Block contract mutation and out-of-scope destructive/external commands."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROTECTED_SUFFIXES = (
    "/openpali-one-shot/GOAL_PROMPT.txt",
    "/openpali-one-shot/README.md",
    "/openpali-one-shot/SYSTEM.md",
    "/openpali-one-shot/MISSION.md",
    "/openpali-one-shot/BASELINE.md",
    "/openpali-one-shot/settings.json",
    "/openpali-one-shot/mcp.json",
    "/openpali-one-shot/research/",
    "/openpali-one-shot/contract/",
    "/openpali-one-shot/plugin/",
    "/openpali-one-shot/scripts/",
    "/openpali-one-shot/state/evaluator-latest.md",
    "/openpali-one-shot/state/evaluator-attestation.json",
)

DANGEROUS_BASH = (
    (r"(?:^|[;&|]\s*)docker\s", "Direct Docker access is forbidden; use openpali-one-shot/scripts/docker_safe.py with a repository-scoped Compose file."),
    (r"\bgit\s+push\b", "Git push is outside this experiment."),
    (r"\bgit\s+pull\b", "Git pull can change the controlled starting state."),
    (r"\bgit\s+fetch\b", "Git fetch can change the controlled starting refs mid-run."),
    (r"\bgit\s+reset\s+--hard\b", "Destructive Git reset is forbidden."),
    (r"\bgit\s+clean\b", "Git clean can delete user-owned files."),
    (r"\bgit\s+stash\b", "Do not hide pre-existing or run state in a stash."),
    (r"\bgit\s+(?:checkout\s+--|restore\b)", "Do not discard working-tree changes."),
    (r"\bgit\s+branch\s+-D\b", "Force-deleting branches is forbidden."),
    (r"\bgh\b", "GitHub CLI access is outside this local implementation run."),
    (r"\brm\s+-[^\n]*r[^\n]*f\b|\brm\s+-rf\b", "Recursive forced deletion is forbidden."),
    (r"\b(?:npm\s+publish|pnpm\s+publish|yarn\s+npm\s+publish|twine\s+upload)\b", "Package publication is outside scope."),
    (r"\b(?:terraform|pulumi)\s+(?:apply|destroy|up)\b", "Cloud/infrastructure mutation is outside scope."),
    (r"\b(?:kubectl|helm)\s+(?:apply|create|delete|replace|upgrade|install|uninstall)\b", "Cluster mutation is outside scope."),
    (r"\b(?:aws|gcloud|az)\b", "Cloud CLI access is outside this local experiment."),
    (r"\b(?:vercel|netlify|wrangler|flyctl|firebase)\s+(?:deploy|publish)\b", "Production deployment is outside scope."),
    (r"(?:^|[;&|]\s*)(?:curl|wget|http|https)(?:\s|$)", "Ad-hoc network clients are blocked; use read-only WebFetch/WebSearch or tested source adapters."),
    (r"(?:^|[;&|]\s*)(?:printenv|env|set|export\s+-p)\s*(?:$|[;&|])", "Enumerating the session environment can expose credentials."),
    (r"\bsecurity\s+find-", "Reading macOS Keychain entries is forbidden."),
)

MUTATING_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)(?:rm|mv|cp|truncate|tee|chmod|chown)\b|"
    r"\bsed\s+-i\b|\bperl\s+-p?i\b|(?:^|[^<])>{1,2}\s*[^&]",
    re.IGNORECASE,
)
SAFE_DOCKER_WRAPPER = re.compile(
    r"^\s*(?:python3\s+openpali-one-shot/scripts/docker_safe\.py|"
    r"\./openpali-one-shot/scripts/docker_safe\.py)"
    r"(?:\s+[^;&|`$<>\n]+)?\s*$"
)


def deny(reason: str) -> int:
    print(f"OpenPali one-shot guardrail: {reason}", file=sys.stderr)
    return 2


def normalized_path(raw: object, cwd: Path) -> str:
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path.resolve(strict=False).as_posix()


def is_protected(path: str) -> bool:
    return any(suffix in path or path.endswith(suffix.rstrip("/")) for suffix in PROTECTED_SUFFIXES)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return deny("could not parse tool input; fail closed")

    tool_name = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return deny("malformed tool input; fail closed")
    cwd = Path(str(event.get("cwd") or Path.cwd())).resolve()

    if tool_name in {"Write", "Edit", "NotebookEdit"}:
        candidates = [
            tool_input.get("file_path"),
            tool_input.get("path"),
            tool_input.get("notebook_path"),
        ]
        for candidate in candidates:
            if candidate and is_protected(normalized_path(candidate, cwd)):
                return deny(
                    "MISSION, acceptance, baseline, plugin, settings, and launch "
                    "controls are immutable; record proposed corrections in state/"
                )
        return 0

    if tool_name != "Bash":
        return 0

    command = str(tool_input.get("command") or "")
    if "openpali-one-shot/scripts/docker_safe.py" in command and not SAFE_DOCKER_WRAPPER.fullmatch(command):
        return deny("the unsandboxed Docker wrapper must be the entire simple command")
    for pattern, reason in DANGEROUS_BASH:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return deny(reason)

    protected_reference = any(token.lstrip("/") in command for token in PROTECTED_SUFFIXES)
    if protected_reference and MUTATING_COMMAND.search(command):
        return deny("a shell command attempted to mutate protected harness controls")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
