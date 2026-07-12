# Run status

State: `CP5_DRILLS_COMPLETE__CP6_TERMINAL_PROTOCOL_NEXT`

Verified checkpoints: CP0 (`edde389`), CP1 (`9c24e27`), CP2 (`0310c98`),
CP3 (`691ea8c`), CP4A+CP4B (`d85793e`..`9ca6588`), CP4C (routes + API-backed
evidence + corrections + a11y, browser gate 6/6), CP5 drills (this commit).

CP5 COMPLETE (evidence cp5-ops-drills-2026-07-12.md):
- Restore drill PASS (destructive clean-namespace restore, verified).
- Schedule drill PASS (scheduler-created run executed by the worker).
- Worker kill drill PASS with a REAL finding remediated: zombie Running
  runs -> `flow-reap` makes failures visible; recovery re-trigger published
  a FRESH live representative release rel-3b1f5b45 (6,204 properties, up
  from 5,877 — live re-acquisition of all 7 sources) with LKG intact.
- Observability PASS: pinned prometheus+blackbox profile; injected mlflow
  outage fired ServiceDown (alert-check-firing exit 0) and resolved after
  restoration (alert-check exit 0).
- CI (fast gate + SBOM/vuln/gitleaks/audits), reconciliation disclosures on
  metric values, fault-drill pointer isolation, SECURITY.md, check-full.

FINAL_REPORT.md DRAFTED at repo root (demonstrated results / limitations /
APPROVAL-001 sections) — review before evaluator run.

CP6 terminal protocol REMAINING (openpali-one-shot/state/README.md governs):
1. OPTIONAL final sweeps: rerun scripts/check-fast (green), consider a final
   e2e-browser run against rel-3b1f5b45.
2. Commit the candidate containing FINAL_REPORT.md (clean tree).
3. Run the openpali-independent-evaluator subagent FRESH on the clean
   candidate; the hook captures the response.
4. Repair loop if any MUST fails; else create EXACTLY ONE child commit
   changing only state/evaluator-latest.md + state/evaluator-attestation.json.
5. `python3 openpali-one-shot/scripts/verify_completion.py` must exit 0.

NOTE for the evaluator run: the zero-network replay job validates the
CURRENT release — rerun `replay` job against rel-3b1f5b45 first (its raw
pages are new); ml-representative + spatial selection also reference the
current release and may warrant a re-run for coherence.
