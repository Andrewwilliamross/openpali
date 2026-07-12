"""Spatial asset registry + release selection (SPATIAL-001).

Asset identity model:

    asset_id     stable identity of one asset (subject x kind x vintage slot)
    version_id   content-derived version (hash of the immutable inputs)

Release selection returns EXACTLY ONE nonempty version per enabled
(subject, kind, vintage_slot) so explicit vintage comparison is possible while
accidental epoch concatenation, empty enabled slots, and stale tiles are
structurally impossible. Assets whose rights are not resolved to a rights-safe
state are excluded WITH a recorded reason — exclusion of one asset never
disables the spatial path itself.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from openpali.storage.models import AssetRelation, SpatialAsset

SELECTION_POLICY = "latest-ready-rights-safe-v1"

#: rights states a public release may select. Everything else (unresolved,
#: proprietary, license_pending) is excluded with a recorded reason.
RIGHTS_SAFE_STATES = ("public_domain", "openly_licensed", "synthetic_fixture")


def version_id_from_hashes(*shas: str) -> str:
    return "sv-" + hashlib.sha256("|".join(shas).encode()).hexdigest()[:20]


def register_asset_version(
    session: Session,
    *,
    asset_id: str,
    version_id: str,
    subject_type: str,
    subject_id: str,
    asset_kind: str,
    vintage_slot: str,
    source_id: str,
    observation_kind: str,
    rights_state: str,
    horizontal_crs: str | None = None,
    vertical_datum: str | None = None,
    units: str | None = None,
    transform: dict | None = None,
    registration_residual_m: float | None = None,
    acquisition_start: datetime | None = None,
    acquisition_end: datetime | None = None,
    source_updated_at: datetime | None = None,
    processed_at: datetime | None = None,
    extent_wkt: str | None = None,
    resolution_m: float | None = None,
    coverage: dict | None = None,
    quality: dict | None = None,
    lineage: list | None = None,
    object_uri: str | None = None,
    object_sha256: str | None = None,
    format_version: str | None = None,
    status: str = "registered",
) -> bool:
    """Idempotent insert of one immutable asset version. Returns created?"""

    result = session.execute(
        pg_insert(SpatialAsset)
        .values(
            asset_id=asset_id,
            version_id=version_id,
            subject_type=subject_type,
            subject_id=subject_id,
            asset_kind=asset_kind,
            vintage_slot=vintage_slot,
            source_id=source_id,
            horizontal_crs=horizontal_crs,
            vertical_datum=vertical_datum,
            units=units,
            transform=transform or {},
            registration_residual_m=registration_residual_m,
            acquisition_start=acquisition_start,
            acquisition_end=acquisition_end,
            source_updated_at=source_updated_at,
            ingested_at=datetime.now(timezone.utc),
            processed_at=processed_at,
            observation_kind=observation_kind,
            extent=extent_wkt,
            resolution_m=resolution_m,
            coverage=coverage or {},
            quality=quality or {},
            lineage=lineage or [],
            rights_state=rights_state,
            object_uri=object_uri,
            object_sha256=object_sha256,
            format_version=format_version,
            status=status,
        )
        .on_conflict_do_nothing(constraint="uq_spatial_asset_version")
        .returning(SpatialAsset.id)
    ).first()
    session.flush()
    return result is not None


def add_relation(
    session: Session,
    *,
    from_asset: tuple[str, str],
    to_asset: tuple[str, str],
    relation: str,
    detail: dict | None = None,
) -> None:
    session.execute(
        pg_insert(AssetRelation)
        .values(
            from_asset_id=from_asset[0],
            from_version_id=from_asset[1],
            to_asset_id=to_asset[0],
            to_version_id=to_asset[1],
            relation=relation,
            detail=detail or {},
        )
        .on_conflict_do_nothing(constraint="uq_asset_relation")
    )
    session.flush()


def mark_ready(session: Session, asset_id: str, version_id: str) -> None:
    asset = session.execute(
        select(SpatialAsset).where(
            SpatialAsset.asset_id == asset_id,
            SpatialAsset.version_id == version_id,
        )
    ).scalar_one()
    asset.status = "ready"
    session.flush()


class EmptySlotError(Exception):
    """An enabled spatial slot selected an asset version with no content."""


def select_release_assets(session: Session, *, release_kind: str = "representative") -> dict:
    """Selection for a release manifest.

    Returns {"selection_policy", "assets": [...], "excluded": [...]}. For each
    (subject_type, subject_id, asset_kind, vintage_slot) with at least one
    ready + rights-safe version, the newest version (processed_at, then
    ingested_at) is selected. A selected version with zero content bytes/tiles
    raises: an enabled slot may be absent, never silently empty.

    Synthetic fixture assets are TECHNICALLY excluded from every non-fixture
    release: they can never become public spatial facts (MULTIMODAL-001).
    """

    rows = list(
        session.execute(
            select(SpatialAsset).order_by(
                SpatialAsset.subject_type,
                SpatialAsset.subject_id,
                SpatialAsset.asset_kind,
                SpatialAsset.vintage_slot,
            )
        ).scalars()
    )
    slots: dict[tuple, list[SpatialAsset]] = {}
    excluded: list[dict] = []
    for asset in rows:
        key = (asset.subject_type, asset.subject_id, asset.asset_kind, asset.vintage_slot)
        synthetic = (
            asset.rights_state == "synthetic_fixture"
            or asset.subject_type == "fixture"
        )
        if synthetic and release_kind != "fixture":
            excluded.append(
                {
                    "asset_id": asset.asset_id,
                    "version_id": asset.version_id,
                    "asset_kind": asset.asset_kind,
                    "vintage_slot": asset.vintage_slot,
                    "reason": "synthetic fixture asset; barred from non-fixture releases",
                }
            )
            continue
        if asset.rights_state not in RIGHTS_SAFE_STATES:
            excluded.append(
                {
                    "asset_id": asset.asset_id,
                    "version_id": asset.version_id,
                    "asset_kind": asset.asset_kind,
                    "vintage_slot": asset.vintage_slot,
                    "reason": f"rights_state={asset.rights_state} is not rights-safe",
                }
            )
            continue
        if asset.status != "ready":
            continue
        slots.setdefault(key, []).append(asset)

    selected: list[dict] = []
    for key, versions in sorted(slots.items()):
        versions.sort(
            key=lambda a: (
                a.processed_at or a.ingested_at,
                a.ingested_at,
                a.version_id,
            ),
            reverse=True,
        )
        chosen = versions[0]
        content_units = int(
            (chosen.quality or {}).get("content_units")
            or (chosen.coverage or {}).get("tiles")
            or 0
        )
        if content_units <= 0:
            raise EmptySlotError(
                f"selected version {chosen.asset_id}@{chosen.version_id} for slot "
                f"{key} has no content; an enabled slot may not be empty"
            )
        selected.append(
            {
                "subject_type": chosen.subject_type,
                "subject_id": chosen.subject_id,
                "asset_kind": chosen.asset_kind,
                "vintage_slot": chosen.vintage_slot,
                "asset_id": chosen.asset_id,
                "version_id": chosen.version_id,
                "source_id": chosen.source_id,
                "observation_kind": chosen.observation_kind,
                "horizontal_crs": chosen.horizontal_crs,
                "vertical_datum": chosen.vertical_datum,
                "acquisition_start": (
                    chosen.acquisition_start.isoformat() if chosen.acquisition_start else None
                ),
                "acquisition_end": (
                    chosen.acquisition_end.isoformat() if chosen.acquisition_end else None
                ),
                "processed_at": (
                    chosen.processed_at.isoformat() if chosen.processed_at else None
                ),
                "resolution_m": chosen.resolution_m,
                "rights_state": chosen.rights_state,
                "object_uri": chosen.object_uri,
                "object_sha256": chosen.object_sha256,
                "format_version": chosen.format_version,
                "registration_residual_m": chosen.registration_residual_m,
                "coverage": chosen.coverage,
                "quality": chosen.quality,
                "superseded_versions": [v.version_id for v in versions[1:]],
            }
        )

    return {
        "selection_policy": SELECTION_POLICY,
        "assets": selected,
        "excluded": excluded,
    }
