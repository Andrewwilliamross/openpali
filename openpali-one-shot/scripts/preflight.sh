#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TASK_DIR/.." && pwd)"

cd "$REPO_ROOT"

actual_root="$(git rev-parse --show-toplevel)"
if [[ "$actual_root" != "$REPO_ROOT" ]]; then
  echo "PREFLIGHT: FAIL — launch from the OpenPali repository containing this harness." >&2
  exit 1
fi

remote_default_ref="$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null || true)"
if [[ -z "$remote_default_ref" ]]; then
  echo "PREFLIGHT: FAIL — origin/HEAD is unavailable. Fetch origin and make an explicit starting-base decision." >&2
  exit 1
fi
if ! git merge-base --is-ancestor "$remote_default_ref" HEAD; then
  behind_count="$(git rev-list --count "HEAD..$remote_default_ref")"
  echo "PREFLIGHT: FAIL — local HEAD does not contain $remote_default_ref ($behind_count remote commit(s) missing)." >&2
  echo "Fetch origin, preserve the current work on a safe branch, and reconcile deliberately; do not reset or discard it." >&2
  exit 1
fi

while IFS= read -r -d '' required_path; do
  if ! git cat-file -e "HEAD:$required_path" 2>/dev/null; then
    echo "PREFLIGHT: FAIL — $required_path is absent from local HEAD. Commit the complete harness before launch." >&2
    exit 1
  fi
done < <(
  find openpali-one-shot -type f \
    ! -path 'openpali-one-shot/state/runs/*' \
    ! -path '*/__pycache__/*' \
    ! -name '.DS_Store' \
    -print0
)

status="$(git status --porcelain)"
if [[ -n "$status" ]]; then
  echo "PREFLIGHT: FAIL — the worktree is dirty. Preserve and commit the intended starting state first:" >&2
  echo "$status" >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "PREFLIGHT: FAIL — Claude Code is not installed." >&2
  exit 1
fi

claude_version="$(claude --version | awk '{print $1}')"
python3 -c 'import sys; v=tuple(map(int,sys.argv[1].split("."))); minimum=(2,1,207); raise SystemExit(0 if v>=minimum else 1)' "$claude_version" || {
  echo "PREFLIGHT: FAIL — Claude Code $claude_version is older than this harness's tested minimum 2.1.207." >&2
  exit 1
}

if ! claude auth status >/dev/null 2>&1; then
  echo "PREFLIGHT: FAIL — Claude Code is not authenticated. Run 'claude auth login' or configure the intended API provider." >&2
  exit 1
fi

python3 "$TASK_DIR/scripts/validate_harness.py"
python3 "$TASK_DIR/scripts/test_controls.py"
python3 "$TASK_DIR/scripts/test_observer.py"
claude plugin validate --strict "$TASK_DIR/plugin"

if git worktree list --porcelain | grep -Fq "openpali-fable5-mvp"; then
  echo "PREFLIGHT: FAIL — an openpali-fable5-mvp worktree already exists; resume that session or remove it intentionally." >&2
  exit 1
fi

echo "PREFLIGHT: PASS"
echo "CLAUDE_CODE: $claude_version"
echo "START_COMMIT: $(git rev-parse HEAD)"
echo "REMOTE_BASE: $remote_default_ref @ $(git rev-parse "$remote_default_ref")"
echo "WORKTREE_BASE: local HEAD (enforced by settings.json)"
echo "NOTE: account-level Fable entitlement and spend were not tested by preflight."
