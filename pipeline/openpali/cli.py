"""OpenPali operator CLI (`openpali ...`).

Commands compose the production services: acquisition, ledger load, snapshot
build, and release publication. They are safe to run inside the Compose job
services or from a developer shell with the documented environment variables.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from openpali.adapters.base import AcquisitionRequest
from openpali.adapters.registry import ADAPTERS
from openpali.ingestion.acquire import rehydrate, run_acquisition
from openpali.ingestion.load import load_county_records
from openpali.ingestion.snapshot import build_snapshot
from openpali.publication.release import PublicationGateError, publish_release
from openpali.storage.db import session_scope
from openpali.storage.models import AcquisitionRun
from openpali.storage.objects import ALL_BUCKETS, ObjectStore

LOADERS = {
    "county_base": load_county_records,
}


def cmd_bucket_init(args: argparse.Namespace) -> int:
    store = ObjectStore()
    for bucket in ALL_BUCKETS:
        store.ensure_bucket(bucket)
        print(f"bucket ready: {bucket}")
    return 0


def cmd_source_refresh(args: argparse.Namespace) -> int:
    source_id = args.source
    if source_id not in ADAPTERS:
        print(f"unknown source: {source_id}", file=sys.stderr)
        return 2
    adapter = ADAPTERS[source_id]()
    store = ObjectStore()
    with session_scope() as session:
        if args.replay_run:
            raw = rehydrate(session, store, adapter, args.replay_run)
            run_id = args.replay_run
            observed_at = raw.retrieved_at or raw.requested_at
        else:
            request = AcquisitionRequest(
                online=not args.offline,
                parameters={"where": adapter.where, "out_fields": adapter.out_fields},
            )
            result = run_acquisition(session, store, adapter, request)
            if result.status != "succeeded":
                print(f"acquisition FAILED: {result.error}", file=sys.stderr)
                return 3
            run_id = result.run_id
            raw = result.raw
            if raw is None:  # idempotent re-run: rehydrate from stored pages
                raw = rehydrate(session, store, adapter, run_id)
            observed_at = raw.retrieved_at or raw.requested_at
        print(f"acquisition run: {run_id} records={raw.record_count}")

        loader = LOADERS.get(source_id)
        if loader is None:
            print(f"(no ledger loader wired yet for {source_id}; acquisition only)")
            return 0
        records = list(adapter.normalize(raw))
        load_result = loader(session, records, run_id, observed_at=observed_at)
        run_row = session.execute(
            select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
        ).scalar_one()
        health = dict(run_row.health or {})
        health["load"] = {
            "records_seen": load_result.records_seen,
            "record_versions_new": load_result.record_versions_new,
            "observations_new": load_result.observations_new,
            "parcels_new": load_result.parcels_new,
            "parcels_superseded": load_result.parcels_superseded,
            "undocumented": load_result.undocumented,
        }
        run_row.health = health
        print(json.dumps(health["load"], indent=1))
        if load_result.undocumented:
            print("WARNING: undocumented taxonomy values present — publication will fail closed",
                  file=sys.stderr)
        print(f"RUN_ID={run_id}")
    return 0


def cmd_snapshot_build(args: argparse.Namespace) -> int:
    run_ids = [r.strip() for r in args.runs.split(",") if r.strip()]
    cutoff = (
        datetime.fromisoformat(args.cutoff)
        if args.cutoff
        else datetime.now(timezone.utc).replace(microsecond=0)
    )
    with session_scope() as session:
        result = build_snapshot(session, run_ids, cutoff)
        print(
            f"snapshot {result.snapshot_id} created={result.created} "
            f"properties={result.properties} observations={result.observations} "
            f"conflicts={result.conflicts}"
        )
        print(f"SNAPSHOT_ID={result.snapshot_id}")
    return 0


def cmd_release_publish(args: argparse.Namespace) -> int:
    store = ObjectStore()
    with session_scope() as session:
        # undocumented values frozen from the input runs' load health
        from openpali.storage.models import CivicSnapshot

        snapshot = session.execute(
            select(CivicSnapshot).where(CivicSnapshot.snapshot_id == args.snapshot)
        ).scalar_one()
        undocumented: list[str] = []
        for run_id in snapshot.input_runs:
            run_row = session.execute(
                select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
            ).scalar_one()
            undocumented.extend((run_row.health or {}).get("load", {}).get("undocumented", []))
        try:
            result = publish_release(
                session, store, args.snapshot, kind=args.kind,
                undocumented_values=sorted(set(undocumented)),
            )
        except PublicationGateError as exc:
            print(f"PUBLICATION BLOCKED: {exc}", file=sys.stderr)
            return 4
    print(
        f"release {result.release_id} status={result.status} mirror_ok={result.mirror_ok}"
    )
    print(json.dumps(result.gate_results, indent=1))
    print(f"RELEASE_ID={result.release_id}")
    return 0


def cmd_dev_slice(args: argparse.Namespace) -> int:
    """CP2 vertical slice: county acquisition -> ledger -> snapshot -> release.

    One fixed command so it can run as a Compose job service (`up -d
    slice-dev && wait slice-dev`).
    """

    adapter = ADAPTERS["county_base"]()
    store = ObjectStore()
    with session_scope() as session:
        request = AcquisitionRequest(
            online=not args.offline,
            parameters={"where": adapter.where, "out_fields": adapter.out_fields},
        )
        result = run_acquisition(session, store, adapter, request)
        if result.status != "succeeded":
            print(f"acquisition FAILED: {result.error}", file=sys.stderr)
            return 3
        raw = result.raw or rehydrate(session, store, adapter, result.run_id)
        observed_at = raw.retrieved_at or raw.requested_at
        records = list(adapter.normalize(raw))
        load_result = load_county_records(
            session, records, result.run_id, observed_at=observed_at
        )
        run_row = session.execute(
            select(AcquisitionRun).where(AcquisitionRun.run_id == result.run_id)
        ).scalar_one()
        health = dict(run_row.health or {})
        health["load"] = {
            "records_seen": load_result.records_seen,
            "record_versions_new": load_result.record_versions_new,
            "observations_new": load_result.observations_new,
            "parcels_new": load_result.parcels_new,
            "parcels_superseded": load_result.parcels_superseded,
            "undocumented": load_result.undocumented,
        }
        run_row.health = health
        print(f"acquired+loaded run {result.run_id}: {json.dumps(health['load'])}")

        snapshot_result = build_snapshot(
            session, [result.run_id], observed_at
        )
        print(
            f"snapshot {snapshot_result.snapshot_id} properties={snapshot_result.properties}"
        )
        try:
            release_result = publish_release(
                session, store, snapshot_result.snapshot_id, kind="dev",
                undocumented_values=load_result.undocumented,
            )
        except PublicationGateError as exc:
            print(f"PUBLICATION BLOCKED: {exc}", file=sys.stderr)
            return 4
    print(
        f"release {release_result.release_id} status={release_result.status} "
        f"mirror_ok={release_result.mirror_ok}"
    )
    print(f"RELEASE_ID={release_result.release_id}")
    return 0


def cmd_export_openapi(args: argparse.Namespace) -> int:
    from openpali.api.app import export_openapi

    sys.stdout.write(export_openapi())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openpali")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("bucket-init", help="create object-store buckets")
    p.set_defaults(func=cmd_bucket_init)

    p = sub.add_parser("source-refresh", help="acquire + load one source")
    p.add_argument("source", choices=sorted(ADAPTERS))
    p.add_argument("--offline", action="store_true",
                   help="offline replay (requires --replay-run)")
    p.add_argument("--replay-run", help="existing run id to replay from raw objects")
    p.set_defaults(func=cmd_source_refresh)

    p = sub.add_parser("snapshot-build", help="build an immutable snapshot")
    p.add_argument("--runs", required=True, help="comma-separated acquisition run ids")
    p.add_argument("--cutoff", help="ISO cutoff (default: now UTC)")
    p.set_defaults(func=cmd_snapshot_build)

    p = sub.add_parser("release-publish", help="gate + atomically promote a release")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--kind", default="fixture",
                   choices=["fixture", "representative", "dev"])
    p.set_defaults(func=cmd_release_publish)

    p = sub.add_parser("dev-slice", help="county acquisition -> snapshot -> release")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(func=cmd_dev_slice)

    p = sub.add_parser("refresh-all", help="all sources -> snapshot -> analytics -> release (direct)")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--kind", default="representative",
                   choices=["fixture", "representative", "dev"])
    p.set_defaults(func=cmd_refresh_all)

    p = sub.add_parser("orchestrate-deploy", help="register Prefect work pool + deployments")
    p.set_defaults(func=cmd_orchestrate_deploy)

    p = sub.add_parser("orchestrate-run", help="trigger a deployment and wait")
    p.add_argument("deployment", help="e.g. full-refresh-release/default")
    p.add_argument("--params", help="JSON parameters")
    p.add_argument("--timeout", type=float, default=3600)
    p.set_defaults(func=cmd_orchestrate_run)

    p = sub.add_parser("release-rollback", help="promote LKG back to current")
    p.set_defaults(func=cmd_release_rollback)

    p = sub.add_parser("replay", help="zero-network semantic replay of a release")
    p.add_argument("--release", default="current")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("export-openapi", help="print the OpenAPI schema")
    p.set_defaults(func=cmd_export_openapi)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())


def cmd_refresh_all(args: argparse.Namespace) -> int:
    """Direct (non-Prefect) full refresh -> snapshot -> analytics -> release."""

    from openpali.ingestion.pipeline import full_refresh
    from openpali.ingestion.snapshot import build_snapshot
    from openpali.metrics.compute import compute_all

    store = ObjectStore()
    with session_scope() as session:
        outcome = full_refresh(session, store, online=not args.offline)
        for result in outcome.results:
            print(f"  {result.source_id:18s} {result.status:9s} records={result.record_count}")
        if outcome.blocking_failures:
            print(f"BLOCKING FAILURES: {outcome.blocking_failures}", file=sys.stderr)
            return 3
        cutoff = datetime.now(timezone.utc).replace(microsecond=0)
        snapshot = build_snapshot(session, outcome.run_ids, cutoff)
        print(f"snapshot {snapshot.snapshot_id} properties={snapshot.properties} "
              f"observations={snapshot.observations} conflicts={snapshot.conflicts}")
        analytics = compute_all(session, snapshot.snapshot_id)
        print(f"analytics: {analytics['metrics']} metric values, "
              f"{analytics['reconciliations']} reconciliations")
        try:
            release = publish_release(
                session, store, snapshot.snapshot_id, kind=args.kind,
                undocumented_values=outcome.undocumented,
            )
        except PublicationGateError as exc:
            print(f"PUBLICATION BLOCKED: {exc}", file=sys.stderr)
            return 4
    print(f"release {release.release_id} mirror_ok={release.mirror_ok}")
    print(f"RELEASE_ID={release.release_id}")
    return 0


def cmd_orchestrate_deploy(args: argparse.Namespace) -> int:
    from openpali.orchestration.deploy import register_deployments

    registered = register_deployments()
    print(f"{len(registered)} deployments registered")
    return 0


def cmd_orchestrate_run(args: argparse.Namespace) -> int:
    """Trigger a registered deployment and wait for its terminal state."""

    from prefect.deployments import run_deployment

    parameters = json.loads(args.params) if args.params else {}
    flow_run = run_deployment(
        name=args.deployment, parameters=parameters,
        timeout=args.timeout,
    )
    state = flow_run.state
    print(f"flow_run {flow_run.id} state={state.name if state else 'UNKNOWN'}")
    if state is None or not state.is_completed():
        return 5
    return 0


def cmd_release_rollback(args: argparse.Namespace) -> int:
    """Atomically demote current and promote the last known good release."""

    from sqlalchemy import select as sa_select

    from openpali.identity.ids import canonical_json as cj
    from openpali.storage.models import CurrentRelease, Publication

    store = ObjectStore()
    with session_scope() as session:
        current = session.get(CurrentRelease, 1, with_for_update=True)
        if current is None or not current.lkg_release_id:
            print("no LKG release to roll back to", file=sys.stderr)
            return 6
        if current.current_release_id == current.lkg_release_id:
            print("current already equals LKG; nothing to do")
            return 0
        demoted = current.current_release_id
        promoted = current.lkg_release_id
        lkg_pub = session.execute(
            sa_select(Publication).where(Publication.release_id == promoted)
        ).scalar_one()
        if demoted:
            demoted_pub = session.execute(
                sa_select(Publication).where(Publication.release_id == demoted)
            ).scalar_one_or_none()
            if demoted_pub is not None:
                demoted_pub.status = "rolled_back"
        lkg_pub.status = "published"
        current.current_release_id = promoted
        current.lkg_release_id = demoted
        session.commit()
        manifest_sha = lkg_pub.manifest_sha256
    # repair the non-authoritative mirror afterwards
    try:
        pointer = cj({"release_id": promoted, "manifest_sha256": manifest_sha}).encode()
        from openpali.storage.objects import PUBLICATION_BUCKET

        store.put_manifest(PUBLICATION_BUCKET, "pointers/current.json", pointer)
        mirror_ok = True
    except Exception:  # noqa: BLE001
        mirror_ok = False
    print(f"rolled back: current={promoted} (was {demoted}) mirror_ok={mirror_ok}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    """Zero-network semantic replay of a release's exact raw hashes.

    Runs on the internal Compose network with NO proxy environment: the
    process is physically incapable of egress. Every raw page is re-read
    through digest+size verification; normalization and observation-ID
    derivation are recomputed in memory and compared against the release's
    stored membership.
    """

    from sqlalchemy import select as sa_select

    from palisades.apn import normalize_apn as _napn

    from openpali.domain.observations import SourceRecordRef as SRR
    from openpali.domain.policy import classify_permit
    from openpali.ingestion import normalize as norm
    from openpali.ingestion.load import _payload_sha
    from openpali.storage.models import (
        CurrentRelease,
        Publication,
        RecoveryObservationRow,
        SnapshotMember,
    )

    store = ObjectStore()
    failures: list[str] = []
    with session_scope() as session:
        if args.release == "current":
            current = session.get(CurrentRelease, 1)
            release_id = current.current_release_id if current else None
        else:
            release_id = args.release
        if not release_id:
            print("no release to replay", file=sys.stderr)
            return 6
        publication = session.execute(
            sa_select(Publication).where(Publication.release_id == release_id)
        ).scalar_one()
        manifest = publication.manifest
        input_runs = manifest["input_runs"]
        print(f"replaying release {release_id} ({len(input_runs)} input runs), "
              f"snapshot {publication.snapshot_id}")

        recomputed: set[str] = set()
        permit_classifications: dict[str, object] = {}
        permit_to_apn: dict[str, str] = {}

        ordered = sorted(input_runs, key=lambda rid: _replay_order(session, rid))
        for run_id in ordered:
            run_row = session.execute(
                sa_select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
            ).scalar_one()
            source_id = run_row.source_id
            adapter = ADAPTERS[source_id]()
            raw = rehydrate(session, store, adapter, run_id)  # digest-verified
            observed_at = raw.retrieved_at or raw.requested_at
            records = list(adapter.normalize(raw))
            if run_row.record_count is not None and len(records) != run_row.record_count:
                failures.append(
                    f"{source_id}: replayed {len(records)} records, "
                    f"acquisition recorded {run_row.record_count}"
                )

            if source_id == "county_base":
                for record in records:
                    normalized = norm.normalize_county_parcel(
                        record.payload, observed_at=observed_at,
                        source_record=SRR("county_base", record.native_key,
                                          _payload_sha(record.payload)),
                    )
                    recomputed.update(o.observation_id for o in normalized.observations)
            elif source_id == "ladbs_permits":
                for record in records:
                    payload = record.payload
                    permit_no = str(payload.get("PERMIT") or "").strip() or record.native_key
                    permit_classifications[permit_no] = classify_permit(
                        payload.get("PERMIT_TYPE"), payload.get("PALISADES_WF_REBUILD")
                    )
                    apn = _napn(payload.get("APN"))
                    if apn:
                        permit_to_apn[permit_no] = apn
                    normalized = norm.normalize_ladbs_permit(
                        payload, observed_at=observed_at,
                        source_record=SRR("ladbs_permits", permit_no, _payload_sha(payload)),
                    )
                    recomputed.update(o.observation_id for o in normalized.observations)
            elif source_id == "ladbs_inspections":
                for record in records:
                    payload = record.payload
                    normalized = norm.normalize_ladbs_inspection(
                        payload, observed_at=observed_at,
                        source_record=SRR(
                            "ladbs_inspections",
                            str(payload.get("PERMIT") or record.native_key),
                            _payload_sha(payload),
                        ),
                        permit_classifications=permit_classifications,
                        permit_to_apn=permit_to_apn,
                    )
                    recomputed.update(o.observation_id for o in normalized.observations)
            elif source_id == "malibu_dash":
                for record in records:
                    normalized = norm.normalize_malibu_marker(
                        record.payload, observed_at=observed_at,
                        source_record=SRR("malibu_dash", record.native_key,
                                          _payload_sha(record.payload)),
                    )
                    recomputed.update(o.observation_id for o in normalized.observations)
            elif source_id == "calfire_dins":
                for record in records:
                    payload = record.payload
                    global_id = str(payload.get("GLOBALID") or "").strip() or record.native_key
                    normalized = norm.normalize_dins_structure(
                        payload, observed_at=observed_at,
                        source_record=SRR("calfire_dins", global_id, _payload_sha(payload)),
                    )
                    recomputed.update(o.observation_id for o in normalized.observations)
            print(f"  replayed {source_id}: {len(records)} records "
                  f"({len(raw.pages)} verified raw pages)")

        # The replay guarantee: the release's exact raw bytes deterministically
        # reproduce every observation derived from them, and every reproduced
        # observation exists in the append-only ledger. Membership can also
        # contain assertions first observed in EARLIER acquisitions of the
        # same sources (each replayable from its own pages) — correct
        # bitemporality, reported but never a failure.
        source_ids = {
            session.execute(
                sa_select(AcquisitionRun.source_id).where(
                    AcquisitionRun.run_id == run_id
                )
            ).scalar_one()
            for run_id in input_runs
        }
        stored_all = set(
            session.execute(
                sa_select(RecoveryObservationRow.observation_id).where(
                    RecoveryObservationRow.source_id.in_(source_ids)
                )
            ).scalars()
        )
        member_ids = set(
            session.execute(
                sa_select(SnapshotMember.member_id).where(
                    SnapshotMember.snapshot_id == publication.snapshot_id,
                    SnapshotMember.member_type == "observation",
                )
            ).scalars()
        )
        derived_ids = set(
            session.execute(
                sa_select(RecoveryObservationRow.observation_id).where(
                    RecoveryObservationRow.observation_id.in_(member_ids),
                    RecoveryObservationRow.source_id == "openpali_conflict_detection",
                )
            ).scalars()
        )
        members = member_ids - derived_ids
        not_in_ledger = recomputed - stored_all
        members_reproduced = members & recomputed
        members_from_earlier_runs = members - recomputed - derived_ids
        print(f"recomputed observations: {len(recomputed)}; in ledger: "
              f"{len(recomputed & stored_all)}")
        print(f"membership (non-derived): {len(members)}; reproduced from this "
              f"release's bytes: {len(members_reproduced)}; from earlier "
              f"acquisitions of the same sources: {len(members_from_earlier_runs)}")
        if not_in_ledger:
            failures.append(
                f"{len(not_in_ledger)} recomputed observation IDs are NOT in the "
                f"ledger — raw bytes no longer reproduce stored semantics "
                f"(sample: {sorted(not_in_ledger)[:3]})"
            )

    if failures:
        print("REPLAY FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 7
    print("REPLAY OK: exact raw hashes reproduced the release's semantic observations")
    return 0


def _replay_order(session, run_id: str) -> int:
    from openpali.ingestion.pipeline import FULL_REFRESH_ORDER

    row = session.execute(
        select(AcquisitionRun).where(AcquisitionRun.run_id == run_id)
    ).scalar_one()
    try:
        return FULL_REFRESH_ORDER.index(row.source_id)
    except ValueError:
        return 99
