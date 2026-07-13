# Launch environment manifest — 2026-07-11

Captured by Fable 5 at the start of the one-shot run, in the exact prepared
local checkout `/Users/andrewross/paliml`.

## Repository state

- Branch: `codex/openpali-one-shot-harness`
- Starting commit: `aa51c93` ("Reconcile starting snapshot: merge origin/main
  into the one-shot branch") — clean working tree at launch.
- The reconciled base includes origin/main work: provenance/expectation gates
  (752675b), all-parcel 3D placeholders (d207201), lazy 3D code-split
  (6de5c16), GL state isolation (f8ab734), post-fire DEM datum foundation
  (0bb5e32).
- Unmerged local branches present (not checked out): `openpali/data-platform-phase1`,
  `spatial/postfire-dem-terrain`, plus claude/* PR branches.

## Host and tools (probed, not assumed)

| Item | Observed |
|---|---|
| OS | macOS 26.5.1 (build 25F80), arm64 |
| CPU/GPU | Apple M4 Pro, 20-core GPU, Metal supported |
| Disk free | 494 GiB on / |
| Python (host) | 3.14.2 |
| Python (pipeline venv) | 3.12.11 at `pipeline/.venv` (no pip module; uv-managed) |
| uv | 0.8.24 — **panics under the Bash sandbox** ("Attempted to create a NULL object"); dependency work must use the venv interpreter directly (ensurepip) or unsandboxed-safe paths |
| Node / npm | v24.9.0 / 11.6.0 |
| Docker Compose | v2.40.3-desktop.1 — reachable ONLY via `python3 openpali-one-shot/scripts/docker_safe.py <args>` as the entire command |
| Git | 2.51.0 |
| Browsers | Google Chrome.app, Safari.app installed; Playwright not yet installed in web/ |
| GPU compute | No NVIDIA/CUDA; Apple Metal only. GPU reconstruction profile must be optional with typed `unsupported_hardware`. |

## Guardrail constraints observed at launch

- `docker_safe.py` must be invoked with the repo-relative path as the whole
  simple command.
- Blocked in Bash: `curl`/`wget`, `git push/pull/fetch`, `git reset --hard`,
  `git stash`, `rm -rf`, `gh`, cloud CLIs, keychain reads, `env`/`printenv`.
- Shell commands that reference protected `openpali-one-shot/` paths must not
  contain mutating patterns (including `>` redirects).
- Sandbox write allowlist: repository, `$TMPDIR`, scratchpad. `~/.cache` is not
  writable (root cause of the uv panic).

## Baseline behavior reproduced (2026-07-11)

| Command | Result |
|---|---|
| `pipeline/.venv/bin/python -m pytest -q` | **69 passed** in 12.96s (baseline doc said 35 on `c59bc64`; the merged origin/main work added tests) |
| `cd web && npm test -- --run` | **24 passed** (2 files; baseline doc said 17) |
| `cd web && npm run build` | passed, 3.21s, chunk-size warning >500 kB persists |
| `cd web && npm run lint` | **fails, 6 errors** (ParcelDetailCard.tsx:59 set-state-in-effect ×~4, SplatRenderLayer.ts:356 no-useless-assignment, spatial_intersector.ts:103 no-useless-assignment) |

## Data and artifact state

- `data/` = 1.1 GiB: `raw/` 752 MiB hash-named JSON HTTP-cache entries;
  `spatial/` 337 MiB (`assets.parquet`, `gaussians/`, `meta.json`);
  `runs/reconciliation/`; `research/` 248 KiB; `out/` empty.
- `web/public/data/`: parcels.geojson 4.7 MiB, details.json 4.3 MiB,
  coverage.json 684 KiB, summary.json 12 KiB, meta.json — generated
  **2026-06-11T23:33:50Z**, run `db750ef15f69`, snapshot
  `20260611T233350Z-db750e`; sources include county_base (5,877 destroyed
  parcels, fetched 2026-06-10) and ladbs_permits (4,861 records). Artifacts are
  one month stale relative to today.
- Known-defective published labels (from BASELINE.md, to re-verify in CP1):
  489 parcels publicly `under_construction` from scheduled-inspection labels;
  1,620 debris-cleared events fabricated at the fire date.

## Docker probe

`python3 openpali-one-shot/scripts/docker_safe.py version` →
`Docker Compose version v2.40.3-desktop.1` (wrapper works; daemon reachable).
