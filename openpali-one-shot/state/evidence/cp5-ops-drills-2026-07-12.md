# CP5 evidence: operational drills (OPS-001/OPS-002/E2E-001/GOV-001)

All service actions via `python3 openpali-one-shot/scripts/docker_safe.py -f
infra/compose.yaml ...` as individual commands; job containers carry the
proofs (exit codes + logs).

## Restore drill (destructive, clean namespace) — PASS

    restore-drill: Exited (0)
    pg_dump -Fc openpali (15,433,911 bytes) -> createdb openpali_restore ->
    pg_restore -> verification queries MATCH live:
      civic.recovery_observation = 33,358
      civic.snapshot = 12
      ops.publication published = 1
      ops.current_release pointer = rel-970232d7821196872b35ddf7
      spatial.spatial_asset = 10
    -> dropdb openpali_restore -> RESTORE DRILL OK

## Prefect schedule drill — PASS

    schedule-drill: Exited (0)
    45s interval schedule attached to source-refresh/default (county, online);
    SCHEDULER-created run 019f5751-294a-789c-a028-a0caaaf72e09 executed by the
    process worker to Completed; schedule detached. SCHEDULE DRILL OK

## Worker kill/resume drill — PASS (with a real finding + landed remediation)

    1. full-release job triggers full-refresh-release/default and waits.
    2. Worker confirmed mid-flow (run 'curly-rat' 66d01ff3...), then
       `restart prefect-worker` killed the flow subprocess.
    FINDING: the killed run lingers in Running FOREVER — Prefect process
    workers have no zombie heartbeat reaper; the trigger job hangs and
    nothing marks the failure. Remediation LANDED: `openpali flow-reap`
    (compose job flow-reap) force-marks zombie Running runs Crashed:
        reaped 66d01ff3 (curly-rat) Running -> Crashed
    3. The waiting trigger job then exited 5 with `state=Crashed` — the
       failure is VISIBLE, never silent.
    4. Recovery: full-release re-triggered after the restart (result appended
       below) — convergence guaranteed by idempotent acquisition + atomic
       single-transaction promotion (a crashed run cannot half-move the
       current pointer).

## Observability profile + injected alert — PASS

    Profile `observability`: prometheus v3.9.1 + blackbox-exporter v0.28.0
    (both digest-pinned; config baked into openpali-prometheus:local — the
    wrapper forbids host binds). Probes: api/web/mlflow/prefect health.
    Rule: ServiceDown = probe_success==0 for 30s.

    Baseline:   alert-check (EXPECT none)      -> ALERT-CHECK OK
    Injection:  stop mlflow                    -> alert-check-firing
                ALERT-CHECK OK: ServiceDown firing for mlflow:5000
    Resolution: up mlflow -> alert-check (none) -> result appended below

    Wrapper constraints found on the way: `.env` interpolation is not
    honored and `extends:` is rejected — expectation variants are separate
    static services.

## CI (executes the SAME local gates)

    .github/workflows/ci.yml: fast-gate job = scripts/check-fast (pinned
    installs) + web build; supply-chain job = image builds (digest-pinned
    bases), SPDX SBOMs (anchore), vulnerability scan failing on fixable
    high/critical, gitleaks full-history secret scan, pip/npm audits.

## Governance/quality wiring

    - Reconciliation disclosures now ride ON affected metric values
      (`reconciliation_disclosure` + top-level data_quality_warnings) — a
      failed independent cross-check cannot be missed by consumers.
    - Fault-drill isolation: the publication fault module restores the
      current-release pointer around itself.
    - SECURITY.md threat model committed; LARIAC rights exclusion live in
      the manifest; scripts/check-full orchestrates host + service halves.

## Recovery run result — PASS (converged on FRESH live data)

    Resolution: alert-check (EXPECT none) -> Exited 0 (ServiceDown resolved
    after mlflow restoration)
    Recovery:   full-release -> flow_run cb0eeeb0 state=Completed
    API:        current release rel-3b1f5b4506807355fffa930e (representative,
                6,204 properties — the county universe grew since the prior
                acquisition), lkg = rel-970232d7 (the pre-drill release).

The complete loop is proven: worker killed mid-flow -> zombie made VISIBLE
(flow-reap -> Crashed; trigger job exits 5) -> re-trigger -> full 7-source
live refresh -> snapshot -> analytics -> atomic release promotion with LKG.
No partial state survived the crash (single-transaction promotion).
