# OpenPali Fable 5 production-MVP one-shot

This folder is the complete, siloed control plane for a long-running Claude
Code experiment. It does **not** implement the MVP itself. It gives Fable 5 a
repository-specific mission, immutable acceptance contract, bounded tools,
persistent run state, specialist subagents, and an independent verification
loop.

The mission is intentionally narrower than “improve everything.” It first
repairs public-data truth and publication safety, then delivers one evidence-
backed recovery-intelligence journey. Continual ML and 3D expansion are gated
on trustworthy observations, licensing, and measured value.

## Before launch

1. Review `MISSION.md`, `BASELINE.md`, and `contract/acceptance.json`.
2. Fetch the current remote refs (`git fetch --prune origin`) and make an
   explicit starting-base decision. At harness creation, local `main` was 18
   commits behind `origin/main`; the remote commits include overlapping
   provenance and spatial work. Preserve the current local/uncommitted work on
   a safe branch and reconcile deliberately. Do not reset, clean, or discard it.
3. Decide which current uncommitted changes belong in the experiment snapshot,
   then commit that complete snapshot—including this folder—on the safe branch.
   Launch refuses a dirty tree and requires the remote default ref to be an
   ancestor of local `HEAD`.
4. Task settings pin Claude Code's isolated worktree to that local `HEAD`, not
   its normal remote-default base. Preflight verifies every control-plane file
   in this folder exists in the commit, so ignored or untracked controls cannot
   silently disappear.
5. Authenticate Claude Code (`claude auth login`) or configure the intended
   supported API provider. Local inspection found no active Claude Code login;
   Fable entitlement still depends on the account/provider.
6. If this repository has not previously been trusted by Claude Code, start
   `claude` once from the repository root, accept the workspace trust prompt,
   and exit. This interactive trust decision cannot be pre-approved by the
   harness.
7. Run:

   ```bash
   python3 openpali-one-shot/scripts/validate_harness.py
   ./openpali-one-shot/scripts/preflight.sh
   ```

## Launch

From the repository root, run one command:

```bash
./openpali-one-shot/scripts/launch.sh
```

The script launches Claude Code 2.1.207 or newer—the tested harness floor—with:

- Claude Fable 5 at `xhigh` effort;
- an isolated Git worktree named `openpali-fable5-mvp`;
- Claude Code sandboxing and auto permission review;
- this folder's local plugin, agents, hooks, and guardrails;
- an explicit empty MCP configuration, a fixed built-in tool surface, no
  signed-in Chrome session, and no user/project CLAUDE.md or auto-memory;
- a single `/goal` prompt from `GOAL_PROMPT.txt`.

`/goal` keeps starting turns until the condition is satisfied. If the session
is interrupted, resume it with Claude Code's `--continue` or `--resume`; active
goals are restored. The authoritative state is on disk under `state/`, not in
one conversation. The task raises Claude Code's default consecutive Stop-hook
override cap so an incomplete narrative cannot end the run after eight blocks;
use Ctrl+C for deliberate human interruption and a headless budget cap for
unattended spend control.

For a non-interactive run with a hard API-spend ceiling, use:

```bash
OPENPALI_MAX_BUDGET_USD=<positive-cap> ./openpali-one-shot/scripts/launch_headless.sh
```

This harness deliberately does not choose a budget for the sponsor.

## Preserve and resume the experiment

When the interactive Claude session exits, choose **Keep the worktree**. The
Claude Code Remove option deletes the worktree branch and its new commits. Then
inspect the exact branch and commit before any integration:

```bash
git worktree list
git -C .claude/worktrees/openpali-fable5-mvp status --short --branch
git -C .claude/worktrees/openpali-fable5-mvp log --oneline --decorate -10
```

Resume an interrupted interactive run with:

```bash
./openpali-one-shot/scripts/resume.sh
```

Headless worktrees are retained automatically. The launcher prints and records
the required UUID. Resume with a new explicit incremental spend cap:

```bash
OPENPALI_SESSION_ID=<uuid> OPENPALI_MAX_BUDGET_USD=<positive-cap> \
  ./openpali-one-shot/scripts/resume_headless.sh
```

Do not remove either worktree until Andrew has reviewed and preserved its
branch. Neither launch path pushes, merges, or deploys.

## Experiment record

Each launch gets a UUID and an ignored trace directory at
`state/runs/<session-id>/`. Hooks record lifecycle events, starting and final
commit/branch, requested and observed models, observed token/cost fields, wall
time, status, and a hash plus archival copy of the Claude transcript. Headless
mode also records the complete stream-JSON output and process exit. These trace
files are experiment observability—not product acceptance evidence—and should
be handled according to the no-private-data rule.

## What is enforced

- `MISSION.md`, `SYSTEM.md`, `BASELINE.md`, the acceptance contract, plugin,
  settings, launch controls, and evaluator artifacts are protected from both
  built-in edit tools and sandboxed subprocess writes during the run.
- Git push, remote-ref mutation, GitHub CLI, common ad-hoc network clients,
  production deploy commands, destructive Git, and paid acquisition are
  blocked. The network allowlist is defense in depth, not TLS method
  inspection; the operating contract remains authoritative.
- Ambient MCP servers and personal Chrome state are excluded so the run cannot
  silently acquire unrelated external authority.
- Claude/cloud credentials are stripped from Bash, hooks, and stdio child
  processes while the parent Claude process retains authentication.
- A `SessionStart` hook re-injects the operating invariants and compact status
  after startup, resume, or compaction.
- Input-heavy research and audit work has named read-only agents. One principal
  owns architecture and integration.
- The final evaluator has no Write/Edit tools. Its exact verdict is captured by
  a hook, bound to its transcript, contract hash, and evaluated commit.
- The `/goal` evaluator is only a persistence mechanism. It cannot call tools;
  it is never treated as the independent product verifier.
- A deterministic Stop hook rejects narrative completion unless the terminal
  evidence schema, required criterion IDs, evaluator attestation, commit chain,
  and clean-tree rules validate.

## Terminal states

- `PASS`: every mandatory acceptance item has machine evidence and the fresh
  independent evaluator returns `VERDICT: PASS`.
- `BLOCKED_EXTERNAL`: all safe in-scope work is complete and only a documented
  human decision, private credential, license/right, or material spend remains.
- `BUDGET_EXHAUSTED` or `STALLED`: the best valid commit, failing gates, exact
  resume command, and next action are recorded. Neither is MVP completion or a
  Stop-gate success; a budget limit, API failure, or deliberate human interrupt
  ends the invocation while preserving those recovery records.

## Cost and data warning

Fable 5 is a premium model and `/goal` can run for many turns. Monitor spend.
Anthropic's current documentation also says Fable is not available for
zero-data-retention use and uses 30-day retention. Keep resident submissions,
credentials, insurance documents, private imagery, and other non-public data
out of this experiment.

## Folder map

```text
openpali-one-shot/
├── GOAL_PROMPT.txt              single prompt sent to Claude Code
├── SYSTEM.md                    compact non-negotiable operating contract
├── MISSION.md                   product outcome, scope, and execution policy
├── BASELINE.md                  verified repository findings as of 2026-07-11
├── contract/                    immutable acceptance and evidence schema
├── research/                    curated primary-source brief
├── state/                       mutable plan, status, evidence, and handoffs
├── plugin/                      local Claude Code agents and hooks
├── scripts/                     launch, resume, preflight, and validation
└── state/runs/                  ignored session manifests and trace archives
```
