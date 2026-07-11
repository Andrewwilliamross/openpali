# OpenPali Fable 5 production-MVP one-shot

This folder launches one Fable 5 principal-engineering run against the exact
local OpenPali checkout. The goal is not another planning or harness sprint. It
is an integrated production-MVP release candidate with a real backend/data
platform, continual ML experimentation and serving, substantive spatial/3D
engineering, complete product journeys, and executable operations.

The known civic-data defects are mandatory phase-0 repairs because they poison
metrics and learning labels. They are the foundation of the build, not a reason
to omit the rest of it.

## What Fable is required to build

- PostgreSQL/PostGIS-backed canonical recovery data and a FastAPI-style typed
  backend, migrations, immutable object artifacts, snapshot APIs, and health;
- idempotent source acquisition, Prefect-style orchestration, bitemporal event
  history, metrics, atomic publication, last-known-good, and rollback;
- point-in-time ML datasets, baseline plus challenger experiments, MLflow-style
  tracking/registry, temporal evaluation, batch inference, and continual
  reevaluation without unsafe automatic promotion;
- a rights-safe spatial asset and reconstruction path, multimodal observation
  contract, coherent 2D/3D map, and measured renderer/GPU/z-fighting/
  registration improvements;
- property and community intelligence journeys backed by the live local API;
  and
- a bounded validated-Compose-plus-bootstrap local operator path, CI-equivalent
  gates, browser/model/spatial tests, observability, security, accessibility,
  release, backup, and recovery work.

The detailed reference architecture is
[`research/production-mvp-architecture.md`](research/production-mvp-architecture.md).
The machine-readable outcome contract is
[`contract/acceptance.json`](contract/acceptance.json).

## Why the harness is deliberately small

Claude Code's native `/goal` loop already continues across turns and uses a
fresh transcript evaluator. Fable 5 is also designed for long-horizon work and
strong subagent delegation. This package therefore keeps only:

- one immutable product mission and acceptance contract;
- a compact startup context and safety guardrail;
- read-only specialist research/evaluation agents;
- launch, resume, preflight, and static validation scripts; and
- small mutable plan/status/evidence directories plus one deterministic terminal
  verifier.

It does not run a custom stop loop or make Fable build another harness. Claude
Code's native goal/evaluator loop decides when product work is complete; one
hook preserves the fresh evaluator response and a small verifier proves that
the terminal child contains evidence only. Working product behavior and
independent runtime evidence remain the basis of completion.

## Exact local environment

Fable runs from this repository directory. No separate Git worktree is created.
That means it sees the same committed files and local toolchain prepared by
Andrew. The preflight intentionally requires the intended starting state to be
clean and committed so existing work is included and attributable; it never
resets, stashes, cleans, fetches, or rewrites that state.

The preparation audit found:

- Claude Code 2.1.207;
- `uv` 0.8.24 and the locked Python 3.12 project;
- Node 24.9.0 and npm 11.6.0;
- Docker 28.5.1 and Docker Compose 2.40.3; and
- the current local data, cache, spatial artifacts, browser project, and
  uncommitted production-readiness work described in `BASELINE.md`.

Fable must probe and record the actual launch-time state rather than trusting
these preparation-time versions. A Docker socket is effectively host authority,
so raw Docker is unavailable to Fable. The only unsandboxed path is the supplied
`scripts/docker_safe.py` wrapper, which accepts repository-scoped Compose
operations after structural and rendered validation. It uses an isolated
Docker HOME/config and fixed local socket; blocks external resources, local
secret files, unsafe mounts/contexts/privileges, unpinned external images, and
arbitrary `run`/`exec`; and permits runtime egress only through one pinned,
bind-free proxy while product services remain on internal networks.

## Before the one-shot

The launch must represent the intended product snapshot, not an accidental
combination of stale local and remote history.

1. Review and reconcile the local branch, current user-owned changes, and the
   useful `origin/main` work identified in `BASELINE.md` and the architecture
   blueprint.
2. Commit the exact starting snapshot on the branch Fable should develop.
3. Run `claude` once from the repository and accept workspace trust.
4. Authenticate Claude Code and confirm the account can use Fable 5.
5. Decide the maximum spend/time for the run. The headless launcher requires an
   explicit dollar cap.

