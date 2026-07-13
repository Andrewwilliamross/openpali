# OpenPali local stack

Validated-wrapper Compose topology. Start/stop/build ONLY through
`python3 openpali-one-shot/scripts/docker_safe.py` (during the one-shot run) or
plain `docker compose` under your own trust boundary afterwards.

## Operator sequence (fresh checkout)

Every step is explicit because the one-shot guardrail requires the Docker
wrapper to be the ENTIRE shell command (scripts cannot invoke it internally).
All steps are idempotent.

```sh
# 1. build the three locally built images exactly once each
python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml build api web proxy
# 2. start the stack
python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d --wait
# 3. host dependencies (python venv + web node_modules)
./scripts/bootstrap
# 4. database schema (job service; exit code via `ps -a`, logs via `logs migrate`)
python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d migrate
# 5. object-store buckets
python3 openpali-one-shot/scripts/docker_safe.py -f infra/compose.yaml up -d bucket-init
# 6. fast gate
./scripts/check-fast
# 7. readiness
#    http://127.0.0.1:58000/health/ready must report status=ready once a
#    release exists (dev slice: up -d slice-dev)
```

NOTE: several job services share the `openpali-pipeline:local` image; always
build via the explicit service list above (a bare `build` would race the same
tag from multiple services).

## Topology

- All runtime services live on the `internal` (internal: true) network, which
  cannot publish host ports on Docker Desktop.
- The single `proxy` service (squid, label `org.openpali.egress-proxy=true`)
  owns the non-internal `egress` network and is both:
  - **ingress**: loopback-published reverse-accel ports
    58000→api, 58080→web, 54200→prefect, 55000→mlflow, 58333→S3;
  - **egress**: forward proxy `proxy:3128` with a destination allowlist of the
    documented public sources (workers set HTTP(S)_PROXY).
- PostgreSQL is intentionally NOT reachable from the host: anything that needs
  the database runs as a Compose job service
  (`up -d <job> && wait <job>`): `migrate`, `bucket-init`, `test-integration`,
  `slice-dev`.

## Fixture credentials

All credentials in this stack are non-secret local fixtures (prefix
`openpali-local-`); the wrapper rejects anything else. Production secret
injection is documented separately and never flows through this file.
