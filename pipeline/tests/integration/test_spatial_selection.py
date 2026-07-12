"""Spatial asset selection integration tests (SPATIAL-001).

Two-epoch discipline: with two vintage slots for the same subject/kind, a
release selects exactly one nonempty version PER SLOT (explicit comparison
vintages, no accidental epoch concatenation); within a slot, a newer version
supersedes the older (no stale tiles); empty enabled slots refuse; synthetic
and rights-unresolved assets are barred from public manifests with recorded
reasons.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("OPENPALI_INTEGRATION") != "1",
    reason="integration environment (real PostGIS + S3) not requested",
)

RUN_TAG = uuid.uuid4().hex[:10]
T0 = datetime(2025, 1, 21, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    from openpali.storage.db import get_session_factory

    s = get_session_factory()()
    try:
        yield s
        s.rollback()
    finally:
        s.close()


def _register(session, *, slot: str, version: str, processed_at: datetime,
              rights: str = "public_domain", subject_type: str = "aoi",
              content_units: int = 10, status: str = "ready") -> None:
    from openpali.spatial.registry import register_asset_version

    register_asset_version(
        session,
        asset_id=f"test-{RUN_TAG}-{slot}",
        version_id=version,
        subject_type=subject_type,
        subject_id=f"subj-{RUN_TAG}",
        asset_kind="surfel_tiles",
        vintage_slot=slot,
        source_id="test_source",
        observation_kind="post_fire_observation",
        rights_state=rights,
        acquisition_start=T0,
        acquisition_end=T0 + timedelta(hours=6),
        processed_at=processed_at,
        quality={"content_units": content_units},
        object_uri=f"s3://test/{version}/manifest.json",
        object_sha256="0" * 64,
        format_version="test-v1",
        status=status,
    )


def _mine(selection: dict) -> list[dict]:
    return [a for a in selection["assets"] if RUN_TAG in a["asset_id"]]


def test_two_epoch_slots_select_one_version_each(session):
    from openpali.spatial.registry import select_release_assets

    now = datetime.now(timezone.utc)
    # slot A: two versions -> newest wins, older listed as superseded
    _register(session, slot=f"epochA-{RUN_TAG}", version="v-old",
              processed_at=now - timedelta(days=2))
    _register(session, slot=f"epochA-{RUN_TAG}", version="v-new", processed_at=now)
    # slot B: an explicit comparison vintage, independent of slot A
    _register(session, slot=f"epochB-{RUN_TAG}", version="v-b", processed_at=now)

    selected = _mine(select_release_assets(session))
    by_slot = {a["vintage_slot"]: a for a in selected}
    assert set(by_slot) == {f"epochA-{RUN_TAG}", f"epochB-{RUN_TAG}"}
    slot_a = by_slot[f"epochA-{RUN_TAG}"]
    assert slot_a["version_id"] == "v-new"
    assert slot_a["superseded_versions"] == ["v-old"]
    assert by_slot[f"epochB-{RUN_TAG}"]["version_id"] == "v-b"
    # acquisition survives into the manifest entry (never processing time)
    assert slot_a["acquisition_start"].startswith("2025-01-21")


def test_empty_enabled_slot_refuses(session):
    from openpali.spatial.registry import EmptySlotError, select_release_assets

    _register(session, slot=f"empty-{RUN_TAG}", version="v-empty",
              processed_at=datetime.now(timezone.utc), content_units=0)
    with pytest.raises(EmptySlotError):
        select_release_assets(session)


def test_synthetic_and_unresolved_rights_are_barred(session):
    from openpali.spatial.registry import select_release_assets

    now = datetime.now(timezone.utc)
    _register(session, slot=f"synth-{RUN_TAG}", version="v-s",
              processed_at=now, rights="synthetic_fixture", subject_type="fixture")
    _register(session, slot=f"prop-{RUN_TAG}", version="v-p",
              processed_at=now, rights="unresolved")

    selection = select_release_assets(session, release_kind="representative")
    assert not _mine(selection)
    reasons = {
        e["asset_id"]: e["reason"]
        for e in selection["excluded"]
        if RUN_TAG in e["asset_id"]
    }
    assert any("synthetic" in r for r in reasons.values())
    assert any("rights_state=unresolved" in r for r in reasons.values())

    # the SAME synthetic asset is allowed in a fixture-kind release
    fixture_sel = select_release_assets(session, release_kind="fixture")
    assert any(a["version_id"] == "v-s" for a in _mine(fixture_sel))


def test_live_usgs_assets_reconcile_coverage(session):
    """Coverage reconciliation on the REAL registered USGS assets."""

    from sqlalchemy import select as sa_select

    from openpali.storage.models import SpatialAsset

    rows = list(
        session.execute(
            sa_select(SpatialAsset).where(
                SpatialAsset.asset_id == "usgs-surfel-aoi",
                SpatialAsset.status == "ready",
            )
        ).scalars()
    )
    if not rows:
        pytest.skip("USGS derivation has not run in this database")
    newest = max(rows, key=lambda a: a.processed_at or a.ingested_at)
    coverage = newest.coverage or {}
    assert coverage["parcels_with_dem_coverage"] >= 25
    assert coverage["destroyed_parcels_in_aoi"] >= 25
    assert 0 < coverage["coverage_fraction"] <= 1
    # observation kind + acquisition discipline
    assert newest.observation_kind == "post_fire_observation"
    assert newest.acquisition_start.date().isoformat() == "2025-01-21"
    assert newest.processed_at > newest.acquisition_end