Use the headless launcher when a hard CLI-enforced budget is required;
interactive mode requires the operator to monitor and interrupt the session.

The sponsor may decide the source-code license and proprietary imagery rights
later. The mission requires technical gates and rights-safe defaults now.

## Validate and launch

From `/Users/andrewross/paliml`:

```bash
./openpali-one-shot/scripts/preflight.sh
./openpali-one-shot/scripts/launch.sh
```

`launch.sh` starts Fable 5 at `xhigh` effort in the current checkout with the
single prompt in `GOAL_PROMPT.txt`, the task-local specialist agents, the
task-local sandbox/permission policy, and the user's normal local project
instructions and browser/toolchain environment. Ambient MCP connectors are
excluded so signed-in external write tools cannot bypass the Git/deployment
boundary; public research remains available through WebSearch/WebFetch.

For a non-interactive run with an explicit incremental spend cap:

```bash
OPENPALI_MAX_BUDGET_USD=250 \
  ./openpali-one-shot/scripts/launch_headless.sh
```

The headless launcher prints a UUID and stores the JSONL stream under
`openpali-one-shot/state/runs/<session-id>/`. Resume it with:

```bash
OPENPALI_SESSION_ID=<uuid> OPENPALI_MAX_BUDGET_USD=100 \
  ./openpali-one-shot/scripts/resume_headless.sh
```

The interactive launcher prints its UUID before Claude starts. Resume that
session from the same checkout and branch with:

```bash
OPENPALI_SESSION_ID=<uuid> ./openpali-one-shot/scripts/resume.sh
```

## Specialist agents

Fable remains the only architect/integrator and uses read-only subagents for
input-heavy work:

- repository and backend/data-platform archaeology;
- official public-data and rights research;
- continual-ML/statistical methods and leakage review;
- multimodal/spatial/reconstruction/renderer analysis; and
- fresh adversarial evaluation of the integrated candidate.

They may retrieve papers, documentation, schemas, public data candidates, and
large test/log context. Their reports are not implementation evidence.
The input-heavy research agents use Sonnet so Fable's frontier context remains
focused on architecture, implementation, integration, and final evaluation.

## Completion evidence

A release candidate passes only when:

- meaningful product implementation exists outside this task folder in every
  required component;
- a Prefect-worker fixture release and a separate current representative-data
  release exercise source acquisition, temporal ledger, metrics, model
  evaluation/status, spatial publication, release-qualified API, and browser;
- the representative release includes the named civic sources, DINS, and a real
  USGS Palisades AOI, and exact-hash zero-network replay matches;
- fast/full/CI-equivalent, browser, model, spatial, security, and recovery
  checks pass;
- the working tree is clean at the candidate commit;
- the fresh independent evaluator reports `VERDICT: PASS` after rerunning the
  exact clean candidate;
- exactly one evidence-only child changes the two hook-owned files in
  `state/README.md` while the founder report remains in the evaluated candidate;
  and
- `python3 openpali-one-shot/scripts/verify_completion.py` passes there.

Data insufficiency may cause a typed no-forecast product result, but the ML
system must still execute. Proprietary-rights uncertainty may remove an asset,
but a rights-safe 3D path must still work. Documentation-only, harness-only,
workflow-YAML-only, no-model, or disabled-3D-only outcomes fail.

## Folder map

```text
openpali-one-shot/
├── GOAL_PROMPT.txt
├── SYSTEM.md
├── MISSION.md
├── BASELINE.md
├── contract/acceptance.json
├── research/
│   ├── BRIEF.md
│   └── production-mvp-architecture.md
├── plugin/
│   ├── agents/
│   ├── hooks/hooks.json
│   └── scripts/
├── scripts/
│   ├── preflight.sh
│   ├── validate_harness.py
│   ├── verify_completion.py
│   ├── docker_safe.py
│   ├── launch.sh
│   ├── launch_headless.sh
│   ├── resume.sh
│   └── resume_headless.sh
├── settings.json
└── state/
```
