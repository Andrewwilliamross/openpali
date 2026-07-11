#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${OPENPALI_MAX_BUDGET_USD:-}" ]]; then
  echo "Set OPENPALI_MAX_BUDGET_USD to an explicit positive amount before a headless run." >&2
  exit 1
fi
python3 -c 'import math,sys; value=float(sys.argv[1]); raise SystemExit(0 if math.isfinite(value) and value > 0 else 1)' "$OPENPALI_MAX_BUDGET_USD" || {
  echo "OPENPALI_MAX_BUDGET_USD must be a finite positive number." >&2
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
mkdir -p "$run_dir"

python3 -c 'import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"session_id":sys.argv[2],"mode":"headless","checkout":sys.argv[3],"start_commit":sys.argv[4],"branch":sys.argv[5],"initial_budget_usd":float(sys.argv[6])},indent=2)+"\n")' \
  "$run_dir/launcher.json" "$session_id" "$REPO_ROOT" "$(git rev-parse HEAD)" "$(git branch --show-current)" "$OPENPALI_MAX_BUDGET_USD"

unset GH_TOKEN GITHUB_TOKEN NPM_TOKEN NODE_AUTH_TOKEN PYPI_TOKEN VERCEL_TOKEN NETLIFY_AUTH_TOKEN CLOUDFLARE_API_TOKEN

set +e
claude -p \
  --session-id "$session_id" \
  --model fable \
  --effort xhigh \
  --permission-mode auto \
  --strict-mcp-config \
  --mcp-config "$TASK_DIR/mcp.json" \
  --max-budget-usd "$OPENPALI_MAX_BUDGET_USD" \
  --name "OpenPali Fable 5 production MVP headless" \
  --plugin-dir "$TASK_DIR/plugin" \
  --settings "$TASK_DIR/settings.json" \
  --append-system-prompt "$system_prompt" \
  --output-format stream-json \
  --verbose \
  --include-hook-events \
  "$goal" | tee "$run_dir/stdout.stream.jsonl"
claude_status="${PIPESTATUS[0]}"
set -e

python3 -c 'import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"claude_exit_code":int(sys.argv[2])},indent=2)+"\n")' \
  "$run_dir/launcher-exit.json" "$claude_status"
echo "HEADLESS_SESSION_ID: $session_id"
echo "RESUME_WITH: OPENPALI_SESSION_ID=$session_id OPENPALI_MAX_BUDGET_USD=<additional-cap> ./openpali-one-shot/scripts/resume_headless.sh"
exit "$claude_status"
