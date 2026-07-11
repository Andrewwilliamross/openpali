#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${OPENPALI_MAX_BUDGET_USD:-}" ]]; then
  echo "Set OPENPALI_MAX_BUDGET_USD to an explicit positive amount before a headless run." >&2
  exit 1
fi

python3 -c 'import math,sys; v=float(sys.argv[1]); raise SystemExit(0 if math.isfinite(v) and v > 0 else 1)' "$OPENPALI_MAX_BUDGET_USD" || {
  echo "OPENPALI_MAX_BUDGET_USD must be a positive number." >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TASK_DIR/.." && pwd)"

"$SCRIPT_DIR/preflight.sh"
cd "$REPO_ROOT"

goal="$(<"$TASK_DIR/GOAL_PROMPT.txt")"
system_prompt="$(<"$TASK_DIR/SYSTEM.md")"
session_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
run_dir="$TASK_DIR/state/runs/$session_id"

unset GH_TOKEN GITHUB_TOKEN NPM_TOKEN NODE_AUTH_TOKEN PYPI_TOKEN VERCEL_TOKEN NETLIFY_AUTH_TOKEN CLOUDFLARE_API_TOKEN
export OPENPALI_RUNS_ROOT="$TASK_DIR/state/runs"
python3 "$TASK_DIR/plugin/scripts/run_observer.py" --launch "$session_id" headless --budget "$OPENPALI_MAX_BUDGET_USD"

set +e
claude -p \
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
  --max-budget-usd "$OPENPALI_MAX_BUDGET_USD" \
  --name "OpenPali Fable 5 production MVP headless" \
  --plugin-dir "$TASK_DIR/plugin" \
  --settings "$TASK_DIR/settings.json" \
  --append-system-prompt "$system_prompt" \
  --worktree openpali-fable5-mvp \
  --output-format stream-json \
  --verbose \
  --include-hook-events \
  "$goal" | tee "$run_dir/stdout.stream.jsonl"
claude_status="${PIPESTATUS[0]}"
set -e

python3 -c 'import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"claude_exit_code": int(sys.argv[2])}, indent=2) + "\n")' \
  "$run_dir/launcher-exit.json" "$claude_status"
echo "HEADLESS_SESSION_ID: $session_id"
echo "RESUME_WITH: OPENPALI_SESSION_ID=$session_id ./openpali-one-shot/scripts/resume_headless.sh"
exit "$claude_status"
