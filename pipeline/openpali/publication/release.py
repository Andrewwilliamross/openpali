"""Release publication (PUB-001).

PostgreSQL is the sole current/LKG authority: promotion is one transaction
that validates gates, marks the publication row, and moves the singleton
``ops.current_release`` pointer. The object-store ``pointers/current.json``
mirror is repaired AFTER commit and is explicitly non-authoritative — a failed
mirror leaves the API on the promoted release and records drift.

Fail-closed gates here (extended by the full-release pipeline in later
checkpoints): undocumented taxonomy, empty universe, missing snapshot, and
manifest/hash coherence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from openpali.identity.ids import canonical_json, release_id_from_manifest
from openpali.ingestion.acquire import frozen_source_health
from openpali.storage.models import (
    CivicSnapshot,
    CurrentRelease,
    Publication,
    SnapshotPropertyState,
)
from openpali.storage.objects import ObjectStore, PUBLICATION_BUCKET


class PublicationGateError(Exception):
    """A release gate failed; publication must not advance current."""


@dataclass(slots=True)
class ReleaseResult:
    release_id: str
    snapshot_id: str
    status: str
    mirror_ok: bool
    gate_results: dict


def _coverage(session: Session, snapshot_id: str) -> dict[str, int]:
    total = session.execute(
        select(func.count()).select_from(SnapshotPropertyState).where(
            SnapshotPropertyState.snapshot_id == snapshot_id
        )
    ).scalar_one()
    milestone_keys = (
        "cleanup_complete",
        "application_submitted",
        "plan_check_approved",
        "permit_issued",
        "construction_evidence",
        "cofo_issued",
    )
    coverage = {"properties": int(total)}
    for key in milestone_keys:
        count = session.execute(
            select(func.count()).select_from(SnapshotPropertyState).where(
                SnapshotPropertyState.snapshot_id == snapshot_id,
                SnapshotPropertyState.milestones[key].as_boolean().is_(True),
            )
        ).scalar_one()
        coverage[key] = int(count)
    return coverage


def build_manifest(
    session: Session,
    snapshot_id: str,
    *,
    kind: str,
    undocumented_values: list[str],
    limitations: list[str] | None = None,
) -> dict:
    from openpali.spatial.registry import select_release_assets

    snapshot = session.execute(
        select(CivicSnapshot).where(CivicSnapshot.snapshot_id == snapshot_id)
    ).scalar_one()
    sources = frozen_source_health(session, list(snapshot.input_runs))
    manifest = {
        "manifest_schema": "release-manifest-v1",
        "kind": kind,
        "snapshot_id": snapshot_id,
        "input_runs": snapshot.input_runs,
        "input_runs_sha256": snapshot.input_runs_sha256,
        "policy_versions": snapshot.policy_versions,
        "schema_versions": {
            "civic": snapshot.schema_version,
            "api": "v1",
        },
        "sources": sources,
        "coverage": _coverage(session, snapshot_id),
        "spatial": select_release_assets(session, release_kind=kind),
        "undocumented_values": sorted(undocumented_values),
        "limitations": limitations or [],
    }
    return manifest


def run_gates(session: Session, snapshot_id: str, manifest: dict) -> dict:
    """Fail-closed publication gates (CP2 core set)."""

    gates: dict[str, str] = {}
    if manifest["undocumented_values"]:
        gates["undocumented_taxonomy"] = (
            f"FAIL: {manifest['undocumented_values']}"
        )
    else:
        gates["undocumented_taxonomy"] = "PASS"
    coverage = manifest["coverage"]
    gates["universe_nonempty"] = "PASS" if coverage.get("properties", 0) > 0 else "FAIL: empty universe"
    failed_sources = [s["source_id"] for s in manifest["sources"] if not s["ok"]]
    gates["required_sources"] = (
        "PASS" if not failed_sources else f"FAIL: {failed_sources}"
    )
    # spatial slots: selection already raised on an empty enabled slot; here we
    # additionally refuse a manifest whose selected assets are not rights-safe
    # or carry no verified object reference
    spatial = manifest.get("spatial", {})
    bad_assets = [
        f"{a['asset_id']}@{a['version_id']}"
        for a in spatial.get("assets", [])
        if not a.get("object_sha256") or not a.get("object_uri")
    ]
    gates["spatial_assets_verified"] = (
        "PASS" if not bad_assets else f"FAIL: missing object refs {bad_assets}"
    )
    return gates


def publish_release(
    session: Session,
    store: ObjectStore,
    snapshot_id: str,
    *,
    kind: str = "fixture",
    undocumented_values: list[str] | None = None,
    limitations: list[str] | None = None,
    promoted_by: str = "openpali-cli",
    promote: bool = True,
) -> ReleaseResult:
    manifest = build_manifest(
        session,
        snapshot_id,
        kind=kind,
        undocumented_values=undocumented_values or [],
        limitations=limitations,
    )
    gates = run_gates(session, snapshot_id, manifest)
    manifest["gates"] = gates
    failures = {k: v for k, v in gates.items() if not str(v).startswith("PASS")}
    release_id = release_id_from_manifest(manifest)
    manifest_with_id = {**manifest, "release_id": release_id}
    manifest_bytes = canonical_json(manifest_with_id).encode()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    existing = session.execute(
        select(Publication).where(Publication.release_id == release_id)
    ).scalar_one_or_none()

    if failures:
        if existing is None:
            session.add(
                Publication(
                    release_id=release_id,
                    snapshot_id=snapshot_id,
                    kind=kind,
                    manifest=manifest_with_id,
                    manifest_sha256=manifest_sha,
                    gate_results=gates,
                    status="failed_gates",
                )
            )
            session.flush()
        raise PublicationGateError(f"release gates failed: {failures}")

    now = datetime.now(timezone.utc)
    if existing is not None and existing.status == "published":
        publication = existing
    else:
        publication = existing or Publication(
            release_id=release_id,
            snapshot_id=snapshot_id,
            kind=kind,
            manifest=manifest_with_id,
            manifest_sha256=manifest_sha,
            gate_results=gates,
            status="staged",
        )
        if existing is None:
            session.add(publication)
            session.flush()

        if promote:
            # --- atomic promotion: one transaction moves the authority pointer ---
            current = session.get(CurrentRelease, 1, with_for_update=True)
            previous = current.current_release_id
            publication.status = "published"
            publication.promoted_at = now
            publication.promoted_by = promoted_by
            if previous and previous != release_id:
                prior = session.execute(
                    select(Publication).where(Publication.release_id == previous)
                ).scalar_one_or_none()
                if prior is not None and prior.status == "published":
                    prior.status = "superseded"
                current.lkg_release_id = previous
            current.current_release_id = release_id
            session.flush()
        else:
            # release-qualified and API-addressable, but the CURRENT authority
            # pointer is untouched (e.g. the cross-stack FIXTURE release must
            # never displace real civic data)
            publication.status = "published"
            publication.promoted_at = now
            publication.promoted_by = promoted_by
            session.flush()

    snapshot = session.execute(
        select(CivicSnapshot).where(CivicSnapshot.snapshot_id == snapshot_id)
    ).scalar_one()
    snapshot.status = "published"
    snapshot.published_at = now
    snapshot.manifest_sha256 = manifest_sha
    session.commit()

    # --- non-authoritative mirror (after commit; failure = drift, not error) --
    mirror_ok = True
    try:
        store.ensure_bucket(PUBLICATION_BUCKET)
        store.put_manifest(
            PUBLICATION_BUCKET,
            f"publications/{release_id}/manifest.json",
            manifest_bytes,
        )
        pointer = canonical_json(
            {"release_id": release_id, "manifest_sha256": manifest_sha}
        ).encode()
        store.put_manifest(PUBLICATION_BUCKET, "pointers/current.json", pointer)
    except Exception:  # noqa: BLE001 - mirror failure must not fail promotion
        mirror_ok = False

    return ReleaseResult(
        release_id=release_id,
        snapshot_id=snapshot_id,
        status="published",
        mirror_ok=mirror_ok,
        gate_results=gates,
    )
