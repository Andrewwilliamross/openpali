# Security policy and threat model

OpenPali is a locally deployable civic data platform that republishes and
analyzes PUBLIC recovery records for the 2025 Palisades fire. It stores no
resident accounts, no private submissions beyond an optional correction
contact, and no credentials besides local fixture secrets.

## Reporting

Open a private report to the repository owner (see repo metadata). Do not
file public issues for suspected vulnerabilities.

## Deployment trust model

- Single-host Docker Compose (`infra/compose.yaml`). Every runtime network is
  `internal: true`; the ONE egress point is the labeled squid proxy with a
  documented destination allowlist (`infra/proxy/squid.conf`) — services
  cannot reach arbitrary hosts, and nothing binds host ports except the
  proxy's loopback accel listeners.
- Third-party images are digest-pinned. The pipeline image runs as a
  non-root user (uid 10001). No host binds, no docker socket, no host
  namespaces.
- Credentials in the compose file are LOCAL FIXTURE VALUES for a
  single-machine deployment; production deployments must inject real secrets
  via environment (never committed) and rotate the fixture values.
- PostgreSQL is not host-reachable; operational actions run as compose job
  services with least privilege (no `docker exec` pathway).

## Data-integrity model (the primary threat surface)

The product's main risk is publishing WRONG civic facts, not classic
exfiltration:

- Immutable evidence: raw source bytes are content-addressed; the object
  store refuses same-key different-byte writes; acquisition runs record
  digests, counts, and server-side cross-checks (count-before/after paging
  mutation detection).
- Releases are atomic single-transaction promotions gated by fail-closed
  checks (undocumented taxonomy, empty universe, failed sources, spatial
  slot integrity, rights-unsafe assets); rollback restores last-known-good.
- The API serves only release-qualified, manifest-selected artifacts; stale
  or foreign asset versions 404.
- ML: point-in-time discipline is enforced by precommitted gates; promotion
  requires a named human reviewer and final-holdout-only evaluation;
  fixture-trained models are structurally barred from civic serving.
- Synthetic/fixture identities (reserved source ids, APN prefix 99) cannot
  enter non-fixture release manifests.

## Input handling

- All upstream payloads are treated as untrusted data: typed adapters parse
  with schema fingerprints and fail closed on drift; nothing from upstream
  is executed or templated into queries (SQLAlchemy bound parameters
  everywhere; MVT tiles via parameterized ST_AsMVT).
- API path parameters for spatial assets reject traversal (`..`, absolute
  paths) and only resolve within the release's selected asset prefixes.
- The web client consumes same-origin `/v1` only; external tile sources are
  the documented public basemap/terrain/imagery hosts.

## Privacy

- Only agency-published parcel-level records are stored. No person names,
  no contact information from sources, no resident-submitted media.
- The correction path stores a minimal contact channel, rate-limited, in a
  restricted table not exposed by any public endpoint.
- Rights-unresolved spatial assets (LARIAC-derived corpus) are registered,
  excluded from release manifests, and documented pending sponsor license
  decisions.

## Known limitations (deliberate, documented)

- Local fixture credentials in compose are not secrets; single-host model
  has no network segmentation beyond compose internals.
- TLS terminates at the operator's boundary; the local accel listeners are
  loopback HTTP by design.
- Dependency and image scanning runs in CI (`scripts/check-full`); no
  runtime IDS is included.
