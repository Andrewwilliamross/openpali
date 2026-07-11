"""Provenance, expectation gates, and artifact-stamping contracts (ROADMAP PR1)."""

from __future__ import annotations

import hashlib
import json

import pytest

from palisades import checks, http, provenance
from palisades.emit import emit_all
from palisades.model import Parcel
from palisades.validate import reconcile


@pytest.fixture(autouse=True)
def _clean_registry():
    provenance.reset()
    yield
    provenance.reset()


# ---------- provenance ----------

def test_schema_fingerprint_deterministic_and_order_insensitive():
    a = provenance.schema_fingerprint([{"x": 1, "y": "s"}, {"x": 2, "y": None}])
    b = provenance.schema_fingerprint([{"y": None, "x": 9}, {"y": "t", "x": 0}])
    assert a == b and a is not None


def test_schema_fingerprint_changes_on_new_field_and_type_shift():
    base = provenance.schema_fingerprint([{"x": 1}])
    added = provenance.schema_fingerprint([{"x": 1, "z": 1}])
    retyped = provenance.schema_fingerprint([{"x": "1"}])
    assert len({base, added, retyped}) == 3


def test_schema_fingerprint_empty_is_none():
    assert provenance.schema_fingerprint([]) is None


def test_source_tagging_and_summarize_is_pagination_order_independent():
    with provenance.source("a"):
        provenance.add("u1", None, "page-one", fetched_at="2026-06-11T00:00:00+00:00", cache_hit=True)
        provenance.add("u2", None, "page-two", fetched_at="2026-06-11T00:00:01+00:00", cache_hit=False)
    provenance.add("u3", None, "other", fetched_at="2026-06-11T00:00:02+00:00", cache_hit=False)

    s = provenance.summarize("a")
    assert s["requests"] == 2 and s["cache_hits"] == 1
    assert s["bytes"] == len("page-one") + len("page-two")
    assert s["last_fetch"] == "2026-06-11T00:00:01+00:00"

    provenance.reset()
    with provenance.source("a"):  # same pages, reversed arrival order
        provenance.add("u2", None, "page-two", fetched_at="2026-06-11T00:00:01+00:00", cache_hit=False)
        provenance.add("u1", None, "page-one", fetched_at="2026-06-11T00:00:00+00:00", cache_hit=True)
    assert provenance.summarize("a")["sha256"] == s["sha256"]


def test_cached_get_json_records_provenance_on_miss_then_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(http, "RAW_DIR", tmp_path)
    monkeypatch.setattr(http, "_get", lambda url, params: {"a": 1})

    with provenance.source("probe"):
        http.cached_get_json("https://x.test/q", {"w": 1}, ttl_hours=12, sleep=0)
        http.cached_get_json("https://x.test/q", {"w": 1}, ttl_hours=12, sleep=0)

    recs = provenance.records("probe")
    assert [r.cache_hit for r in recs] == [False, True]
    assert recs[0].sha256 == recs[1].sha256  # identical canonical bytes
    assert recs[0].bytes == len(json.dumps({"a": 1}))
    assert all(r.fetched_at for r in recs)


# ---------- expectation gates ----------

def _health(sid="county_base", **kv):
    h = {"id": sid, "ok": True, "records": 1000}
    h.update(kv)
    return h


def _recon_ok():
    return [{"source": "LADBS", "metric": "m", "official": 100, "ours": 100,
             "drift_pct": 0.0, "ok": True}]


def test_gates_clean_run_has_no_incidents():
    out = checks.run_gates([Parcel("1")], [_health()], _recon_ok())
    assert out == []


def test_gate_universe_empty_is_error():
    out = checks.run_gates([], [_health()], _recon_ok())
    assert checks.has_errors(out) and out[0]["code"] == "universe_empty"


def test_gate_apn_parse_rate():
    out = checks.run_gates([Parcel("1")], [_health(unparseable=20)], _recon_ok())
    assert any(i["code"] == "apn_parse_rate" and i["level"] == "error" for i in out)
    out = checks.run_gates([Parcel("1")], [_health(unparseable=5)], _recon_ok())
    assert not any(i["code"] == "apn_parse_rate" for i in out)


def test_gate_duplicates_error_vs_info():
    err = checks.run_gates([Parcel("1")], [_health(duplicates=30)], _recon_ok())
    assert any(i["code"] == "duplicate_apns" and i["level"] == "error" for i in err)
    info = checks.run_gates([Parcel("1")], [_health(duplicates=3)], _recon_ok())
    assert any(i["code"] == "duplicate_apns" and i["level"] == "info" for i in info)
    assert not checks.has_errors(info)


def test_gate_missing_geometry_warns():
    out = checks.run_gates([Parcel("1")], [_health(no_geometry=2)], _recon_ok())
    assert any(i["code"] == "missing_geometry" and i["level"] == "warn" for i in out)


