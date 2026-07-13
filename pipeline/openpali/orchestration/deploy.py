"""Register Prefect work pool + deployments (runs INSIDE the cluster so the
stored source path matches the worker's filesystem)."""

from __future__ import annotations

import asyncio
from pathlib import Path

WORK_POOL = "openpali-process"

#: Deployments: flow entrypoint -> (deployment name, default parameters).
DEPLOYMENTS = {
    "source_refresh_flow": ("default", {}),
    "civic_snapshot_flow": ("default", {}),
    "analytics_snapshot_flow": ("default", {}),
    "release_candidate_flow": ("default", {}),
    "full_refresh_release_flow": ("default", {}),
    "spatial_refresh_flow": ("default", {}),
}


async def _ensure_work_pool() -> None:
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import WorkPoolCreate
    from prefect.exceptions import ObjectAlreadyExists

    async with get_client() as client:
        try:
            await client.create_work_pool(
                WorkPoolCreate(name=WORK_POOL, type="process")
            )
            print(f"work pool created: {WORK_POOL}")
        except ObjectAlreadyExists:
            print(f"work pool exists: {WORK_POOL}")


def register_deployments() -> list[str]:
    asyncio.run(_ensure_work_pool())
    from openpali.orchestration import flows as flows_module

    source_root = str(Path(flows_module.__file__).resolve().parents[2])
    registered: list[str] = []
    for function_name, (deployment_name, parameters) in DEPLOYMENTS.items():
        flow_fn = getattr(flows_module, function_name)
        flow_from_source = flow_fn.from_source(
            source=source_root,
            entrypoint=f"openpali/orchestration/flows.py:{function_name}",
        )
        identifier = flow_from_source.deploy(
            name=deployment_name,
            work_pool_name=WORK_POOL,
            parameters=parameters,
            build=False,
            push=False,
            print_next_steps=False,
        )
        registered.append(f"{flow_fn.name}/{deployment_name} ({identifier})")
        print(f"registered deployment: {flow_fn.name}/{deployment_name}")
    return registered
