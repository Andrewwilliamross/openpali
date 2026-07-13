"""Deterministic ID derivations.

Canonicalization rules (PUB-001): JSON with sorted keys, compact separators,
UTF-8; the release ID canonicalization EXCLUDES the release ID itself,
signatures, mutable aliases, build/MLflow timestamps, and mirror state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

IDENTITY_SEED_POLICY_VERSION = "identity-seed-v1"


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def property_id_from_apn(apn: str) -> str:
    """Durable public property ID.

    Seed policy v1: the authoritative identity seed is the first-observed
    normalized county APN. APN changes/merges/splits later attach explicit
    relations on ``civic.property_identity`` rather than re-deriving the ID.
    """

    seed = f"county_apn:{apn}"
    return "prop-" + _digest(f"{IDENTITY_SEED_POLICY_VERSION}:{seed}")[:20]


def identity_seed_for_apn(apn: str) -> str:
    return f"county_apn:{apn}"


def record_version_id(source_id: str, native_key: str, payload_sha256: str) -> str:
    return "srv-" + _digest(canonical_json(
        {"source": source_id, "native_key": native_key, "payload": payload_sha256}
    ))[:24]


def acquisition_run_id(source_id: str, parameters: dict, requested_at_iso: str) -> str:
    return "run-" + _digest(canonical_json(
        {"source": source_id, "parameters": parameters, "requested_at": requested_at_iso}
    ))[:24]


def snapshot_id_from_inputs(
    input_run_ids: list[str], policy_versions: dict[str, str], cutoff_iso: str,
    schema_version: str,
) -> str:
    return "snap-" + _digest(canonical_json(
        {
            "input_runs": sorted(input_run_ids),
            "policies": policy_versions,
            "cutoff": cutoff_iso,
            "schema": schema_version,
        }
    ))[:24]


def dataset_id(snapshot_id: str, cohort_policy: str, target_policy: str,
               feature_schema_version: str, cutoff_iso: str) -> str:
    return "ds-" + _digest(canonical_json(
        {
            "snapshot": snapshot_id,
            "cohort": cohort_policy,
            "target": target_policy,
            "features": feature_schema_version,
            "cutoff": cutoff_iso,
        }
    ))[:24]


#: Manifest envelope keys excluded from the semantic release hash.
RELEASE_ENVELOPE_KEYS = frozenset(
    {"release_id", "signatures", "aliases", "built_at", "mlflow_timestamps", "mirror"}
)


def release_id_from_manifest(manifest: dict) -> str:
    """Compute the public release ID from versioned canonical manifest JSON,
    excluding the envelope keys (the ID is inserted afterwards)."""

    semantic = {k: v for k, v in manifest.items() if k not in RELEASE_ENVELOPE_KEYS}
    return "rel-" + _digest(canonical_json(semantic))[:24]
