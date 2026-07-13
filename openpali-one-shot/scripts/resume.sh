#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${OPENPALI_SESSION_ID:-}" ]]; then
  echo "Set OPENPALI_SESSION_ID to the UUID printed by launch.sh." >&2
  exit 1
fi
if [[ ! "$OPENPALI_SESSION_ID" =~ ^[0-9a-fA-F-]{36}$ ]]; then
  echo "OPENPALI_SESSION_ID must be a UUID." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TASK_DIR/.." && pwd)"
run_dir="$TASK_DIR/state/runs/$OPENPALI_SESSION_ID"

cd "$REPO_ROOT"
if [[ ! -f "$run_dir/launcher.json" ]]; then
  echo "RESUME: FAIL — no local launcher record for session $OPENPALI_SESSION_ID." >&2
  exit 1
fi
python3 -c 'import json,sys; from pathlib import Path; data=json.loads(Path(sys.argv[1]).read_text()); ok=(data.get("session_id")==sys.argv[2] and data.get("mode")=="interactive" and Path(data.get("checkout","")).resolve()==Path(sys.argv[3]).resolve() and data.get("branch")==sys.argv[4]); print("RESUME: FAIL — launcher checkout, branch, mode, or session does not match." if not ok else "", file=sys.stderr); raise SystemExit(0 if ok else 1)' \
  "$run_dir/launcher.json" "$OPENPALI_SESSION_ID" "$REPO_ROOT" "$(git branch --show-current)"
start_commit="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["start_commit"])' "$run_dir/launcher.json")"
if ! git merge-base --is-ancestor "$start_commit" HEAD; then
  echo "RESUME: FAIL — recorded start commit is not in the current branch lineage." >&2
  exit 1
fi
if ! claude auth status >/dev/null 2>&1; then
  echo "RESUME: FAIL — Claude Code is not authenticated." >&2
  exit 1
fi
python3 "$TASK_DIR/scripts/validate_harness.py"
claude plugin validate --strict "$TASK_DIR/plugin"

system_prompt="$(<"$TASK_DIR/SYSTEM.md")"
unset GH_TOKEN GITHUB_TOKEN NPM_TOKEN NODE_AUTH_TOKEN PYPI_TOKEN VERCEL_TOKEN NETLIFY_AUTH_TOKEN CLOUDFLARE_API_TOKEN

exec claude \
  --resume "$OPENPALI_SESSION_ID" \
  --model fable \
  --effort xhigh \
  --permission-mode auto \
  --strict-mcp-config \
  --mcp-config "$TASK_DIR/mcp.json" \
  --plugin-dir "$TASK_DIR/plugin" \
  --settings "$TASK_DIR/settings.json" \
  --append-system-prompt "$system_prompt"
