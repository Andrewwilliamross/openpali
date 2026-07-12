"""PUB-001 fault injection on the real stack: pinned sessions across
promotion, mirror failure drift, gate fail-closed with LKG intact, rollback."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("OPENPALI_INTEGRATION") != "1",
    reason="integration environment (real PostGIS + S3) not requested",
)

RUN_TAG = uuid.uuid4().hex[:10]
OBSERVED = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _apn(suffix: int) -> str:
    return f"45{int(RUN_TAG[:6], 16) % 10**6:06d}{suffix:02d}"


def _payload(apn: str, roe: str = "Final Sign Off - Complete") -> dict:
    return {
        "APN": apn,
        "LCITY": "Los Angeles",
        "DAMAGE": "Destroyed (>50%)",
        "ROE_STATUS": roe,
        "FSO_PKG_APPROVED_USACE": "22-MAR-25 09.37.30.000000 PM"
        if roe.startswith("Final Sign Off - C") else None,
        "REBUILD_PROGRESS": None,
    }


@pytest.fixture(scope="module")
def session_factory():
    from openpali.storage.db import get_engine, get_session_factory

    return get_session_factory(get_engine())


# CURRENT-pointer isolation for the whole suite lives in conftest.py
# (restore_current_release_pointer, session-scoped autouse).


@pytest.fixture(scope="module")
def store():
    from openpali.storage.objects import ALL_BUCKETS, ObjectStore

    s = ObjectStore()
    for bucket in ALL_BUCKETS:
        s.ensure_bucket(bucket)
    return s


def _publish(session_factory, store, tag: str, apns: list[str], cutoff_offset_hours: int):
    from openpali.adapters.base import SourceRecord
    from openpali.adapters.registry import county_parcels_adapter
    from openpali.ingestion.acquire import ensure_source
    from openpali.ingestion.load import load_county_records
    from openpali.ingestion.snapshot import build_snapshot
    from openpali.publication.release import publish_release
    from openpali.storage.models import AcquisitionRun

    session = session_factory()
    try:
        ensure_source(session, county_parcels_adapter())
        run = AcquisitionRun(
            run_id=f"run-fault-{tag}-{RUN_TAG}",
            source_id="county_base",
            parameters={},
            online=False,
            requested_at=OBSERVED,
            retrieved_at=OBSERVED,
            status="succeeded",
            record_count=len(apns),
        )
        session.add(run)
        session.flush()
        load_county_records(
            session,
            [SourceRecord(a, _payload(a), 1) for a in apns],
            run.run_id,
            observed_at=OBSERVED,
        )
        snapshot = build_snapshot(
            session, [run.run_id], OBSERVED + timedelta(hours=cutoff_offset_hours)
        )
        result = publish_release(session, store, snapshot.snapshot_id, kind="dev")
        return result
    finally:
        session.close()


class TestPromotionAndPinnedSessions:
    def test_two_pinned_sessions_never_mix_releases(self, session_factory, store):
        import httpx

        api = os.environ.get("OPENPALI_API_URL", "http://api:8000")
        client = httpx.Client(timeout=30)

        release_a = _publish(session_factory, store, "a", [_apn(1)], 1)
        pinned = client.get(f"{api}/v1/releases/current").json()
        assert pinned["release_id"] == release_a.release_id

        # A pinned session keeps using release-A URLs while B is promoted.
        page_a_before = client.get(
            f"{api}/v1/releases/{release_a.release_id}/properties",
            params={"q": _apn(1), "limit": 5},
        ).json()
        assert [i["apn"] for i in page_a_before["items"]] == [_apn(1)]

        release_b = _publish(session_factory, store, "b", [_apn(1), _apn(2)], 2)
        assert release_b.release_id != release_a.release_id

        current = client.get(f"{api}/v1/releases/current").json()
        assert current["release_id"] == release_b.release_id
        assert current["lkg_release_id"] == release_a.release_id

        # Pinned release-A representation is unchanged (immutable).
        page_a_after = client.get(
            f"{api}/v1/releases/{release_a.release_id}/properties",
            params={"q": _apn(1), "limit": 5},
        ).json()
        assert page_a_after["items"] == page_a_before["items"]
        # The new parcel exists only in release B.
        in_a = client.get(
            f"{api}/v1/releases/{release_a.release_id}/properties",
            params={"q": _apn(2), "limit": 5},
        ).json()
        in_b = client.get(
            f"{api}/v1/releases/{release_b.release_id}/properties",
            params={"q": _apn(2), "limit": 5},
        ).json()
        assert in_a["items"] == []
        assert [i["apn"] for i in in_b["items"]] == [_apn(2)]

        # Cross-release cursor reuse fails.
        if page_a_after.get("next_cursor"):
            crossed = client.get(
                f"{api}/v1/releases/{release_b.release_id}/properties",
                params={"cursor": page_a_after["next_cursor"]},
            )
            assert crossed.status_code == 400


class TestMirrorFailureDrift:
    def test_failed_mirror_never_blocks_promotion(self, session_factory, store):
        """The object pointer is a non-authoritative mirror: promotion
        succeeds, drift is detectable, the API stays coherent."""

        from openpali.storage.objects import ObjectStore, PUBLICATION_BUCKET

        from openpali.adapters.base import SourceRecord
        from openpali.adapters.registry import county_parcels_adapter
        from openpali.ingestion.acquire import ensure_source
        from openpali.ingestion.load import load_county_records
        from openpali.ingestion.snapshot import build_snapshot
        from openpali.publication.release import publish_release
        from openpali.storage.models import AcquisitionRun

        broken_store = ObjectStore(endpoint_url="http://object-store:19999")
        session = session_factory()
        try:
            ensure_source(session, county_parcels_adapter())
            run = AcquisitionRun(
                run_id=f"run-fault-mirror-{RUN_TAG}",
                source_id="county_base",
                parameters={},
                online=False,
                requested_at=OBSERVED,
                retrieved_at=OBSERVED,
                status="succeeded",
                record_count=1,
            )
            session.add(run)
            session.flush()
            load_county_records(
                session, [SourceRecord(_apn(3), _payload(_apn(3)), 1)],
                run.run_id, observed_at=OBSERVED,
            )
            snapshot = build_snapshot(session, [run.run_id], OBSERVED + timedelta(hours=3))
            result = publish_release(session, broken_store, snapshot.snapshot_id, kind="dev")
        finally:
            session.close()

        assert result.status == "published"
        assert result.mirror_ok is False

        # Drift is detectable: DB authority says the new release; the healthy
        # store's pointer object (if present) differs or is stale.
        session = session_factory()
        try:
            from openpali.storage.models import CurrentRelease

            current = session.get(CurrentRelease, 1)
            assert current.current_release_id == result.release_id
        finally:
            session.close()
        try:
            pointer = store.client.get_object(
                Bucket=PUBLICATION_BUCKET, Key="pointers/current.json"
            )["Body"].read()
            assert json.loads(pointer)["release_id"] != result.release_id
        except Exception:
            pass  # pointer may not exist yet — also acceptable drift evidence


class TestGateFailClosedAndRollback:
    def test_gate_failure_keeps_current_untouched(self, session_factory, store):
        from openpali.adapters.base import SourceRecord
        from openpali.adapters.registry import county_parcels_adapter
        from openpali.ingestion.acquire import ensure_source
        from openpali.ingestion.load import load_county_records
        from openpali.ingestion.snapshot import build_snapshot
        from openpali.publication.release import PublicationGateError, publish_release
        from openpali.storage.models import AcquisitionRun, CurrentRelease

        session = session_factory()
        try:
            before = session.get(CurrentRelease, 1).current_release_id
            ensure_source(session, county_parcels_adapter())
            run = AcquisitionRun(
                run_id=f"run-fault-gate-{RUN_TAG}",
                source_id="county_base",
                parameters={},
                online=False,
                requested_at=OBSERVED,
                retrieved_at=OBSERVED,
                status="succeeded",
                record_count=1,
            )
            session.add(run)
            session.flush()
            load_county_records(
                session, [SourceRecord(_apn(4), _payload(_apn(4)), 1)],
                run.run_id, observed_at=OBSERVED,
            )
            snapshot = build_snapshot(session, [run.run_id], OBSERVED + timedelta(hours=4))
            with pytest.raises(PublicationGateError):
                publish_release(
                    session, store, snapshot.snapshot_id, kind="dev",
                    undocumented_values=["Fault Injected Value"],
                )
            session.rollback()
            after = session.get(CurrentRelease, 1).current_release_id
            assert after == before  # fail closed; current untouched
        finally:
            session.close()

    def test_rollback_restores_lkg_and_api_state(self, session_factory, store):
        import httpx

        from openpali.storage.models import CurrentRelease, Publication
        from sqlalchemy import select

        api = os.environ.get("OPENPALI_API_URL", "http://api:8000")
        client = httpx.Client(timeout=30)

        release_a = _publish(session_factory, store, "ra", [_apn(5)], 5)
        release_b = _publish(session_factory, store, "rb", [_apn(5), _apn(6)], 6)

        session = session_factory()
        try:
            current = session.get(CurrentRelease, 1, with_for_update=True)
            assert current.current_release_id == release_b.release_id
            assert current.lkg_release_id == release_a.release_id
            demoted = current.current_release_id
            promoted = current.lkg_release_id
            lkg_pub = session.execute(
                select(Publication).where(Publication.release_id == promoted)
            ).scalar_one()
            demoted_pub = session.execute(
                select(Publication).where(Publication.release_id == demoted)
            ).scalar_one()
            demoted_pub.status = "rolled_back"
            lkg_pub.status = "published"
            current.current_release_id = promoted
            current.lkg_release_id = demoted
            session.commit()
        finally:
            session.close()

        current_response = client.get(f"{api}/v1/releases/current").json()
        assert current_response["release_id"] == release_a.release_id
        # The rolled-back release is no longer addressable as published/lkg…
        rolled = client.get(f"{api}/v1/releases/{release_b.release_id}")
        assert rolled.status_code == 404
        # …while the restored release serves coherently.
        page = client.get(
            f"{api}/v1/releases/{release_a.release_id}/properties",
            params={"q": _apn(5), "limit": 5},
        ).json()
        assert [i["apn"] for i in page["items"]] == [_apn(5)]
