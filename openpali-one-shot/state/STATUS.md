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

POST-CP5 COHERENCE (all verified on the NEW release):
- replay job: REPLAY OK against rel-3b1f5b45 (32,459 observations, exact
  hashes, zero network).
- ml-representative: typed INSUFFICIENT on the new snapshot
  (pset-7d369401); two acquisition dates now exist but the 60d span gate
  still honestly fails.
- FIXTURE RELEASE via the worker: rel-464d5ce8 (kind=fixture, published,
  promote=false — current pointer untouched, verified) with 321 fixture
  properties; its manifest includes recon-fixture-scene (fixture-kind
  selection) while representative manifests exclude it. /v1/releases
  listing added (18 API paths).
- publish_release(promote=false) added; pointer MIRROR also gated on
  promote (a fixture publish before the fix may have touched the
  non-authoritative mirror; healed by the subsequent promoting republish).

EVALUATOR PRE-FLIGHT REMAINING: restart prefect-worker on the final image;
scripts/check-fast green; commit candidate (FINAL_REPORT.md present at
root); then the CP6 protocol in state/README.md.
