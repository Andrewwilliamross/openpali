#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TASK_DIR/.." && pwd)"

cd "$REPO_ROOT"

if [[ -e "openpali-one-shot/state/evaluator-attestation.json" ]]; then
  echo "PREFLIGHT: FAIL — terminal evaluator evidence already exists; initialize a new experiment explicitly rather than reusing it." >&2
  exit 1
fi

actual_root="$(git rev-parse --show-toplevel)"
if [[ "$actual_root" != "$REPO_ROOT" ]]; then
  echo "PREFLIGHT: FAIL — run from the OpenPali checkout containing openpali-one-shot/." >&2
  exit 1
fi

branch="$(git branch --show-current)"
if [[ -z "$branch" ]]; then
  echo "PREFLIGHT: FAIL — detached HEAD; create or select the intended implementation branch." >&2
  exit 1
fi
if [[ "$branch" == "main" || "$branch" == "master" ]]; then
  echo "PREFLIGHT: FAIL — do not run the one-shot directly on the default branch." >&2
  echo "Create the intended implementation branch after reconciling local and remote work." >&2
  exit 1
fi

while IFS= read -r -d '' required_path; do
  if ! git ls-files --error-unmatch "$required_path" >/dev/null 2>&1 || \
     ! git cat-file -e "HEAD:$required_path" 2>/dev/null; then
    echo "PREFLIGHT: FAIL — $required_path is not committed at HEAD." >&2
    echo "Commit the complete task package and intended product snapshot before launch." >&2
    exit 1
  fi
done < <(
  find openpali-one-shot -type f \
    ! -path 'openpali-one-shot/state/runs/*' \
    ! -path '*/__pycache__/*' \
    ! -name '.DS_Store' \
    -print0
)

status="$(git status --porcelain=v1 --untracked-files=all)"
if [[ -n "$status" ]]; then
  echo "PREFLIGHT: FAIL — this exact local starting state is not clean and committed:" >&2
  echo "$status" >&2
  echo "Review and commit the intended files; do not reset, clean, or stash user work." >&2
  exit 1
fi

for command_name in claude git uv python3 node npm docker; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "PREFLIGHT: FAIL — required local command is missing: $command_name" >&2
    exit 1
  fi
done
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  echo "PREFLIGHT: FAIL — PyYAML is required by the safe Compose parser." >&2
  exit 1
fi

claude_version="$(claude --version | awk '{print $1}')"
python3 -c 'import sys; current=tuple(map(int,sys.argv[1].split("."))); raise SystemExit(0 if current >= (2,1,207) else 1)' "$claude_version" || {
  echo "PREFLIGHT: FAIL — Claude Code $claude_version is older than the tested 2.1.207 floor." >&2
  exit 1
}

if ! claude auth status >/dev/null 2>&1; then
  echo "PREFLIGHT: FAIL — Claude Code is not authenticated. Run 'claude auth login' or configure the intended provider." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "PREFLIGHT: FAIL — Docker Compose v2 is unavailable." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "PREFLIGHT: FAIL — the local Docker daemon is unavailable; start Docker Desktop and retry." >&2
  exit 1
fi
if ! python3 "$TASK_DIR/scripts/docker_safe.py" version >/dev/null 2>&1; then
  echo "PREFLIGHT: FAIL — Docker Compose is unavailable through the isolated safe wrapper." >&2
  exit 1
fi

python3 "$TASK_DIR/scripts/validate_harness.py"
python3 "$TASK_DIR/scripts/test_harness.py"
claude plugin validate --strict "$TASK_DIR/plugin"

available_kb="$(df -Pk "$REPO_ROOT" | awk 'NR == 2 {print $4}')"
if [[ "${available_kb:-0}" -lt 10485760 ]]; then
  echo "PREFLIGHT: WARN — less than 10 GiB is available for images, databases, models, and spatial artifacts." >&2
fi

echo "PREFLIGHT: PASS"
echo "CHECKOUT: $REPO_ROOT"
echo "BRANCH: $branch"
echo "START_COMMIT: $(git rev-parse HEAD)"
echo "CLAUDE_CODE: $claude_version"
echo "UV: $(uv --version)"
echo "PYTHON: $(python3 --version)"
echo "NODE: $(node --version)"
echo "NPM: $(npm --version)"
echo "DOCKER: $(docker --version)"
echo "COMPOSE: $(docker compose version)"
echo "AVAILABLE_KB: ${available_kb:-unknown}"
echo "NOTE: preflight verifies the shared local runtime, not account-level Fable entitlement, GPU suitability, or external data rights."
