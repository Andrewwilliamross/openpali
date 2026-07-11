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

unset GH_TOKEN GITHUB_TOKEN NPM_TOKEN NODE_AUTH_TOKEN PYPI_TOKEN VERCEL_TOKEN NETLIFY_AUTH_TOKEN CLOUDFLARE_API_TOKEN
export OPENPALI_RUNS_ROOT="$TASK_DIR/state/runs"
python3 "$TASK_DIR/plugin/scripts/run_observer.py" --launch "$session_id" interactive

exec claude \
  --session-id "$session_id" \
  --model fable \
  --effort xhigh \
  --permission-mode auto \
  --brief \
  --no-chrome \
  --strict-mcp-config \
  --mcp-config "$TASK_DIR/mcp.json" \
  --setting-sources project \
  --tools "Bash,Edit,Read,Write,Grep,Glob,Agent,WebFetch,WebSearch" \
  --name "OpenPali Fable 5 production MVP" \
  --plugin-dir "$TASK_DIR/plugin" \
  --settings "$TASK_DIR/settings.json" \
  --append-system-prompt "$system_prompt" \
  --worktree openpali-fable5-mvp \
  "$goal"
