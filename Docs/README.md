# OpenPali documentation

OpenPali brings public records, geospatial data, and imagery together for
analysis of the Palisades rebuild. Start with the guides below to explore the
map, work on the platform, or contribute.

## Guides

| Task | Guide |
| --- | --- |
| Understand the platform and get started | [Project overview](../README.md) |
| Run or develop the map interface | [Frontend guide](../web/README.md) |
| Work on ingestion, publication, analytics, or spatial processing | [Python platform guide](../pipeline/README.md) |
| Start the database, API, storage, and workers | [Local stack guide](../infra/README.md) |
| Make a contribution and verify it | [Contributor guide](../CONTRIBUTING.md) |
| Build or preview the project website | [Website guide](../site/README.md) |
| Use the current identity or prepare launch materials | [Signal brand kit](Brand/README.md) and [launch kit](Brand/LAUNCH.md) |
| Report a vulnerability or understand community expectations | [Security policy](../SECURITY.md) and [Code of Conduct](../CODE_OF_CONDUCT.md) |

For implementation details, see the [source adapters](../pipeline/openpali/adapters/),
[metric definitions](../pipeline/openpali/metrics/catalog.py), and
[API contract](../contracts/). Source-code and data rights are described in the
[licensing notice](../README.md#license-and-data-rights).

## Current research and implementation

- [September 2026 CTO audit](Research/2026-09-24-CTO-AUDIT.md)
- [Verified source inventory](Research/2026-09-24-SOURCE-INVENTORY.md)
- [Data expansion research](Research/2026-09-24-DATA-EXPANSION.md)
- [Recovery implementation record](Plans/2026-09-24-IMPLEMENTATION.md)
- [Systems design space](Research/2026-09-29-SYSTEMS-DESIGN-SPACE.md)
- [Dated Palisades scene experiment](Research/2026-09-29-PALISADES-SCENE.md)

## Plans and research

- [Plans](Plans/README.md) — implementation proposals, sequencing, dependencies,
  and decision records.
- [Tickets](Tickets/README.md) — scoped product and engineering work.
- [Research](Research/README.md) — investigations, evaluations, and supporting evidence.
- [Roadmap](../ROADMAP.md) — dated technical and product direction.

These documents record decisions and proposed work. Check the current guides
and implementation before treating a proposal as shipped behavior.

## Historical reference

[`initialbuild_docs/`](initialbuild_docs/) preserves the earlier prototype's
architecture, data sources, methodology, artifacts, and spatial system.
It does not describe the current platform; the prototype's scoring and
completion estimates are retired.

Earlier visual directions are preserved in the [design studies](../design-lab/README.md)
and [brand history](Brand/README.md#design-history). Use the Signal brand kit
for current presentation work.
