"""OpenPali production platform package.

Modular-monolith boundaries (see openpali-one-shot/research/production-mvp-architecture.md):

- ``domain``: enums, identifiers, observations, taxonomy, policies. No I/O.
- ``ingestion``: pure normalization from raw source payloads to domain
  observations, plus acquisition services (added with the platform spine).
- Later slices add ``storage``, ``identity``, ``metrics``, ``ml``, ``spatial``,
  ``publication``, ``api``, ``orchestration``, and ``observability``.

The legacy ``palisades`` package remains the source-adapter substrate during
migration; new semantics live here and are the only authority for public
claims.
"""

__all__ = ["domain"]
