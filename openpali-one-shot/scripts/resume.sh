#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TASK_DIR/.." && pwd)"
SESSION_NAME="OpenPali Fable 5 production MVP"

cd "$REPO_ROOT"
if [[ "${OPENPALI_RESUME_BOOTSTRAPPED:-0}" != "1" ]]; then
  worktree_path="$(
    git worktree list --porcelain | awk '
      $1 == "worktree" { path = substr($0, 10) }
      index($0, "openpali-fable5-mvp") { print path; exit }
    '
  )"
  if [[ -z "$worktree_path" || ! -d "$worktree_path/openpali-one-shot" ]]; then
    echo "RESUME: FAIL — the openpali-fable5-mvp worktree is missing. Inspect git worktree list before recovery." >&2
    exit 1
  fi
  export OPENPALI_RESUME_BOOTSTRAPPED=1
  export OPENPALI_RUNS_ROOT="$TASK_DIR/state/runs"
  exec "$worktree_path/openpali-one-shot/scripts/resume.sh"
fi

worktree_path="$REPO_ROOT"
if ! claude auth status >/dev/null 2>&1; then
  echo "RESUME: FAIL — Claude Code is not authenticated." >&2
  exit 1
fi
python3 "$TASK_DIR/scripts/validate_harness.py"
python3 "$TASK_DIR/scripts/test_controls.py"
python3 "$TASK_DIR/scripts/test_observer.py"
claude plugin validate --strict "$TASK_DIR/plugin"

system_prompt="$(<"$TASK_DIR/SYSTEM.md")"
unset GH_TOKEN GITHUB_TOKEN NPM_TOKEN NODE_AUTH_TOKEN PYPI_TOKEN VERCEL_TOKEN NETLIFY_AUTH_TOKEN CLOUDFLARE_API_TOKEN

exec claude \
  --resume "$SESSION_NAME" \
  --model fable \
  --effort xhigh \
  --permission-mode auto \
  --brief \
  --no-chrome \
  --strict-mcp-config \
  --mcp-config "$TASK_DIR/mcp.json" \
  --setting-sources project \
  --tools "Bash,Edit,Read,Write,Grep,Glob,Agent,WebFetch,WebSearch" \
  --plugin-dir "$TASK_DIR/plugin" \
  --settings "$TASK_DIR/settings.json" \
  --append-system-prompt "$system_prompt"
