"""Unit tests for platform primitives that need no database:
deterministic IDs, adapter normalization/fail-closed behavior, and release
manifest canonicalization."""

from __future__ import annotations

import json

import pytest

from openpali.adapters.base import AcquisitionRequest, OfflineInputError
from openpali.adapters.registry import county_parcels_adapter
from openpali.identity.ids import (
    acquisition_run_id,
    dataset_id,
    property_id_from_apn,
    record_version_id,
    release_id_from_manifest,
    snapshot_id_from_inputs,
)


class TestDeterministicIds:
    def test_property_id_stable_and_seeded(self):
        a = property_id_from_apn("4400001001")
        b = property_id_from_apn("4400001001")
        c = property_id_from_apn("4400001002")
        assert a == b
        assert a != c
        assert a.startswith("prop-")

    def test_record_version_id_content_derived(self):
        a = record_version_id("county_base", "4400001001", "aa" * 32)
        b = record_version_id("county_base", "4400001001", "bb" * 32)
        assert a != b and a.startswith("srv-")

    def test_snapshot_id_order_insensitive_inputs(self):
        policies = {"taxonomy": "taxonomy-v1"}
        a = snapshot_id_from_inputs(["run-b", "run-a"], policies, "2026-07-11T00:00:00+00:00", "civic-v1")
        b = snapshot_id_from_inputs(["run-a", "run-b"], policies, "2026-07-11T00:00:00+00:00", "civic-v1")
        assert a == b

    def test_snapshot_id_policy_sensitive(self):
        a = snapshot_id_from_inputs(["r"], {"taxonomy": "v1"}, "2026-07-11T00:00:00+00:00", "civic-v1")
        b = snapshot_id_from_inputs(["r"], {"taxonomy": "v2"}, "2026-07-11T00:00:00+00:00", "civic-v1")
        assert a != b

    def test_run_and_dataset_ids(self):
        assert acquisition_run_id("s", {"w": 1}, "t").startswith("run-")
        assert dataset_id("snap-x", "c", "t", "f", "cut").startswith("ds-")

    def test_release_id_excludes_envelope(self):
        manifest = {"kind": "fixture", "snapshot_id": "snap-1", "coverage": {"properties": 1}}
        base = release_id_from_manifest(manifest)
        with_envelope = release_id_from_manifest(
            {**manifest, "release_id": "rel-something", "built_at": "2026-07-11", "signatures": ["x"]}
        )
        assert base == with_envelope
        changed = release_id_from_manifest({**manifest, "coverage": {"properties": 2}})
        assert changed != base


class TestAdapterOffline:
    def test_offline_without_hashes_fails_immediately(self):
        adapter = county_parcels_adapter()
        with pytest.raises(OfflineInputError):
            adapter.acquire(AcquisitionRequest(online=False))

    def test_offline_constructs_no_network_client(self, monkeypatch):
        """The offline path must never touch httpx.Client."""

        import httpx

        def boom(*args, **kwargs):  # pragma: no cover - guard
            raise AssertionError("offline acquisition constructed a network client")

        monkeypatch.setattr(httpx, "Client", boom)
        adapter = county_parcels_adapter()
        with pytest.raises(OfflineInputError):
            adapter.acquire(AcquisitionRequest(online=False))


class TestAdapterNormalize:
    def _raw(self, features: list[dict]):
        from datetime import datetime, timezone

        from openpali.adapters.base import RawAcquisition, RawPage

        meta = {"fields": [{"name": "APN", "type": "esriFieldTypeString"}]}
        now = datetime.now(timezone.utc)
        pages = [
            RawPage(0, "meta", {}, json.dumps(meta).encode(), "m" * 64, now),
            RawPage(1, "q", {}, json.dumps({"features": features}).encode(), "p" * 64, now),
        ]
        return RawAcquisition(
            source_id="county_base",
            request=AcquisitionRequest(online=False, raw_page_hashes=(("m" * 64, 1), ("p" * 64, 1))),
            pages=pages,
            requested_at=now,
            retrieved_at=now,
            upstream_edited_at=None,
            record_count=len(features),
            schema_fingerprint="x",
        )

    def test_normalize_keys_on_normalized_apn(self):
        adapter = county_parcels_adapter()
        raw = self._raw(
            [
                {"attributes": {"APN": "4400-001-001"}, "geometry": {"type": "Polygon", "coordinates": []}},
                {"attributes": {"APN": "bad"}},
            ]
        )
        records = list(adapter.normalize(raw))
        assert len(records) == 1
        assert records[0].native_key == "4400001001"
        assert "_geometry" in records[0].payload
