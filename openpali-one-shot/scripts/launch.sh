#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TASK_DIR/.." && pwd)"

"$SCRIPT_DIR/preflight.sh"
cd "$REPO_ROOT"

goal="$(<"$TASK_DIR/GOAL_PROMPT.txt")"
system_prompt="$(<"$TASK_DIR/SYSTEM.md")"
session_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
run_dir="$TASK_DIR/state/runs/$session_id"
mkdir -p "$run_dir"

python3 -c 'import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"session_id":sys.argv[2],"mode":"interactive","checkout":sys.argv[3],"start_commit":sys.argv[4],"branch":sys.argv[5]},indent=2)+"\n")' \
  "$run_dir/launcher.json" "$session_id" "$REPO_ROOT" "$(git rev-parse HEAD)" "$(git branch --show-current)"

echo "INTERACTIVE_SESSION_ID: $session_id"
echo "RESUME_WITH: OPENPALI_SESSION_ID=$session_id ./openpali-one-shot/scripts/resume.sh"

unset GH_TOKEN GITHUB_TOKEN NPM_TOKEN NODE_AUTH_TOKEN PYPI_TOKEN VERCEL_TOKEN NETLIFY_AUTH_TOKEN CLOUDFLARE_API_TOKEN

exec claude \
  --session-id "$session_id" \
  --model fable \
  --effort xhigh \
  --permission-mode auto \
  --strict-mcp-config \
  --mcp-config "$TASK_DIR/mcp.json" \
  --name "OpenPali Fable 5 production MVP" \
  --plugin-dir "$TASK_DIR/plugin" \
  --settings "$TASK_DIR/settings.json" \
  --append-system-prompt "$system_prompt" \
  "$goal"
