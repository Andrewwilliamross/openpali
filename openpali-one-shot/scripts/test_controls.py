#!/usr/bin/env python3
"""Behavior tests for the task-local Claude Code control scripts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS = ROOT / "plugin" / "scripts"


def run_hook(
    script: str,
    payload: dict,
    *,
    project: Path | None = None,
    home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    if home is not None:
        env["HOME"] = str(home)
    return subprocess.run(
        ["python3", str(PLUGIN_SCRIPTS / script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


class GuardrailTests(unittest.TestCase):
    def test_protected_contract_edit_is_blocked(self) -> None:
        result = run_hook(
            "guardrails.py",
            {
                "tool_name": "Edit",
                "cwd": "/tmp/openpali",
                "tool_input": {"file_path": "openpali-one-shot/contract/acceptance.json"},
            },
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("immutable", result.stderr)

    def test_mutable_status_edit_is_allowed(self) -> None:
        result = run_hook(
            "guardrails.py",
            {
                "tool_name": "Edit",
                "cwd": "/tmp/openpali",
                "tool_input": {"file_path": "openpali-one-shot/state/STATUS.md"},
            },
        )
        self.assertEqual(result.returncode, 0)

    def test_push_and_destructive_git_are_blocked(self) -> None:
        for command in (
            "git push origin branch",
            "git reset --hard HEAD",
            "git clean -fd",
            "printenv",
            "security find-generic-password -s token",
        ):
            with self.subTest(command=command):
                result = run_hook(
                    "guardrails.py",
                    {"tool_name": "Bash", "cwd": "/tmp/openpali", "tool_input": {"command": command}},
                )
                self.assertEqual(result.returncode, 2)

    def test_read_only_contract_hash_is_allowed(self) -> None:
        result = run_hook(
            "guardrails.py",
            {
                "tool_name": "Bash",
                "cwd": "/tmp/openpali",
                "tool_input": {"command": "shasum -a 256 openpali-one-shot/contract/acceptance.json"},
            },
        )
        self.assertEqual(result.returncode, 0)

    def test_url_argument_is_not_mistaken_for_network_client(self) -> None:
        result = run_hook(
            "guardrails.py",
            {
                "tool_name": "Bash",
                "cwd": "/tmp/openpali",
                "tool_input": {"command": "python3 verify_source.py https://example.org/schema"},
            },
        )
        self.assertEqual(result.returncode, 0)

    def test_network_client_and_manual_evaluator_capture_are_blocked(self) -> None:
        for command in (
            "curl https://example.org/schema",
            "python3 openpali-one-shot/plugin/scripts/capture_evaluator.py",
        ):
            with self.subTest(command=command):
                result = run_hook(
                    "guardrails.py",
                    {"tool_name": "Bash", "cwd": "/tmp/openpali", "tool_input": {"command": command}},
                )
                self.assertEqual(result.returncode, 2)

    def test_evaluator_attestation_is_hook_owned_but_can_be_staged(self) -> None:
        edit = run_hook(
            "guardrails.py",
            {
                "tool_name": "Edit",
                "cwd": "/tmp/openpali",
                "tool_input": {"file_path": "openpali-one-shot/state/evaluator-attestation.json"},
            },
        )
        stage = run_hook(
            "guardrails.py",
            {
                "tool_name": "Bash",
                "cwd": "/tmp/openpali",
                "tool_input": {"command": "git add openpali-one-shot/state/evaluator-attestation.json"},
            },
        )
        self.assertEqual(edit.returncode, 2)
        self.assertEqual(stage.returncode, 0)


class OneShotGitFixture:
    def __init__(self, temporary: str, *, blocked_id: str | None = None) -> None:
        self.project = Path(temporary)
        self.home = self.project
        self.blocked_id = blocked_id
        self.contract_path = self.project / "openpali-one-shot" / "contract" / "acceptance.json"
        self.state = self.project / "openpali-one-shot" / "state"
        self.parent_transcript = self.project / ".claude" / "main.jsonl"
        self.agent_transcript = self.project / ".claude" / "agent.jsonl"
        self.session_id = "session-test-001"
        self.agent_id = "agent-test-001"

        self.contract_path.parent.mkdir(parents=True)
        self.state.joinpath("evidence").mkdir(parents=True)
        self.state.joinpath("evaluator").mkdir(parents=True)
        self.parent_transcript.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "contract" / "acceptance.json", self.contract_path)
        (self.state / "evaluator-latest.md").write_text("VERDICT: NOT_RUN\n", encoding="utf-8")
        (self.state / "evidence" / "gate.log").write_text("all synthetic harness checks passed\n", encoding="utf-8")
        (self.state / "evaluator" / ".gitkeep").write_text("", encoding="utf-8")
        (self.project / ".gitignore").write_text(".claude/\n", encoding="utf-8")
        self.parent_transcript.write_text("{}\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Harness Test")
        self.git("config", "user.email", "harness@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "release candidate")
        self.candidate = self.git("rev-parse", "HEAD").stdout.strip()
        self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        self.contract_hash = hashlib.sha256(self.contract_path.read_bytes()).hexdigest()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(self.project), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"git {' '.join(arguments)} failed: {result.stderr}")
        return result

    def evaluator_message(self) -> str:
        verdict = "FAIL" if self.blocked_id else "PASS"
        rows = []
        for item in self.contract["criteria"]:
            status = "FAIL" if item["id"] == self.blocked_id else "PASS"
            rows.append(f"- {item['id']}: {status} — independently verified at candidate commit")
        failure = (
            f"- {self.blocked_id} awaits an external sponsor decision; release remains safely disabled"
            if self.blocked_id
            else "- none"
        )
        return (
            f"VERDICT: {verdict}\n"
            f"COMMIT: {self.candidate}\n"
            f"CONTRACT_SHA256: {self.contract_hash}\n"
            "CONFIDENCE: high\n\n"
            "MUST RESULTS\n"
            + "\n".join(rows)
            + "\n\nCOMMANDS\n"
            "- python3 full_gate.py — exit 0 with synthetic fixture\n\n"
            "FAILURES\n"
            f"{failure}\n\n"
            "UNTESTED RISKS\n"
            "- none material\n"
        )

    def capture(self, message: str | None = None) -> subprocess.CompletedProcess[str]:
        final_message = message or self.evaluator_message()
        self.agent_transcript.write_text(
            json.dumps({"message": {"content": [{"type": "text", "text": final_message}]}}) + "\n",
            encoding="utf-8",
        )
        return run_hook(
            "capture_evaluator.py",
            {
                "hook_event_name": "SubagentStop",
                "cwd": str(self.project),
                "session_id": self.session_id,
                "transcript_path": str(self.parent_transcript),
                "agent_id": self.agent_id,
                "agent_type": "openpali-one-shot:openpali-independent-evaluator",
                "agent_transcript_path": str(self.agent_transcript),
                "last_assistant_message": final_message,
            },
            project=self.project,
            home=self.home,
        )

    def seal_results(self) -> None:
        log = self.state / "evidence" / "gate.log"
        evidence_id = "full-gate-log"
        attestation = json.loads((self.state / "evaluator-attestation.json").read_text())
        evaluator_archive_relative = attestation["archive_path"]
        evaluator_archive = self.project / evaluator_archive_relative
        evaluator_evidence_id = "final-evaluator-output"
        criteria = []
        for criterion in self.contract["criteria"]:
            blocked = criterion["id"] == self.blocked_id
            criteria.append(
                {
                    "id": criterion["id"],
                    "status": "BLOCKED" if blocked else "PASS",
                    "proof_results": [
                        {
                            "index": index,
                            "status": "BLOCKED" if blocked and index == 0 else "PASS",
                            "evidence_ids": [
                                evaluator_evidence_id
                                if criterion["id"] == "RELEASE-001" and index == 0
                                else evidence_id
                            ],
                        }
                        for index, _proof in enumerate(criterion["proof"])
                    ],
                    "fail_if_results": [
                        {"index": index, "triggered": False, "evidence_ids": [evidence_id]}
                        for index, _failure in enumerate(criterion["fail_if"])
                    ],
                }
            )
        blockers = []
        if self.blocked_id:
            blockers.append(
                {
                    "criterion_ids": [self.blocked_id],
                    "category": "scope_decision",
                    "decision_owner": "Andrew Ross",
                    "decision_needed": "Approve the documented sponsor-owned release decision.",
                    "safe_default": "Keep the affected release capability disabled by default.",
                    "evidence_ids": [evidence_id],
                    "resume_command": "python3 scripts/full_gate.py",
                }
            )
        results = {
            "schema_version": "2.0.0",
            "contract_version": self.contract["contract_version"],
            "contract_sha256": self.contract_hash,
            "release_candidate_commit": self.candidate,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "terminal_state": "BLOCKED_EXTERNAL" if self.blocked_id else "PASS",
            "summary": "Synthetic fixture demonstrating deterministic terminal evidence validation.",
            "criteria": criteria,
            "evidence": [
                {
                    "id": evidence_id,
                    "kind": "command",
                    "command": "python3 full_gate.py",
                    "exit_code": 0,
                    "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "commit": self.candidate,
                    "result": "all synthetic harness checks passed",
                    "artifact": "openpali-one-shot/state/evidence/gate.log",
                    "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                },
                {
                    "id": evaluator_evidence_id,
                    "kind": "review",
                    "observed_at": attestation["captured_at"],
                    "commit": self.candidate,
                    "result": "exact final independent evaluator output",
                    "artifact": evaluator_archive_relative,
                    "sha256": hashlib.sha256(evaluator_archive.read_bytes()).hexdigest(),
                }
            ],
            "external_blockers": blockers,
            "stall_cycles": [],
        }
        (self.state / "acceptance-results.json").write_text(
            json.dumps(results, indent=2) + "\n", encoding="utf-8"
        )
        self.git("add", "openpali-one-shot/state")
        self.git("commit", "-qm", "seal terminal evidence")

    def stop(self) -> subprocess.CompletedProcess[str]:
        return run_hook(
            "terminal_gate.py",
            {
                "hook_event_name": "Stop",
                "cwd": str(self.project),
                "session_id": self.session_id,
                "transcript_path": str(self.parent_transcript),
                "stop_hook_active": True,
                "last_assistant_message": "terminal report",
            },
            project=self.project,
            home=self.home,
        )


class LifecycleHookTests(unittest.TestCase):
    def test_context_injection_contains_contract_and_status(self) -> None:
        project = ROOT.parent
        result = run_hook(
            "inject_context.py",
            {"cwd": str(project), "hook_event_name": "SessionStart"},
            project=project,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Acceptance contract SHA256", result.stdout)
        self.assertIn("CURRENT COMPACT STATUS", result.stdout)

    def test_context_injection_fails_closed_without_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            result = run_hook(
                "inject_context.py",
                {"cwd": str(project), "hook_event_name": "SessionStart"},
                project=project,
            )
            self.assertEqual(result.returncode, 0)
            decision = json.loads(result.stdout)
            self.assertIs(decision["continue"], False)
            self.assertIn("control plane", decision["stopReason"])

    def test_scoped_evaluator_output_is_captured_and_attested_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OneShotGitFixture(temporary)
            message = fixture.evaluator_message()
            result = fixture.capture(message)
            self.assertEqual(result.returncode, 0)
            self.assertEqual((fixture.state / "evaluator-latest.md").read_text(), message)
            attestation = json.loads((fixture.state / "evaluator-attestation.json").read_text())
            self.assertIs(attestation["valid"], True)
            self.assertEqual(attestation["release_candidate_commit"], fixture.candidate)
            self.assertEqual(attestation["agent_type"], "openpali-one-shot:openpali-independent-evaluator")
            archives = list((fixture.state / "evaluator").glob("evaluator-*.md"))
            self.assertEqual(len(archives), 1)
            self.assertEqual(archives[0].read_text(), message)

    def test_rejected_evaluator_capture_does_not_dirty_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OneShotGitFixture(temporary)
            bad = fixture.evaluator_message().replace(fixture.candidate, fixture.candidate[:7], 1)
            result = fixture.capture(bad)
            self.assertEqual(result.returncode, 2)
            self.assertEqual((fixture.state / "evaluator-latest.md").read_text(), "VERDICT: NOT_RUN\n")
            self.assertFalse((fixture.state / "evaluator-attestation.json").exists())
            self.assertEqual(fixture.git("status", "--porcelain=v1", "--untracked-files=all").stdout, "")

    def test_evaluator_capture_requires_real_parent_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OneShotGitFixture(temporary)
            message = fixture.evaluator_message()
            fixture.agent_transcript.write_text(
                json.dumps({"message": {"content": [{"type": "text", "text": message}]}}) + "\n",
                encoding="utf-8",
            )
            result = run_hook(
                "capture_evaluator.py",
                {
                    "hook_event_name": "SubagentStop",
                    "cwd": str(fixture.project),
                    "session_id": fixture.session_id,
                    "transcript_path": "",
                    "agent_id": fixture.agent_id,
                    "agent_type": "openpali-one-shot:openpali-independent-evaluator",
                    "agent_transcript_path": str(fixture.agent_transcript),
                    "last_assistant_message": message,
                },
                project=fixture.project,
                home=fixture.home,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse((fixture.state / "evaluator-attestation.json").exists())
            self.assertEqual(fixture.git("status", "--porcelain=v1", "--untracked-files=all").stdout, "")

    def test_terminal_gate_accepts_pass_with_one_evidence_only_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OneShotGitFixture(temporary)
            self.assertEqual(fixture.capture().returncode, 0)
            fixture.seal_results()
            result = fixture.stop()
            self.assertEqual(result.returncode, 0)
            decision = json.loads(result.stdout)
            self.assertNotIn("decision", decision)
            self.assertIn("accepted PASS", decision["systemMessage"])

    def test_terminal_gate_accepts_exact_external_block_mapping_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OneShotGitFixture(temporary, blocked_id="GOV-001")
            self.assertEqual(fixture.capture().returncode, 0)
            fixture.seal_results()
            result = fixture.stop()
            decision = json.loads(result.stdout)
            self.assertNotIn("decision", decision)
            self.assertIn("accepted BLOCKED_EXTERNAL", decision["systemMessage"])

    def test_terminal_gate_rejects_missing_supplied_criterion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OneShotGitFixture(temporary)
            self.assertEqual(fixture.capture().returncode, 0)
            fixture.seal_results()
            results_path = fixture.state / "acceptance-results.json"
            results = json.loads(results_path.read_text())
            results["criteria"].pop()
            results_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
            fixture.git("add", str(results_path.relative_to(fixture.project)))
            fixture.git("commit", "--amend", "--no-edit", "-q")
            decision = json.loads(fixture.stop().stdout)
            self.assertEqual(decision["decision"], "block")
            self.assertIn("omitted supplied MUST", decision["reason"])

    def test_terminal_gate_rejects_tampered_evaluator_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OneShotGitFixture(temporary)
            self.assertEqual(fixture.capture().returncode, 0)
            fixture.seal_results()
            with fixture.agent_transcript.open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            decision = json.loads(fixture.stop().stdout)
            self.assertEqual(decision["decision"], "block")
            self.assertIn("transcript hash changed", decision["reason"])

    def test_stalled_is_report_only_even_with_shaped_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = OneShotGitFixture(temporary)
            self.assertEqual(fixture.capture().returncode, 0)
            fixture.seal_results()
            results_path = fixture.state / "acceptance-results.json"
            results = json.loads(results_path.read_text())
            results["terminal_state"] = "STALLED"
            results["stall_cycles"] = [
                {
                    "cycle": index,
                    "commit": fixture.candidate,
                    "started_at": "2026-07-11T00:00:00Z",
                    "ended_at": "2026-07-11T00:01:00Z",
                    "repair_or_replan": "Repeated synthetic repair attempt",
                    "observed_result": "No accepted synthetic improvement",
                    "evidence_ids": ["full-gate-log"],
                }
                for index in range(1, 4)
            ]
            results_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
            fixture.git("add", str(results_path.relative_to(fixture.project)))
            fixture.git("commit", "--amend", "--no-edit", "-q")
            decision = json.loads(fixture.stop().stdout)
            self.assertEqual(decision["decision"], "block")
            self.assertIn("reportable recovery state", decision["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
