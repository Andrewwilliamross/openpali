#!/usr/bin/env python3
"""Behavior test for the siloed launch/session observer."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OBSERVER = ROOT / "plugin" / "scripts" / "run_observer.py"


class ObserverTests(unittest.TestCase):
    def test_lifecycle_resolves_root_and_archives_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "worktree"
            nested = project / "web"
            runs = base / "runs"
            transcript = base / "session.jsonl"
            nested.mkdir(parents=True)
            (project / "fixture.txt").write_text("fixture\n", encoding="utf-8")
            transcript.write_text(
                json.dumps({
                    "message": {
                        "model": "claude-fable-5",
                        "usage": {"input_tokens": 3, "output_tokens": 5},
                    },
                    "total_cost_usd": 0.25,
                }) + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            subprocess.run(["git", "-C", str(project), "config", "user.name", "Observer Test"], check=True)
            subprocess.run(["git", "-C", str(project), "config", "user.email", "observer@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(project), "add", "."], check=True)
            subprocess.run(["git", "-C", str(project), "commit", "-qm", "fixture"], check=True)

            env = os.environ.copy()
            env["OPENPALI_RUNS_ROOT"] = str(runs)
            session_id = "00000000-0000-4000-8000-000000000001"
            subprocess.run(
                ["python3", str(OBSERVER), "--launch", session_id, "headless", "--budget", "1.00"],
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            for event_name in ("SessionStart", "SessionEnd"):
                result = subprocess.run(
                    ["python3", str(OBSERVER)],
                    input=json.dumps({
                        "session_id": session_id,
                        "hook_event_name": event_name,
                        "source": "startup",
                        "cwd": str(nested),
                        "transcript_path": str(transcript),
                        "reason": "test_complete",
                    }),
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            run_dir = runs / session_id
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            archived = run_dir / "transcript.jsonl"
            self.assertEqual(Path(manifest["worktree_path"]), project.resolve())
            self.assertEqual(manifest["final_worktree_clean"], True)
            self.assertEqual(manifest["observability"]["actual_models_observed"], ["claude-fable-5"])
            self.assertEqual(
                manifest["observability"]["token_usage_observed_unDeduplicated"]["output_tokens"],
                5,
            )
            self.assertEqual(manifest["observability"]["cost_values_observed_usd"], [0.25])
            self.assertEqual(manifest["transcript_sha256"], hashlib.sha256(archived.read_bytes()).hexdigest())
            self.assertGreaterEqual(manifest["wall_time_seconds"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
