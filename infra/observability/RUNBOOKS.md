# Alert runbooks

Alerts come from the `observability` profile (prometheus + blackbox; rule
file `alerts.yml`). Every command below is a complete wrapper invocation
from the repository root.

## ServiceDown (critical)

Meaning: a health probe (`probed` label names the target) failed for 30s.

1. Confirm and identify:
   `python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml ps -a --format '{{.Name}} {{.State}} {{.ExitCode}}'`
2. Read the failing service's log:
   `python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml logs --no-log-prefix --tail 100 <service>`
3. Restart it:
   `python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d <service>`
4. Verify resolution (exits 0 when no ServiceDown is firing):
   `python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml --profile observability up -d --force-recreate alert-check`
5. If `api` was down and users saw the offline badge, no repair beyond the
   restart is needed — the web client re-pins the release automatically.
6. If `prefect-worker` was down mid-flow, zombie runs may linger in
   Running. Make failures visible, then re-trigger:
   `python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d flow-reap`
   `python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d full-release`
7. If `postgres` was down: after restart, run the integrity half of the
   restore drill before trusting new publications:
   `python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d restore-drill`
   `python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d restore-verify`

## Suspected data corruption / bad release

1. Roll back to last-known-good (atomic pointer move):
   run the `release-rollback` CLI via a job, or re-promote a known release
   through `release-candidate/default`.
2. Verify: `GET /v1/releases/current` shows the expected release;
   `restore-verify` job exits 0.

## Disaster recovery (host loss)

Volumes `pgdata` + `seaweed-data` are authoritative. On a fresh host:
bootstrap, `up -d` the core services, then run `restore-verify` — it fails
closed if the object plane and database disagree.
