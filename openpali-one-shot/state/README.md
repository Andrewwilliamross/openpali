# Mutable run state

Fable owns this directory during the one-shot. Keep current truth small and use
artifacts for history.

Expected outputs:

- `STATUS.md`: current verified state, best valid commit, failing gate, blocker,
  and next action.
- `PLAN.md`: current path mapped to acceptance IDs.
- `acceptance-results.json`: results conforming to
  `../contract/evidence.schema.json`; generate the terminal version only after
  the final evaluator capture so its timestamp and statuses can be bound.
- `evaluator-latest.md`: exact output captured automatically from the fresh
  evaluator.
- `evaluator-attestation.json`: hook-owned evaluator/session/commit/transcript
  binding; the principal must never create or edit it manually.
- `evaluator/`: hook-owned exact evaluator and attestation archives.
- `evidence/`: full logs, reports, screenshots, benchmark outputs, manifests,
  and command summaries.
- `FINAL_REPORT.md`: founder-readable terminal report included only in the
  one evidence-only commit after evaluator capture.
- `handoffs/`: compact recovery notes only when a session or owner changes.
- `memory/`: one durable lesson per file; no facts already obvious from code,
  Git, or the current status.
- `failures/`: meaningful failed approaches with evidence and retry conditions.
- `runs/`: ignored launcher/session manifests, stream output, and transcript
  archives for experiment observability. These are not acceptance proof.
