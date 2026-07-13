#!/usr/bin/env python3
"""Behavioral tests for the small safety and terminal-evidence boundary."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace


TASK = Path(__file__).resolve().parents[1]
ROOT = TASK.parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_guardrail(tool_name: str, tool_input: dict[str, object]) -> subprocess.CompletedProcess[str]:
    event = {"tool_name": tool_name, "tool_input": tool_input, "cwd": str(ROOT)}
    return subprocess.run(
        [sys.executable, str(TASK / "plugin/scripts/guardrails.py")],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=False,
    )


class GuardrailTests(unittest.TestCase):
    def test_mutable_state_write_is_allowed(self) -> None:
        result = run_guardrail("Write", {"file_path": "openpali-one-shot/state/STATUS.md"})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_contract_write_is_denied(self) -> None:
        result = run_guardrail("Edit", {"file_path": "openpali-one-shot/MISSION.md"})
        self.assertEqual(result.returncode, 2)

    def test_direct_docker_and_push_are_denied(self) -> None:
        docker = run_guardrail("Bash", {"command": "docker run -v $HOME/.ssh:/loot image"})
        push = run_guardrail("Bash", {"command": "git push origin HEAD"})
        self.assertEqual(docker.returncode, 2)
        self.assertEqual(push.returncode, 2)

    def test_safe_wrapper_command_is_allowed(self) -> None:
        result = run_guardrail(
            "Bash",
            {"command": "python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_safe_wrapper_cannot_smuggle_a_second_command(self) -> None:
        result = run_guardrail(
            "Bash",
            {"command": "python3 openpali-one-shot/scripts/docker_safe.py version; python3 -c 'print(1)'"},
        )
        self.assertEqual(result.returncode, 2)


class DockerWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wrapper = load_module("openpali_docker_safe", TASK / "scripts/docker_safe.py")

    def test_safe_config_passes(self) -> None:
        self.wrapper.validate_config(
            {
                "volumes": {"data": {"name": "openpali-local_data"}},
                "networks": {"backend": {"name": "openpali-local_backend", "internal": True}},
                "services": {
                    "api": {
                        "build": {"context": str(ROOT / "pipeline")},
                        "networks": {"backend": None},
                        "ports": [{"target": 8000, "published": "8000", "host_ip": "127.0.0.1"}],
                        "volumes": [{"type": "volume", "source": "data", "target": "/data"}],
                    }
                }
            }
        )

    def assert_unsafe(self, config: dict[str, object], phrase: str) -> None:
        with self.assertRaisesRegex(ValueError, phrase):
            self.wrapper.validate_config(config)

    def test_host_mount_socket_privilege_and_public_port_fail(self) -> None:
        self.assert_unsafe(
            {"services": {"x": {"volumes": [{"type": "bind", "source": str(Path.home()), "target": "/host"}]}}},
            "escapes the repository",
        )
        self.assert_unsafe(
            {"services": {"x": {"volumes": [{"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}]}}},
            "Docker socket",
        )
        self.assert_unsafe({"services": {"x": {"privileged": True}}}, "privileged")
        self.assert_unsafe(
            {"services": {"x": {"ports": [{"target": 80, "published": "8080"}]}}},
            "loopback",
        )

    def test_runtime_escape_flags_fail(self) -> None:
        for arguments in (
            ["run", "--volume", "/:/host", "api"],
            ["exec", "--privileged", "api", "sh"],
            ["build", "--ssh", "default"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.wrapper.validate_runtime_arguments(arguments, arguments[0])

    def test_external_resources_secrets_images_and_egress_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "external resources"):
            self.wrapper.validate_config({"volumes": {"data": {"external": True}}, "services": {}})
        with self.assertRaisesRegex(ValueError, "driver options"):
            self.wrapper.validate_config(
                {"volumes": {"data": {"driver_opts": {"type": "none", "device": "/var/run", "o": "bind"}}}, "services": {}}
            )
        with self.assertRaisesRegex(ValueError, "explicit volume drivers"):
            self.wrapper.validate_config({"volumes": {"data": {"driver": "local"}}, "services": {}})
        with self.assertRaisesRegex(ValueError, "API socket"):
            self.wrapper.validate_config({"services": {"x": {"use_api_socket": True}}})
        internal = {"backend": {"name": "openpali-local_backend", "internal": True}}
        with self.assertRaisesRegex(ValueError, "pinned"):
            self.wrapper.validate_config(
                {"networks": internal, "services": {"x": {"image": "busybox:latest", "networks": {"backend": None}}}}
            )
        with self.assertRaisesRegex(ValueError, "locally built image tags"):
            self.wrapper.validate_config(
                {"networks": internal, "services": {"x": {"build": {"context": str(ROOT / "pipeline")}, "image": "evil.example/image:tag", "networks": {"backend": None}}}}
            )
        pinned = "busybox@sha256:" + "a" * 64
        with self.assertRaisesRegex(ValueError, "local-only fixture credential"):
            self.wrapper.validate_config(
                {"networks": internal, "services": {"x": {"image": pinned, "networks": {"backend": None}, "environment": {"API_TOKEN": "real-secret"}}}}
            )
        egress = {"egress": {"name": "openpali-local_egress", "internal": False}}
        with self.assertRaisesRegex(ValueError, "only the labeled egress proxy"):
            self.wrapper.validate_config(
                {"networks": egress, "services": {"x": {"image": pinned, "networks": {"egress": None}}}}
            )

    def test_docker_cli_uses_isolated_home(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openpali-home-") as temporary:
            environment = self.wrapper.docker_environment(Path(temporary))
            self.assertEqual(environment["HOME"], temporary)
            self.assertNotEqual(environment["HOME"], str(Path.home()))
            self.assertEqual(environment["DOCKER_HOST"], "unix:///var/run/docker.sock")
        self.assertNotIn("run", self.wrapper.ALLOWED_COMMANDS)
        self.assertNotIn("exec", self.wrapper.ALLOWED_COMMANDS)

    def test_build_or_bind_context_with_local_env_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix=".openpali-secret-", dir=ROOT) as temporary:
            (Path(temporary) / ".env.local").write_text("TOKEN=secret\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sensitive local file"):
                self.wrapper.validate_content_root(Path(temporary), "test context")

    def test_compose_indirection_and_project_collision_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix=".openpali-wrapper-", dir=ROOT) as temporary:
            path = Path(temporary) / "compose.yaml"
            path.write_text('services:\n  api:\n    image: busybox\n    "env_file": ../../.env\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "indirection"):
                self.wrapper.parse_args(["-f", str(path), "config"])
        with self.assertRaisesRegex(ValueError, "project names"):
            self.wrapper.validate_project_name("someone-elses-project")
        with self.assertRaisesRegex(ValueError, "unsupported Compose global flag"):
            self.wrapper.parse_args(["--context=remote", "version"])

    def test_rendered_safe_compose_passes_without_starting_services(self) -> None:
        with tempfile.TemporaryDirectory(prefix=".openpali-compose-", dir=ROOT) as temporary:
            path = Path(temporary) / "compose.yaml"
            path.write_text(
                "services:\n"
                "  api:\n"
                "    build:\n"
                "      context: ../pipeline\n"
                "    networks: [backend]\n"
                "    volumes: [data:/data]\n"
                "  egress-proxy:\n"
                f"    image: busybox@sha256:{'a' * 64}\n"
                "    labels:\n"
                "      org.openpali.egress-proxy: 'true'\n"
                "    networks: [backend, egress]\n"
                "volumes:\n"
                "  data: {}\n"
                "networks:\n"
                "  backend:\n"
                "    internal: true\n"
                "  egress: {}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(TASK / "scripts/docker_safe.py"), "--validate-only", "-f", str(path), "up"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DOCKER_COMPOSE_CONFIG: PASS", result.stdout)


class EvaluatorCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = load_module(
            "openpali_capture_evaluator", TASK / "plugin/scripts/capture_evaluator.py"
        )
        cls.contract = json.loads((TASK / "contract/acceptance.json").read_text(encoding="utf-8"))
        cls.must_ids = [
            item["id"] for item in cls.contract["criteria"] if item["priority"] == "MUST"
        ]

    def message(self, verdict: str, commit: str, contract_hash: str) -> str:
        status = "PASS" if verdict == "PASS" else "FAIL"
        results = "\n".join(f"- {item}: {status} — exercised result" for item in self.must_ids)
        return (
            f"VERDICT: {verdict}\nCOMMIT: {commit}\nCONTRACT_SHA256: {contract_hash}\n"
            "CONFIDENCE: high\n\nCOMPONENT MATRIX\n- stack: result\n\nMUST RESULTS\n"
            f"{results}\n\nHUMAN GATE\n- APPROVAL-001: UNRESOLVED — safe default\n\n"
            "COMMANDS\n- check — result\n\nFAILURES\n- none\n\nUNTESTED RISKS\n- none material"
        )

    def run_capture(self, verdict: str, *, stop_hook_active: bool = False) -> tuple[int, Path]:
        temporary = Path(tempfile.mkdtemp(prefix="openpali-capture-"))
        self.addCleanup(shutil.rmtree, temporary, ignore_errors=True)
        task = temporary / "openpali-one-shot"
        (task / "contract").mkdir(parents=True)
        (task / "state").mkdir()
        contract_path = task / "contract/acceptance.json"
        contract_path.write_text(json.dumps(self.contract), encoding="utf-8")
        (task / "state/evaluator-latest.md").write_text("No final evaluation captured.\n", encoding="utf-8")
        transcript = temporary / "transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")
        commit = "a" * 40
        contract_hash = self.capture.digest_file(contract_path)
        message = self.message(verdict, commit, contract_hash)
        event = {
            "agent_type": "openpali-independent-evaluator",
            "last_assistant_message": message,
            "agent_transcript_path": str(transcript),
            "session_id": "session",
            "agent_id": "agent",
            "cwd": str(temporary),
            "stop_hook_active": stop_hook_active,
        }
        original_git = self.capture.git
        original_home_locator = self.capture.home_locator
        original_contains = self.capture.transcript_contains
        original_stdin = sys.stdin
        original_project = os.environ.get("CLAUDE_PROJECT_DIR")
        try:
            self.capture.git = lambda _project, *args: SimpleNamespace(
                returncode=0,
                stdout=(commit + "\n") if args == ("rev-parse", "HEAD") else "",
            )
            self.capture.home_locator = lambda _path: {"base": "HOME", "relative": "transcript.jsonl"}
            self.capture.transcript_contains = lambda _path, _target: True
            sys.stdin = io.StringIO(json.dumps(event))
            os.environ["CLAUDE_PROJECT_DIR"] = str(temporary)
            with redirect_stderr(io.StringIO()):
                result = self.capture.main()
        finally:
            self.capture.git = original_git
            self.capture.home_locator = original_home_locator
            self.capture.transcript_contains = original_contains
            sys.stdin = original_stdin
            if original_project is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = original_project
        return result, task

    def test_fail_does_not_dirty_terminal_files(self) -> None:
        result, task = self.run_capture("FAIL")
        self.assertEqual(result, 0)
        self.assertFalse((task / "state/evaluator-attestation.json").exists())
        self.assertEqual(
            (task / "state/evaluator-latest.md").read_text(encoding="utf-8"),
            "No final evaluation captured.\n",
        )

    def test_pass_writes_bound_terminal_files(self) -> None:
        result, task = self.run_capture("PASS")
        self.assertEqual(result, 0)
        attestation = json.loads((task / "state/evaluator-attestation.json").read_text())
        self.assertEqual(attestation["candidate_commit"], "a" * 40)
        self.assertEqual(attestation["verdict"], "PASS")
        self.assertEqual(set(attestation["must_results"]), set(self.must_ids))

    def test_active_stop_hook_never_reawakens_or_writes(self) -> None:
        result, task = self.run_capture("PASS", stop_hook_active=True)
        self.assertEqual(result, 0)
        self.assertFalse((task / "state/evaluator-attestation.json").exists())


class LaunchContractTests(unittest.TestCase):
    def test_launchers_use_strict_local_mcp_and_exact_checkout(self) -> None:
        for name in ("launch.sh", "launch_headless.sh", "resume.sh", "resume_headless.sh"):
            text = (TASK / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("--strict-mcp-config", text)
            self.assertIn("--mcp-config", text)
            self.assertNotIn("--worktree", text)
        for name in ("resume.sh", "resume_headless.sh"):
            text = (TASK / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("OPENPALI_SESSION_ID", text)
            self.assertIn("launcher.json", text)
            self.assertIn("merge-base --is-ancestor", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
