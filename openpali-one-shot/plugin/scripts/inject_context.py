#!/usr/bin/env python3
"""Re-inject compact mission invariants and current state on session lifecycle events."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


def project_root(event: dict[str, object]) -> Path:
    configured = os.environ.get("CLAUDE_PROJECT_DIR")
    if configured:
        return Path(configured).resolve()
    return Path(str(event.get("cwd") or Path.cwd())).resolve()


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        event = {}

    task = project_root(event) / "openpali-one-shot"
    system_path = task / "SYSTEM.md"
    status_path = task / "state" / "STATUS.md"
    contract_path = task / "contract" / "acceptance.json"

    if not system_path.exists() or not contract_path.exists():
        print(json.dumps({
            "continue": False,
            "stopReason": (
                "OpenPali task context is missing from this checkout. "
                "Restore the committed task folder before any model turn."
            ),
        }))
        return 0

    digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    status = status_path.read_text(encoding="utf-8") if status_path.exists() else "State file missing."

    print("OPENPALI PRODUCT BUILD CONTEXT (re-injected on startup/resume/compaction)")
    print(f"Acceptance contract SHA256: {digest}")
    print("\n--- OPERATING CONTRACT ---")
    print(system_path.read_text(encoding="utf-8").strip())
    print("\n--- CURRENT COMPACT STATUS ---")
    print(status.strip())
    print("\nRe-read openpali-one-shot/MISSION.md, openpali-one-shot/research/production-mvp-architecture.md, and the relevant openpali-one-shot/contract/acceptance.json items before choosing product work. Do not expand the harness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
