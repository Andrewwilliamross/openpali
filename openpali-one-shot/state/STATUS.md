# Run status

State: `CP2_PLATFORM_SPINE_COMPLETE`

Verified checkpoints: CP0 (`edde389`), CP1 (`9c24e27`), CP2 (this commit).

CP2 outcomes (all behavior exercised on the running stack; evidence in
`state/evidence/cp2-api-verification-2026-07-12.log`):
- Compose stack via `docker_safe.py` wrapper: PostGIS 17/3.5 + SeaweedFS 4.39 +
  Prefect 3.7.8 server/worker + MLflow 3.14 + FastAPI + web nginx, all healthy;
  single squid proxy = only non-internal service (loopback ingress accel
  58000/58080/54200/55000/58333 + CONNECT egress allowlist on 3128 — Docker
  Desktop cannot publish ports from internal networks, verified empirically).
- Alembic migration 0001 creates the full canonical schema (source/civic/
  analytics/ml/spatial/ops) on empty PostGIS; migrate/migrate-reset/bucket-init/
  test-integration/slice-dev run as Compose job services (wrapper blocks
  run/exec).
- Content-addressed ObjectStore: dedup, different-byte overwrite rejection,
  digest-verified reads (integration-tested on real SeaweedFS).
- ArcGIS adapter: stable OID ordering, metadata snapshot page, count-before/
  after mutation detection, repeated-page detection, typed failures; true
  offline replay constructs no network client (unit-tested).
- LIVE slice through the worker egress proxy: county acquisition (5,877
  records, 7 raw pages), ledger load (11,741 observations, deterministic IDs,
  idempotent reload = 0 new), snapshot snap-10ca317c (5,877 property states,
  point-in-time correct — late-arriving earlier-occurrence excluded before its
  observed_at), release rel-ee79a630 published atomically with LKG pointer +
  non-authoritative mirror.
- API verified end-to-end from host: ready checks (migrations+release+S3),
  /v1/releases/current resolver, release-qualified search/detail/observations/
  sources, PostGIS MVT tiles (z13 338KB/z14 227KB/z15 98KB), strong ETag +
  bodyless 304, cross-release cursor rejection (400 problem+json), unknown
  release 404, live /v1/status/sources, same-origin web→api /v1 proxy.
- OpenAPI exported to contracts/openapi.json; TS client generated
  (web/src/api/generated via @hey-api/openapi-ts).
- Methods review (CP1) returned 1 BLOCKER + 6 SHOULD-FIX: ALL fixed
  (observation discriminator enters deterministic ID; interval-aware conflict
  intersection; destruction interval capped at observed date; distinct
  flag-missing event type; outcome-branch unit tests; 'Other' neighborhood
  bucket). 141 pipeline tests + 5 in-cluster integration tests pass.
- check-fast green (pipeline-tests, web-tests, web-lint, web-typecheck).

Technical criteria progress: TRUTH-001 implemented+reviewed; DATA-002 core
proven (deterministic IDs, bitemporal point-in-time, idempotency, real PostGIS
constraints); BACKEND-001 core routes+budget-scale tiles live; DATA-001/PUB-001
partial (county source only; full gates/fault-injection in CP3).

Immediate next action: CP3 — remaining adapters (LADBS permits/inspections,
Socrata cross-checks, Malibu, CAL FIRE DINS with APN/spatial join + ambiguity
counts), Prefect flows/deployments through the worker, metric catalog +
independent reconciliation, staged→gated→promoted publication with rollback +
fault injection, representative release + zero-network replay.
