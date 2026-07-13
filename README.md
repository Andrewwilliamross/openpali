# Palisades Rebuild Tracker (OpenPali)

By RE\SPRING (respring.ai)

A public evidence platform for the rebuild after the January 2025 Palisades
Fire: one map of every destroyed property, each showing **what the public
record actually documents** — cleanup, design review, permitting,
construction, and occupancy as separate evidence lanes — plus the observation
timeline behind every claim, down to the source record.

The platform never scores, ranks, or guesses. Milestones appear only when a
documented event supports them; "no public evidence" is displayed as exactly
that, never as a judgment about the property or its owners. Permit-timing
estimates come from a reviewed batch model and are suppressed with a typed
reason whenever the evidence base is insufficient.

## Architecture

A modular Python monolith with workers, serving a React/MapLibre/WebGL client:

- `pipeline/openpali/` — domain semantics, source adapters (LA County, LADBS
  permits + inspections, Socrata permits/CofO, Malibu, CAL FIRE DINS, USGS
  3DEP), bitemporal PostGIS ledger, content-addressed object store,
  censoring-aware analytics, the continual-ML platform (MLflow), the
  spatial/3D pipeline, and the FastAPI release API.
- `infra/compose.yaml` — PostgreSQL/PostGIS, SeaweedFS (S3), Prefect
  orchestration, MLflow, API, web, observability, and the drill/gate jobs.
- `web/` — the 2D-first map product with opt-in 3D (USGS post-fire lidar
  surfels + terrain through release-qualified URLs), generated API client.

Everything a user sees is pinned to ONE published release/snapshot;
publication is atomic with gates, last-known-good, and rollback. Raw source
bytes are immutable and every release replays offline from exact hashes.

## Run it locally

```bash
scripts/bootstrap        # toolchain + dependency setup (no services)
scripts/check-fast       # unit suites, lint, typecheck, OpenAPI drift
scripts/check-full       # full local gate: services, integration, ML,
                         # spatial, browser, security, release packaging
```

Service lifecycle runs through Docker Compose (see `infra/compose.yaml`);
`scripts/check-full` prints each wrapper command it needs when it cannot
invoke Docker itself.

## Data honesty

- Observation, source record, parcel, property, permit, and inspection are
  distinct; unknown stays unknown, and missing dates are never replaced.
- Analytics disclose denominators, censoring, and failed reconciliations on
  the metric itself.
- Corrections: every property card has a report path; contact details are
  stored separately and never published.

## History

The original static-site prototype (0–100 rebuild score, static JSON, no
backend) is retired; its design docs remain in
[Docs/initialbuild_docs/](Docs/initialbuild_docs/ARCHITECTURE.md) as history.
Its scoring and estimated-completion semantics no longer exist anywhere in
the product.

## License

Not yet decided. Licensing (and any open-source release) is a pending
human decision for the project owner; no license is granted by this
repository today. Government data remains public record; imagery, basemaps,
and vendor-derived assets are used under their respective terms with
attribution shown in-app, and rights-unresolved assets are excluded from
public releases by default.
