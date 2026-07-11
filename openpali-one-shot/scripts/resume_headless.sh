#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${OPENPALI_SESSION_ID:-}" ]]; then
  echo "Set OPENPALI_SESSION_ID to the UUID printed by launch_headless.sh." >&2
  exit 1
fi
if [[ -z "${OPENPALI_MAX_BUDGET_USD:-}" ]]; then
  echo "Set OPENPALI_MAX_BUDGET_USD to an explicit positive additional cap." >&2
  exit 1
fi
python3 -c 'import math,sys; v=float(sys.argv[1]); raise SystemExit(0 if math.isfinite(v) and v > 0 else 1)' "$OPENPALI_MAX_BUDGET_USD" || {
  echo "OPENPALI_MAX_BUDGET_USD must be a positive number." >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TASK_DIR/.." && pwd)"
if [[ "${OPENPALI_RESUME_BOOTSTRAPPED:-0}" != "1" ]]; then
  trace_root="$TASK_DIR/state/runs"
  manifest="$trace_root/$OPENPALI_SESSION_ID/manifest.json"
  if [[ ! -f "$manifest" ]]; then
    echo "RESUME: FAIL — no siloed manifest for session $OPENPALI_SESSION_ID." >&2
    exit 1
  fi
  worktree_path="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("worktree_path", ""))' "$manifest")"
  if [[ -z "$worktree_path" || ! -d "$worktree_path/openpali-one-shot" ]]; then
    echo "RESUME: FAIL — the recorded worktree is missing; inspect $manifest and git worktree list." >&2
    exit 1
  fi
  export OPENPALI_RESUME_BOOTSTRAPPED=1
  export OPENPALI_RUNS_ROOT="$trace_root"
  exec "$worktree_path/openpali-one-shot/scripts/resume_headless.sh"
fi

run_dir="$OPENPALI_RUNS_ROOT/$OPENPALI_SESSION_ID"
manifest="$run_dir/manifest.json"

if [[ ! -f "$manifest" ]]; then
  echo "RESUME: FAIL — no siloed manifest for session $OPENPALI_SESSION_ID." >&2
  exit 1
fi
worktree_path="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("worktree_path", ""))' "$manifest")"
if [[ -z "$worktree_path" || ! -d "$worktree_path" || "$worktree_path" != "$REPO_ROOT" ]]; then
  echo "RESUME: FAIL — the recorded worktree is missing; inspect $manifest and git worktree list." >&2
  exit 1
fi
if ! claude auth status >/dev/null 2>&1; then
  echo "RESUME: FAIL — Claude Code is not authenticated." >&2
  exit 1
fi

python3 "$TASK_DIR/scripts/validate_harness.py"
python3 "$TASK_DIR/scripts/test_controls.py"
python3 "$TASK_DIR/scripts/test_observer.py"
claude plugin validate --strict "$TASK_DIR/plugin"

cd "$worktree_path"
system_prompt="$(<"$TASK_DIR/SYSTEM.md")"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
unset GH_TOKEN GITHUB_TOKEN NPM_TOKEN NODE_AUTH_TOKEN PYPI_TOKEN VERCEL_TOKEN NETLIFY_AUTH_TOKEN CLOUDFLARE_API_TOKEN

set +e
claude -p \
  --resume "$OPENPALI_SESSION_ID" \
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
  --plugin-dir "$TASK_DIR/plugin" \
  --settings "$TASK_DIR/settings.json" \
  --append-system-prompt "$system_prompt" \
  --output-format stream-json \
  --verbose \
  --include-hook-events \
  "Resume the active /goal from the current on-disk state and continue until a valid terminal state." \
  | tee "$run_dir/resume-$stamp.stream.jsonl"
claude_status="${PIPESTATUS[0]}"
set -e

echo "HEADLESS_SESSION_ID: $OPENPALI_SESSION_ID"
exit "$claude_status"
