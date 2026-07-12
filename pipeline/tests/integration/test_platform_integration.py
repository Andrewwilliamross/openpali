"""Platform integration tests against REAL PostGIS + SeaweedFS (DATA-002).

These run inside the Compose `test-integration` job service (or any shell
with OPENPALI_INTEGRATION=1 and the documented env vars). They are skipped
elsewhere: a SQLite substitute cannot exercise geometry, JSONB, schemas, or
transactional promotion, so there is deliberately no fallback.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

#: Per-execution uniqueness: S3 writes are not transactional and the
#: publication test commits, so identifiers must not collide across reruns.
RUN_TAG = uuid.uuid4().hex[:10]


def _unique_apn(suffix: int) -> str:
    return f"44{int(RUN_TAG[:6], 16) % 10**6:06d}{suffix:02d}"

pytestmark = pytest.mark.skipif(
    os.environ.get("OPENPALI_INTEGRATION") != "1",
    reason="integration environment (real PostGIS + S3) not requested",
)

OBSERVED_T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
OBSERVED_T1 = datetime(2026, 7, 8, tzinfo=timezone.utc)


def _county_payload(apn: str, roe: str = "Final Sign Off - Complete", **extra) -> dict:
    payload = {
        "APN": apn,
        "LCITY": "Los Angeles",
        "DAMAGE": "Destroyed (>50%)",
        "ROE_STATUS": roe,
        "FSO_PKG_APPROVED_USACE": "22-MAR-25 09.37.30.000000 PM" if roe.startswith("Final Sign Off - C") else None,
        "REBUILD_PROGRESS": None,
        "CENTER_LON": -118.53,
        "CENTER_LAT": 34.04,
        "_geometry": {
            "type": "Polygon",
            "coordinates": [[[-118.531, 34.041], [-118.531, 34.042],
                             [-118.530, 34.042], [-118.530, 34.041],
                             [-118.531, 34.041]]],
        },
    }
    payload.update(extra)
    return payload


@pytest.fixture(scope="module")
def db_session_factory():
    from openpali.storage.db import get_engine, get_session_factory

    engine = get_engine()
    return get_session_factory(engine)


@pytest.fixture(scope="module")
def store():
    from openpali.storage.objects import ALL_BUCKETS, ObjectStore

    s = ObjectStore()
    for bucket in ALL_BUCKETS:
        s.ensure_bucket(bucket)
    return s


@pytest.fixture()
def session(db_session_factory):
    s = db_session_factory()
    yield s
    s.rollback()
    s.close()


def _fake_run(session, run_id: str, source_id: str = "county_base",
              retrieved_at: datetime = OBSERVED_T0):
    from openpali.ingestion.acquire import ensure_source
    from openpali.adapters.registry import county_parcels_adapter
    from openpali.storage.models import AcquisitionRun

    ensure_source(session, county_parcels_adapter())
    run = AcquisitionRun(
        run_id=run_id,
        source_id=source_id,
        parameters={},
        online=False,
        requested_at=retrieved_at,
        retrieved_at=retrieved_at,
        status="succeeded",
        record_count=0,
    )
    session.add(run)
    session.flush()
    return run


class TestObjectStoreIntegrity:
    def test_content_dedup_and_overwrite_rejection(self, store):
        from openpali.storage.objects import ObjectIntegrityError, RAW_BUCKET

        data = json.dumps({"probe": "integrity", "tag": RUN_TAG}).encode()
        import hashlib

        digest = hashlib.sha256(data).hexdigest()
        key = f"raw/test/{digest}.json"
        first = store.put_content(RAW_BUCKET, key, data)
        assert not first.deduplicated
        second = store.put_content(RAW_BUCKET, key, data)
        assert second.deduplicated
        with pytest.raises(ObjectIntegrityError):
            store.put_content(RAW_BUCKET, key, b'{"different": "bytes"}')
        assert store.get_verified(RAW_BUCKET, key, digest, len(data)) == data
        with pytest.raises(ObjectIntegrityError):
            store.get_verified(RAW_BUCKET, key, "0" * 64, len(data))


class TestLedgerIdempotencyAndPointInTime:
    def test_reload_creates_no_duplicates(self, session):
        from openpali.adapters.base import SourceRecord
        from openpali.ingestion.load import load_county_records
        from openpali.storage.models import RecoveryObservationRow
        from sqlalchemy import func, select

        run = _fake_run(session, f"run-int-idem-{RUN_TAG}")
        records = [SourceRecord(_unique_apn(1), _county_payload(_unique_apn(1)), 1)]
        first = load_county_records(session, records, run.run_id, observed_at=OBSERVED_T0)
        again = load_county_records(session, records, run.run_id, observed_at=OBSERVED_T0)
        assert first.observations_new > 0
        assert again.observations_new == 0
        assert again.record_versions_new == 0
        count = session.execute(
            select(func.count()).select_from(RecoveryObservationRow).where(
                RecoveryObservationRow.subject_id == _unique_apn(1)
            )
        ).scalar_one()
        assert count == first.observations_new

    def test_point_in_time_excludes_late_observations(self, session):
        from openpali.adapters.base import SourceRecord
        from openpali.ingestion.load import load_county_records
        from openpali.ingestion.snapshot import build_snapshot

        run0 = _fake_run(session, f"run-int-pit-0-{RUN_TAG}", retrieved_at=OBSERVED_T0)
        run1 = _fake_run(session, f"run-int-pit-1-{RUN_TAG}", retrieved_at=OBSERVED_T1)
        # T0: opt-out only; T1: government cleanup completion arrives later,
        # asserting an EARLIER occurrence — cutoff T0 must not see it.
        load_county_records(
            session,
            [SourceRecord(_unique_apn(2), _county_payload(_unique_apn(2), roe="Opt-Out and Manage Cleanup Independently"), 1)],
            run0.run_id,
            observed_at=OBSERVED_T0,
        )
        load_county_records(
            session,
            [SourceRecord(_unique_apn(2), _county_payload(_unique_apn(2)), 1)],
            run1.run_id,
            observed_at=OBSERVED_T1,
        )
        early = build_snapshot(session, [run0.run_id, run1.run_id], OBSERVED_T0 + timedelta(hours=1))
        late = build_snapshot(session, [run0.run_id, run1.run_id], OBSERVED_T1 + timedelta(hours=1))

        from openpali.identity.ids import property_id_from_apn
        from openpali.storage.models import SnapshotPropertyState
        from sqlalchemy import select

        pid = property_id_from_apn(_unique_apn(2))
        early_state = session.execute(
            select(SnapshotPropertyState).where(
                SnapshotPropertyState.snapshot_id == early.snapshot_id,
                SnapshotPropertyState.property_id == pid,
            )
        ).scalar_one()
        late_state = session.execute(
            select(SnapshotPropertyState).where(
                SnapshotPropertyState.snapshot_id == late.snapshot_id,
                SnapshotPropertyState.property_id == pid,
            )
        ).scalar_one()
        assert early_state.milestones["cleanup_complete"] is False
        assert late_state.milestones["cleanup_complete"] is True

    def test_snapshot_rebuild_is_noop(self, session):
        from openpali.adapters.base import SourceRecord
        from openpali.ingestion.load import load_county_records
        from openpali.ingestion.snapshot import build_snapshot

        run = _fake_run(session, f"run-int-noop-{RUN_TAG}")
        load_county_records(
            session,
            [SourceRecord(_unique_apn(3), _county_payload(_unique_apn(3)), 1)],
            run.run_id,
            observed_at=OBSERVED_T0,
        )
        cutoff = OBSERVED_T0 + timedelta(hours=2)
        first = build_snapshot(session, [run.run_id], cutoff)
        second = build_snapshot(session, [run.run_id], cutoff)
        assert first.snapshot_id == second.snapshot_id
        assert first.created and not second.created


class TestPublicationAuthority:
    def test_publish_and_gates(self, session, store):
        from openpali.adapters.base import SourceRecord
        from openpali.ingestion.load import load_county_records
        from openpali.ingestion.snapshot import build_snapshot
        from openpali.publication.release import PublicationGateError, publish_release
        from openpali.storage.models import CurrentRelease

        run = _fake_run(session, f"run-int-pub-{RUN_TAG}")
        load_county_records(
            session,
            [SourceRecord(_unique_apn(4), _county_payload(_unique_apn(4)), 1)],
            run.run_id,
            observed_at=OBSERVED_T0,
        )
        snap = build_snapshot(session, [run.run_id], OBSERVED_T0 + timedelta(hours=3))

        with pytest.raises(PublicationGateError):
            publish_release(
                session, store, snap.snapshot_id,
                undocumented_values=["Mystery Status"],
            )
        session.rollback()

        run = _fake_run(session, f"run-int-pub2-{RUN_TAG}")  # fresh run after rollback
        load_county_records(
            session,
            [SourceRecord(_unique_apn(4), _county_payload(_unique_apn(4)), 1)],
            run.run_id,
            observed_at=OBSERVED_T0,
        )
        snap = build_snapshot(session, [run.run_id], OBSERVED_T0 + timedelta(hours=3))
        result = publish_release(session, store, snap.snapshot_id)
        assert result.status == "published"
        current = session.get(CurrentRelease, 1)
        assert current.current_release_id == result.release_id
