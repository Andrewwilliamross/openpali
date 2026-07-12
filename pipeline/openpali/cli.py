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

    p = sub.add_parser("export-openapi", help="print the OpenAPI schema")
    p.set_defaults(func=cmd_export_openapi)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
