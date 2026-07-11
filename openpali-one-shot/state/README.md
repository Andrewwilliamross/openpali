# Mutable run state

Fable owns this directory during the one-shot. Keep present truth compact;
history belongs in Git and evidence artifacts.

- `STATUS.md`: current checkpoint, component health, verified commands,
  blocker, and next integration action.
- `PLAN.md`: living implementation path mapped to the acceptance IDs and the
  architecture work packages.
- `evaluator-latest.md`: hook-owned exact final response from the fresh
  independent evaluator. Never paste or edit it manually.
- `evaluator-attestation.json`: hook-owned candidate/contract/transcript hashes
  and parsed MUST verdicts. A first launch requires it to be absent. A completed
  terminal pair ends this experiment; any later product change requires Andrew
  to initialize and commit a new candidate/run explicitly rather than reusing
  stale evaluator evidence.
- `evidence/`: concise command summaries plus full logs, model reports,
  browser screenshots/traces, spatial benchmarks, manifests, security scans,
  and operations drills.
- `FINAL_REPORT.md`: founder-readable outcome, demonstrated behavior, measured
  model/spatial/system results, limitations, and human release gates. Commit it
  in the candidate before final evaluation so the evaluator reviews its claims.
- `handoffs/`: compact recovery notes when a session or owner changes.
- `memory/`: one durable, correctable lesson per file when it is not already
  obvious from code, docs, Git, or status.
- `failures/`: meaningful failed approaches, evidence, and retry conditions.
- `runs/`: ignored headless JSONL streams and launcher metadata; useful for
  observability but not acceptance proof by themselves.

Do not record research-agent summaries as implementation evidence. Every
technical PASS must point to production code outside `openpali-one-shot/` and
current runtime evidence of the kinds required by `contract/acceptance.json`.

## Final evidence boundary

1. Commit all product code, operational assets, full evidence logs, and
   `FINAL_REPORT.md` as a clean candidate `C`.
2. Invoke `openpali-independent-evaluator` exactly against `C`. The
   `SubagentStop` hook writes `evaluator-latest.md` and
   `evaluator-attestation.json`; a FAIL returns to product work and a new clean
   candidate.
3. After PASS, do not edit product, evidence, or the founder report. Make
   exactly one child commit `D` whose diff from `C` is exactly the two
   hook-owned files: `evaluator-latest.md` and
   `evaluator-attestation.json`.
4. With a clean worktree at `D`, run
   `python3 openpali-one-shot/scripts/verify_completion.py`. Do not modify
   product code, evidence logs, the evaluator result, or the contract between
   `C` and `D`.
