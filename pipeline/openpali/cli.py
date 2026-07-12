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
                promote=not getattr(args, "no_promote", False),
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
    p.add_argument("--no-promote", action="store_true",
                   help="publish release-qualified without moving the current "
                        "pointer (required for fixture releases)")
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

    p = sub.add_parser("ml-dataset", help="build the point-in-time dataset for a snapshot")
    p.add_argument("--snapshot", default="current")
    p.set_defaults(func=cmd_ml_dataset)

    p = sub.add_parser("ml-experiments", help="run baseline+challenger experiments")
    p.add_argument("--dataset", required=True)
    p.add_argument("--final", action="store_true",
                   help="the ONE final-holdout evaluation (spec frozen beforehand)")
    p.set_defaults(func=cmd_ml_experiments)

    p = sub.add_parser("ml-promote", help="manual champion promotion (gated)")
    p.add_argument("--model", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--decision", default="promoted", choices=["promoted", "rejected"])
    p.add_argument("--reason", required=True)
    p.add_argument("--evaluate-only", action="store_true")
    p.set_defaults(func=cmd_ml_promote)

    p = sub.add_parser("ml-serve", help="build the snapshot-bound batch prediction set")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--dataset", required=True)
    p.set_defaults(func=cmd_ml_serve)

    p = sub.add_parser("ml-drill", help="temporal fixture + N->N+1 drill (full challenger path)")
    p.add_argument("--reviewer", default="drill-independent-reviewer")
    p.set_defaults(func=cmd_ml_drill)

    p = sub.add_parser("spatial-acquire", help="acquire the frozen USGS AOI DEM tiles")
    p.add_argument("--offline", action="store_true", help="replay from stored raw bytes")
    p.set_defaults(func=cmd_spatial_acquire)

    p = sub.add_parser("spatial-derive", help="derive surfel tileset + terrain from raw DEM")
    p.set_defaults(func=cmd_spatial_derive)

    p = sub.add_parser("spatial-register-prefire",
                       help="register the tracked LARIAC corpus (rights unresolved)")
    p.set_defaults(func=cmd_spatial_register_prefire)

    p = sub.add_parser("recon-drill", help="two-view reconstruction fixture + review drill")
    p.set_defaults(func=cmd_recon_drill)

    p = sub.add_parser("recon-gpu-probe", help="typed GPU worker hardware boundary")
    p.set_defaults(func=cmd_recon_gpu_probe)

    p = sub.add_parser("schedule-drill", help="prove scheduler-created runs execute")
    p.set_defaults(func=cmd_schedule_drill)

    p = sub.add_parser("flow-reap", help="mark zombie Running flow runs Crashed")
    p.set_defaults(func=cmd_flow_reap)

    p = sub.add_parser("restore-verify", help="object/API half of the restore drill")
    p.set_defaults(func=cmd_restore_verify)

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


def cmd_ml_dataset(args: argparse.Namespace) -> int:
    from openpali.ml.dataset import build_dataset
    from openpali.storage.models import CurrentRelease, Publication

    store = ObjectStore()
    with session_scope() as session:
        snapshot_id = args.snapshot
        if snapshot_id == "current":
            current = session.get(CurrentRelease, 1)
            publication = session.execute(
                select(Publication).where(
                    Publication.release_id == current.current_release_id
                )
            ).scalar_one()
            snapshot_id = publication.snapshot_id
        result = build_dataset(session, store, snapshot_id)
        print(json.dumps({
            "dataset_id": result.dataset_id,
            "rows": result.row_count,
            "events": result.events,
            "censored": result.censored,
            "excluded_missing_submission": result.excluded_missing_submission,
            "gate": result.gate,
            "availability": result.availability,
            "object_sha256": result.object_sha256,
            "created": result.created,
        }, indent=1))
        print(f"DATASET_ID={result.dataset_id}")
    return 0


def cmd_ml_experiments(args: argparse.Namespace) -> int:
    from openpali.ml.experiments import run_experiments

    store = ObjectStore()
    with session_scope() as session:
        outcome = run_experiments(
            session, store, args.dataset,
            include_final_holdout=args.final,
        )
        print(f"gate_passed={outcome.gate_passed} challenger={outcome.challenger_status}")
        for run in outcome.runs:
            printable = {k: (round(v, 5) if isinstance(v, float) else v)
                         for k, v in run.metrics.items() if v is not None}
            print(f"  {run.name:16s} mlflow={run.mlflow_run_id} {json.dumps(printable)}")
        if outcome.model_id:
            print(f"MODEL_ID={outcome.model_id}")
        print(f"CHALLENGER_STATUS={outcome.challenger_status}")
    return 0


def cmd_ml_promote(args: argparse.Namespace) -> int:
    from openpali.ml.registry import evaluate_gates, record_promotion
    from openpali.storage.models import ModelVersion

    with session_scope() as session:
        if args.evaluate_only:
            model = session.execute(
                select(ModelVersion).where(ModelVersion.model_id == args.model)
            ).scalar_one()
            gates = evaluate_gates(session, model.experiment_run_id)
            print(json.dumps(gates, indent=1))
            return 0 if gates.get("passed") else 4
        try:
            row = record_promotion(
                session,
                model_id=args.model,
                reviewer=args.reviewer,
                decision=args.decision,
                reason=args.reason,
            )
        except ValueError as exc:
            print(f"PROMOTION REFUSED: {exc}", file=sys.stderr)
            return 4
        print(f"decision {row.decision_id}: {row.decision} by {row.reviewer}")
        print(json.dumps(row.gate_metrics, indent=1))
    return 0


def cmd_ml_serve(args: argparse.Namespace) -> int:
    from openpali.ml.serving import build_prediction_set

    store = ObjectStore()
    with session_scope() as session:
        result = build_prediction_set(session, store, args.snapshot, args.dataset)
        print(json.dumps({
            "prediction_set_id": result.prediction_set_id,
            "status": result.status,
            "rows": result.rows,
            "model_id": result.model_id,
            "insufficiency_reason": result.insufficiency_reason,
        }, indent=1))
    return 0


def cmd_ml_drill(args: argparse.Namespace) -> int:
    """Temporal fixture + full challenger path + the N -> N+1 drill (ML-003)."""

    from openpali.ml.dataset import build_dataset
    from openpali.ml.experiments import run_experiments
    from openpali.ml.fixture import build_fixture_ledger
    from openpali.ml.registry import record_promotion
    from openpali.ml.serving import build_prediction_set, current_champion

    store = ObjectStore()
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append((name, passed, detail))
        print(f"  [{'PASS' if passed else 'FAIL'}] {name} {detail}")

    with session_scope() as session:
        print("== resetting prior fixture state ==")
        from openpali.ml.fixture import reset_fixture

        reset_fixture(session)
        print("== building temporal fixture ledger (staggered observed_at) ==")
        fixture_result = build_fixture_ledger(session, store)
        print(f"snapshot N   = {fixture_result.snapshot_n}")
        print(f"snapshot N+1 = {fixture_result.snapshot_n1}")

        print("== dataset N ==")
        ds_n = build_dataset(session, store, fixture_result.snapshot_n)
        print(f"  rows={ds_n.row_count} events={ds_n.events} gate={ds_n.gate['passed']}")
        check("history gate passes on staggered fixture", ds_n.gate["passed"],
              f"(dates={ds_n.gate['distinct_acquisition_dates']}, span={ds_n.gate['span_days']}d, coverage={ds_n.gate['origin_feature_coverage']})")

        if not ds_n.gate["passed"] or not ds_n.object_sha256:
            print("drill cannot proceed: fixture dataset empty or gate failed",
                  file=sys.stderr)
            return 5

        # byte-identical rebuild of N
        ds_n_again = build_dataset(session, store, fixture_result.snapshot_n)
        check("N dataset rebuild is byte-identical",
              ds_n_again.object_sha256 == ds_n.object_sha256 and not ds_n_again.created,
              f"sha={ds_n.object_sha256[:12]}")

        print("== dataset N+1 (late arrival + retraction) ==")
        ds_n1 = build_dataset(session, store, fixture_result.snapshot_n1)
        check("N+1 dataset hash differs", ds_n1.object_sha256 != ds_n.object_sha256,
              f"{ds_n.object_sha256[:10]} -> {ds_n1.object_sha256[:10]}")
        # N+1 gains the EXPLICIT late-arriving application plus any submission
        # whose first observation naturally falls in the month-12 acquisition
        # (fixture-v3 submissions continue past the N window) — bitemporal
        # arrival is by observation time, never occurrence time
        from openpali.ml.dataset import load_dataset_rows as _load_rows
        from openpali.storage.models import DatasetVersion as _DV

        ids_n = {r["application_id"] for r in _load_rows(
            store, session.execute(
                select(_DV).where(_DV.dataset_id == ds_n.dataset_id)
            ).scalar_one())}
        ids_n1 = {r["application_id"] for r in _load_rows(
            store, session.execute(
                select(_DV).where(_DV.dataset_id == ds_n1.dataset_id)
            ).scalar_one())}
        check("late-arriving application enters N+1 only",
              "FXLATE-10000-00001" in ids_n1 - ids_n and ids_n <= ids_n1,
              f"rows {ds_n.row_count} -> {ds_n1.row_count} "
              f"(+{len(ids_n1 - ids_n)} first-observed in month 12)")

        # no-op: same snapshot rebuilt => same dataset id, no new experiment data
        ds_noop = build_dataset(session, store, fixture_result.snapshot_n1)
        check("semantic no-op creates no duplicate dataset",
              ds_noop.dataset_id == ds_n1.dataset_id and not ds_noop.created)

        print("== experiments on N (rolling folds; final block untouched) ==")
        outcome_n = run_experiments(session, store, ds_n.dataset_id)
        check("challenger executed on fixture", outcome_n.challenger_status == "completed")
        by_name = {r.name: r for r in outcome_n.runs}
        cox = by_name.get("challenger-cox")
        km = by_name.get("baseline-km")
        if cox and km:
            check("challenger beats KM on IPCW Brier@180 (fold eval)",
                  (cox.metrics.get("ipcw_brier_180") or 9) < (km.metrics.get("ipcw_brier_180") or 0),
                  f"cox={cox.metrics.get('ipcw_brier_180'):.5f} km={km.metrics.get('ipcw_brier_180'):.5f}")

        champion_before = current_champion(session)
        print("== experiments on N+1 (snapshot-triggered reevaluation) ==")
        outcome_n1 = run_experiments(session, store, ds_n1.dataset_id)
        check("N+1 evaluation ran with distinct MLflow runs",
              outcome_n1.challenger_status == "completed"
              and {r.mlflow_run_id for r in outcome_n1.runs}.isdisjoint(
                  {r.mlflow_run_id for r in outcome_n.runs}))
        champion_after = current_champion(session)
        check("champion unchanged without review",
              (champion_before.model_id if champion_before else None)
              == (champion_after.model_id if champion_after else None))

        print("== manual promotion (final-holdout evaluation + predeclared gates) ==")
        # a fold-evaluated (dev) model may NEVER be promoted: the gates
        # require the once-only final-holdout evaluation
        fold_promotion_refused = False
        if outcome_n1.model_id:
            try:
                record_promotion(
                    session, model_id=outcome_n1.model_id,
                    reviewer=args.reviewer, decision="promoted",
                    reason="drill: attempting to promote a DEV (fold) evaluation",
                )
            except ValueError as exc:
                fold_promotion_refused = True
                print(f"  fold-eval promotion refused (correct): {exc}")
        check("fold-evaluated model cannot be promoted", fold_promotion_refused)

        outcome_final = run_experiments(
            session, store, ds_n1.dataset_id, include_final_holdout=True
        )
        promoted = False
        if outcome_final.model_id:
            try:
                record_promotion(
                    session, model_id=outcome_final.model_id,
                    reviewer=args.reviewer, decision="promoted",
                    reason="fixture drill: challenger beat KM on the final holdout "
                           "under predeclared gates",
                )
                promoted = True
            except ValueError as exc:
                print(f"  promotion refused: {exc}")
        check("promotion recorded via append-only decision", promoted)

        print("== fresh-process style serving from the immutable artifact ==")
        served = build_prediction_set(
            session, store, fixture_result.snapshot_n1, ds_n1.dataset_id
        )
        check("batch prediction set served",
              served.status == "served" and served.rows > 0,
              f"rows={served.rows} set={served.prediction_set_id}")
        session.commit()

    failures = [c for c in checks if not c[1]]
    print(f"== drill: {len(checks) - len(failures)}/{len(checks)} checks passed ==")
    return 0 if not failures else 5


def cmd_spatial_acquire(args: argparse.Namespace) -> int:
    """Acquire (or offline-replay) the frozen USGS AOI and register raw assets."""

    from openpali.spatial.usgs import refresh_usgs

    store = ObjectStore()
    with session_scope() as session:
        result = refresh_usgs(session, store, online=not args.offline)
        print(
            f"usgs acquisition {result.status}: run={result.run_id} "
            f"tiles={result.tiles} raw_assets_registered={result.raw_assets_registered}"
        )
        for sha, size in result.page_hashes:
            print(f"  page {sha[:16]} {size} bytes")
        print(f"RUN_ID={result.run_id}")
        return 0 if result.status == "succeeded" else 3


def cmd_spatial_derive(args: argparse.Namespace) -> int:
    """Derive + upload + register the surfel tileset and terrain pyramid."""

    from openpali.spatial.derive import derive_usgs_products

    store = ObjectStore()
    with session_scope() as session:
        results = derive_usgs_products(session, store)
        print(json.dumps(results, indent=1, default=str))
        recon = results["reconciliation"]
        if recon["parcels_with_dem_coverage"] < 25:
            print("FAIL: fewer than 25 parcels covered by the derived asset",
                  file=sys.stderr)
            return 4
        print(f"SPATIAL_VERSION={results['version_id']}")
    return 0


def cmd_recon_drill(args: argparse.Namespace) -> int:
    """MULTIMODAL-001 drill: withheld-transform estimation -> gates -> fused
    fixture asset -> candidates -> accepted/rejected/retracted transitions."""

    from openpali.spatial.reconstruction import (
        CandidateReviewError,
        build_fixture_scene,
        fuse_and_register_asset,
        propose_candidates,
        review_candidate,
        run_reconstruction,
    )
    from openpali.storage.models import ObservationCandidate, RecoveryObservationRow

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")

    print("== deterministic two-view stress fixture (withheld ~1.5 m / 3 deg) ==")
    scene = build_fixture_scene()
    result = run_reconstruction(scene)
    for key, gate in result.gates.items():
        check(f"gate {key} <= {gate['max']}", gate["passed"], f"value={gate['value']}")

    store = ObjectStore()
    with session_scope() as session:
        print("== fuse + tile + register (synthetic_fixture rights) ==")
        asset = fuse_and_register_asset(session, store, scene, result)
        check("fused asset tiled and registered", True, f"{asset[0]}@{asset[1][:14]}")

        from openpali.spatial.registry import select_release_assets

        public = select_release_assets(session, release_kind="representative")
        barred = any(
            e["asset_id"] == asset[0] for e in public["excluded"]
        ) and not any(a["asset_id"] == asset[0] for a in public["assets"])
        check("synthetic asset technically barred from public releases", barred)

        print("== probabilistic candidates (residual/coverage-derived) ==")
        candidate_ids = propose_candidates(session, scene, result, asset)
        rows = [
            session.execute(
                select(ObservationCandidate).where(
                    ObservationCandidate.candidate_id == cid
                )
            ).scalar_one()
            for cid in candidate_ids
        ]
        check(
            "change + control candidates proposed",
            len(rows) == 2 and all(r.review_state == "pending" for r in rows),
            f"confidences={[round(r.confidence, 3) for r in rows]}",
        )
        check(
            "candidate carries full truth model",
            all(
                r.confidence_method and r.registration_residual_m is not None
                and r.coverage_fraction is not None and r.occlusion
                and r.process_version and r.rights_state == "synthetic_fixture"
                for r in rows
            ),
        )

        def observation_count() -> int:
            return session.execute(
                select(func.count()).select_from(RecoveryObservationRow).where(
                    RecoveryObservationRow.source_id == "fixture_reconstruction"
                )
            ).scalar_one()

        from sqlalchemy import func

        before = observation_count()
        check("no civic observation exists before review", before == 0, f"n={before}")

        print("== review transitions ==")
        change_id, control_id = candidate_ids[0], candidate_ids[1]
        obs_id = review_candidate(
            session, change_id, "accepted",
            reviewer="drill-reviewer", reason="occupancy delta is decisive",
        )
        check("acceptance appends exactly one observation",
              obs_id is not None and observation_count() == 1)

        review_candidate(
            session, control_id, "rejected",
            reviewer="drill-reviewer", reason="control region: no change claimed",
        )
        check("rejection appends nothing", observation_count() == 1)

        try:
            review_candidate(session, control_id, "accepted",
                             reviewer="x", reason="y")
            check("rejected candidate cannot be accepted later", False)
        except CandidateReviewError:
            check("rejected candidate cannot be accepted later", True)

        review_candidate(
            session, change_id, "retracted",
            reviewer="drill-reviewer", reason="drill: exercising retraction",
        )
        from openpali.storage.models import ObservationRevision

        n_revisions = session.execute(
            select(func.count()).select_from(ObservationRevision).where(
                ObservationRevision.source_id == "fixture_reconstruction"
            )
        ).scalar_one()
        check("retraction is an append-only revision (observation preserved)",
              n_revisions == 1 and observation_count() == 1)
        session.commit()

    failures = [c for c in checks if not c[1]]
    print(f"== recon drill: {len(checks) - len(failures)}/{len(checks)} checks passed ==")
    return 0 if not failures else 5


def cmd_recon_gpu_probe(args: argparse.Namespace) -> int:
    """Typed hardware boundary for the optional GPU reconstruction worker."""

    from openpali.spatial.reconstruction import gpu_probe

    result = gpu_probe()
    print(json.dumps(result, indent=1))
    return 0


def cmd_spatial_register_prefire(args: argparse.Namespace) -> int:
    """Register the tracked pre-fire LARIAC-derived corpus with UNRESOLVED
    rights so every release manifest documents its exclusion (rights gate:
    the asset is excluded, the spatial path stays enabled)."""

    from datetime import datetime, timezone

    from openpali.spatial.registry import register_asset_version

    with session_scope() as session:
        created = register_asset_version(
            session,
            asset_id="lariac-prefire-scene",
            version_id="sv-tracked-corpus-v1",
            subject_type="aoi",
            subject_id="palisades-fire-footprint",
            asset_kind="surfel_tiles",
            vintage_slot="pre_fire_lariac",
            source_id="lariac_derived",
            observation_kind="pre_fire_model",
            rights_state="unresolved",
            horizontal_crs="WGS84 ECEF (tileset ENU origin)",
            vertical_datum="WGS84 ellipsoidal (EGM96-derived offset)",
            units="meters",
            transform={"note": "committed web/public/tiles/palisades corpus"},
            acquisition_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
            acquisition_end=datetime(2023, 12, 31, tzinfo=timezone.utc),
            processed_at=None,
            resolution_m=None,
            coverage={"note": "full fire footprint; per-parcel provenance in coverage.json"},
            quality={
                "content_units": 1,
                "rights_note": (
                    "LARIAC-derived product; county license terms for public "
                    "redistribution and model training are UNRESOLVED — a "
                    "sponsor-owned decision. Excluded from all release "
                    "manifests until resolved; the rights-safe USGS post-fire "
                    "path remains enabled."
                ),
            },
            lineage=[{"kind": "tracked_repo_path", "path": "web/public/tiles/palisades"}],
            object_uri="repo://web/public/tiles/palisades/tileset.json",
            object_sha256=None,
            format_version="3dtiles-splat-v1",
            status="ready",
        )
        print(f"lariac-prefire-scene registered created={created} rights=unresolved")
    return 0


def cmd_schedule_drill(args: argparse.Namespace) -> int:
    """OPS: prove scheduling works end-to-end — attach a short interval
    schedule to the county source-refresh deployment, watch the SCHEDULER
    (not us) create a run, watch the WORKER complete it, then detach."""

    import asyncio
    from datetime import timedelta

    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import DeploymentScheduleCreate
    from prefect.client.schemas.filters import (
        DeploymentFilter,
        DeploymentFilterId,
        FlowRunFilter,
        FlowRunFilterExpectedStartTime,
    )
    from prefect.client.schemas.schedules import IntervalSchedule

    async def drill() -> int:
        async with get_client() as client:
            deployment = await client.read_deployment_by_name("source-refresh/default")
            print(f"deployment: {deployment.id}")
            schedules = await client.create_deployment_schedules(
                deployment.id,
                [DeploymentScheduleCreate(
                    schedule=IntervalSchedule(interval=timedelta(seconds=45)),
                    active=True,
                    parameters={"source_id": "county_base", "online": True},
                )],
            )
            schedule_id = schedules[0].id
            print(f"schedule attached: {schedule_id} (45s interval)")
            try:
                from datetime import datetime, timezone

                started = datetime.now(timezone.utc)
                completed_run = None
                for _ in range(40):  # up to ~7 min
                    await asyncio.sleep(10)
                    runs = await client.read_flow_runs(
                        deployment_filter=DeploymentFilter(
                            id=DeploymentFilterId(any_=[deployment.id])
                        ),
                        flow_run_filter=FlowRunFilter(
                            expected_start_time=FlowRunFilterExpectedStartTime(
                                after_=started
                            )
                        ),
                    )
                    scheduled = [
                        r for r in runs
                        if (r.state_name or "") in {"Scheduled", "Pending", "Running",
                                                    "Completed", "Failed", "Crashed"}
                    ]
                    done = [r for r in scheduled if r.state_name == "Completed"]
                    print(f"  scheduler-created runs: {len(scheduled)} "
                          f"(completed: {len(done)})")
                    if done:
                        completed_run = done[0]
                        break
            finally:
                await client.delete_deployment_schedule(deployment.id, schedule_id)
                print("schedule detached")
            if completed_run is None:
                print("FAIL: no scheduler-created run completed in time")
                return 5
            print(f"SCHEDULE DRILL OK: run {completed_run.id} completed "
                  f"(created by the scheduler, executed by the worker)")
            return 0

    return asyncio.run(drill())


def cmd_flow_reap(args: argparse.Namespace) -> int:
    """OPS remediation: force zombie flow runs (Running, but their worker
    process died) into CRASHED so their failure is VISIBLE and reruns can
    proceed. Process workers have no heartbeat reaper — a mid-run worker
    restart otherwise leaves runs hanging in Running forever (found by the
    worker kill/resume drill)."""

    import asyncio

    from prefect.client.orchestration import get_client
    from prefect.client.schemas.filters import (
        FlowRunFilter,
        FlowRunFilterState,
        FlowRunFilterStateName,
    )
    from prefect.client.schemas.objects import StateType
    from prefect.states import Crashed

    async def reap() -> int:
        async with get_client() as client:
            runs = await client.read_flow_runs(
                flow_run_filter=FlowRunFilter(
                    state=FlowRunFilterState(
                        name=FlowRunFilterStateName(any_=["Running", "Cancelling"])
                    )
                )
            )
            if not runs:
                print("no running flow runs to inspect")
                return 0
            reaped = 0
            for run in runs:
                await client.set_flow_run_state(
                    run.id,
                    Crashed(message="operator reap: worker process died mid-run"),
                    force=True,
                )
                print(f"reaped {run.id} ({run.name}) Running -> Crashed")
                reaped += 1
            print(f"FLOW REAP: {reaped} zombie run(s) marked Crashed (visible failure)")
            return 0

    return asyncio.run(reap())


def cmd_restore_verify(args: argparse.Namespace) -> int:
    """OPS restore drill, object/API half: prove the object plane and the
    serving path survive alongside the database restore — the current
    release's mirrored manifest hash matches the DB, one raw page, one model
    artifact, and one spatial file verify BY DIGEST, and the API serves the
    release, a property, and an MVT tile."""

    import hashlib as _hashlib
    import urllib.request

    from openpali.storage.models import (
        AcquisitionPage,
        CivicSnapshot,
        CurrentRelease,
        ModelVersion,
        Publication,
        RawObject,
        SpatialAsset,
    )
    from openpali.storage.objects import (
        ARTIFACT_BUCKET,
        PUBLICATION_BUCKET,
        RAW_BUCKET,
        SPATIAL_BUCKET,
    )

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")

    store = ObjectStore()
    with session_scope() as session:
        current = session.get(CurrentRelease, 1)
        publication = session.execute(
            select(Publication).where(
                Publication.release_id == current.current_release_id
            )
        ).scalar_one()
        rid = publication.release_id

        mirrored = store.client.get_object(
            Bucket=PUBLICATION_BUCKET, Key=f"publications/{rid}/manifest.json"
        )["Body"].read()
        check(
            "mirrored manifest hash matches DB",
            _hashlib.sha256(mirrored).hexdigest() == publication.manifest_sha256,
            rid,
        )

        snapshot = session.execute(
            select(CivicSnapshot).where(
                CivicSnapshot.snapshot_id == publication.snapshot_id
            )
        ).scalar_one()
        page = session.execute(
            select(RawObject)
            .join(AcquisitionPage, AcquisitionPage.raw_object_id == RawObject.id)
            .limit(1)
        ).scalar_one()
        key = page.object_uri.split("/", 3)[3]
        store.get_verified(RAW_BUCKET, key, page.sha256, page.byte_size)
        check("raw page verifies by digest", True, page.sha256[:16])
        assert snapshot  # release-bound snapshot exists

        model = session.execute(select(ModelVersion).limit(1)).scalar_one_or_none()
        if model is not None:
            mkey = model.artifact_uri.split("/", 3)[3]
            store.get_verified(ARTIFACT_BUCKET, mkey, model.artifact_sha256)
            check("model artifact verifies by digest", True, model.artifact_sha256[:16])
        else:
            check("model artifact verifies by digest", False, "no model rows")

        spatial = session.execute(
            select(SpatialAsset).where(
                SpatialAsset.asset_id == "usgs-surfel-aoi",
                SpatialAsset.status == "ready",
            ).order_by(SpatialAsset.ingested_at.desc()).limit(1)
        ).scalar_one_or_none()
        if spatial is not None:
            skey = f"assets/{spatial.asset_id}/{spatial.version_id}/tileset.json"
            ok = store.exists(SPATIAL_BUCKET, skey)
            check("spatial tileset object present", ok, spatial.version_id[:14])
        else:
            check("spatial tileset object present", False, "no ready asset")

    base = "http://api:8000"
    for path, name in (
        ("/v1/releases/current", "API serves current release"),
        (f"/v1/releases/{rid}/properties?page_size=1", "API serves a property page"),
        (f"/v1/releases/{rid}/tiles/parcels/14/2797/6542.mvt", "API serves an MVT tile"),
    ):
        try:
            with urllib.request.urlopen(base + path, timeout=20) as r:
                check(name, r.status == 200, f"HTTP {r.status}")
        except Exception as exc:  # noqa: BLE001
            check(name, False, str(exc)[:80])

    failures = [c for c in checks if not c[1]]
    print(f"== restore-verify: {len(checks) - len(failures)}/{len(checks)} checks passed ==")
    return 0 if not failures else 5