def test_gate_source_failed_warns():
    out = checks.run_gates(
        [Parcel("1")], [_health(), _health(sid="malibu_dash", ok=False, error="boom", records=0)],
        _recon_ok())
    assert any(i["code"] == "source_failed" and "malibu_dash" in i["message"] for i in out)


def test_gate_stage_taxonomy_error():
    p = Parcel("1")
    p.stage = 7
    out = checks.run_gates([p], [_health()], _recon_ok())
    assert any(i["code"] == "stage_taxonomy" and i["level"] == "error" for i in out)


def test_gate_unknown_labels_warn():
    out = checks.run_gates(
        [Parcel("1")], [_health(unknown_labels=["mystery phase"])], _recon_ok())
    assert any(i["code"] == "label_taxonomy" for i in out)


def test_gate_universe_delta():
    prev = {"totals": {"destroyed": 1000}}
    shrunk = checks.run_gates([Parcel(str(i)) for i in range(900)], [_health()], _recon_ok(), prev)
    assert any(i["code"] == "universe_shrank" and i["level"] == "error" for i in shrunk)
    moved = checks.run_gates([Parcel(str(i)) for i in range(999)], [_health()], _recon_ok(), prev)
    assert any(i["code"] == "universe_changed" and i["level"] == "info" for i in moved)


def test_gate_reconciliation_missing_and_drift():
    missing = checks.run_gates([Parcel("1")], [_health()], [])
    assert any(i["code"] == "reconciliation_unavailable" for i in missing)
    drift = checks.run_gates(
        [Parcel("1")], [_health()],
        [{"metric": "m", "official": 100, "ours": 80, "drift_pct": 20.0, "ok": False}])
    assert any(i["code"] == "official_drift" and i["level"] == "warn" for i in drift)


def test_gate_schema_drift_vs_previous_meta():
    prev_meta = {"sources": [{"id": "county_base", "schema_fingerprint": "aaaa"}]}
    out = checks.run_gates(
        [Parcel("1")], [_health(schema_fingerprint="bbbb")], _recon_ok(), None, prev_meta)
    assert any(i["code"] == "schema_drift" for i in out)
    same = checks.run_gates(
        [Parcel("1")], [_health(schema_fingerprint="aaaa")], _recon_ok(), None, prev_meta)
    assert not any(i["code"] == "schema_drift" for i in same)


# ---------- artifact stamping ----------

def _parcel(apn: str) -> Parcel:
    return Parcel(apn=apn, address="1 TEST ST",
                  geometry={"type": "Polygon",
                            "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]})


def test_emit_stamps_one_snapshot_across_all_artifacts(tmp_path):
    incidents = [{"level": "warn", "code": "x", "message": "y"}]
    res = emit_all([_parcel("4400000001"), _parcel("4400000002")],
                   baselines=_recon_ok(), source_meta=[_health()], incidents=incidents,
                   run_id="cafe00000001", snapshot_id="20260611T000000Z-cafe00",
                   out_dir=tmp_path)
    assert res["snapshot_id"] == "20260611T000000Z-cafe00"

    pg = json.loads((tmp_path / "parcels.geojson").read_bytes())
    dt = json.loads((tmp_path / "details.json").read_bytes())
    sm = json.loads((tmp_path / "summary.json").read_text())
    mt = json.loads((tmp_path / "meta.json").read_text())

    assert pg["snapshot_id"] == dt["_snapshot_id"] == sm["snapshot_id"] == mt["snapshot_id"]
    assert mt["run_id"] == "cafe00000001"
    assert sm["baselines"] == _recon_ok()
    assert mt["incidents"] == incidents
    assert mt["sources"] == [_health()]
    # artifact hashes in meta must match the bytes actually on disk
    for name in ("parcels.geojson", "details.json", "summary.json"):
        assert mt["artifacts"][name] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    # details parcels untouched by the stamp key
    assert set(dt) == {"4400000001", "4400000002", "_snapshot_id"}


# ---------- reconcile math ----------

def test_reconcile_flags_drift_over_5pct():
    parcels = [{"apn": "1", "jurisdiction": "LA", "stage": 3},
               {"apn": "2", "jurisdiction": "LA", "stage": 2},
               {"apn": "3", "jurisdiction": "MALIBU", "stage": 0}]
    rows = reconcile(parcels, [
        {"source": "LA County", "metric": "destroyed_parcels", "official": 3},
        {"source": "LADBS", "metric": "parcels_bldgnew_application", "official": 4},
    ])
    by = {r["metric"]: r for r in rows}
    assert by["destroyed_parcels"]["ok"] and by["destroyed_parcels"]["drift_pct"] == 0.0
    assert by["parcels_bldgnew_application"]["ours"] == 2
    assert not by["parcels_bldgnew_application"]["ok"]  # 50% drift
