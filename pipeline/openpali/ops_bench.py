"""API benchmark (BACKEND-001): cold/warm latency + payload budgets.

200 requests across 20 concurrent clients against the release-qualified
routes, run twice (cold then warm — the second pass hits ETag/manifest
caches). DECLARED budgets fail the run; results print as one JSON artifact.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx

BUDGETS = {
    "warm_p95_ms": 750.0,
    "cold_p95_ms": 3000.0,
    "payload_caps": {  # bytes; queries must page, not dump
        "/properties?": 250_000,
        "/properties/prop": 60_000,
        "/observations": 250_000,
        "/metrics/community": 400_000,
        "/releases/current": 20_000,
    },
}
N_CLIENTS = 20
N_REQUESTS = 200


async def run(base: str) -> int:
    async with httpx.AsyncClient(base_url=base, timeout=30) as bootstrap:
        release = (await bootstrap.get("/v1/releases/current")).json()
        rid = release["release_id"]
        page = (await bootstrap.get(
            f"/v1/releases/{rid}/properties", params={"page_size": 5}
        )).json()
        pid = page["items"][0]["property_id"]

    routes = [
        "/v1/releases/current",
        f"/v1/releases/{rid}",
        f"/v1/releases/{rid}/properties?page_size=50",
        f"/v1/releases/{rid}/properties/{pid}",
        f"/v1/releases/{rid}/properties/{pid}/observations?limit=50",
        f"/v1/releases/{rid}/properties/{pid}/forecast",
        f"/v1/releases/{rid}/metrics/community",
        f"/v1/releases/{rid}/tiles/parcels/14/2797/6542.mvt",
        f"/v1/releases/{rid}/spatial/assets",
        f"/v1/releases/{rid}/sources",
    ]
    plan = [routes[i % len(routes)] for i in range(N_REQUESTS)]

    async def pass_once(label: str) -> dict:
        latencies: list[float] = []
        payload_violations: list[str] = []
        errors: list[str] = []
        queue: asyncio.Queue[str] = asyncio.Queue()
        for url in plan:
            queue.put_nowait(url)

        async def worker() -> None:
            async with httpx.AsyncClient(base_url=base, timeout=30) as client:
                while True:
                    try:
                        url = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    start = time.perf_counter()
                    try:
                        resp = await client.get(url)
                        elapsed = (time.perf_counter() - start) * 1000
                        latencies.append(elapsed)
                        if resp.status_code >= 400:
                            errors.append(f"{url} -> {resp.status_code}")
                        size = len(resp.content)
                        for fragment, cap in BUDGETS["payload_caps"].items():
                            if fragment in url and size > cap:
                                payload_violations.append(f"{url}: {size} > {cap}")
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{url}: {exc}")

        await asyncio.gather(*[worker() for _ in range(N_CLIENTS)])
        latencies.sort()
        p = lambda q: latencies[min(len(latencies) - 1, int(q * len(latencies)))] if latencies else None  # noqa: E731
        return {
            "pass": label,
            "requests": len(latencies),
            "p50_ms": round(p(0.5), 1),
            "p95_ms": round(p(0.95), 1),
            "max_ms": round(p(1.0), 1),
            "errors": errors[:5],
            "error_count": len(errors),
            "payload_violations": sorted(set(payload_violations))[:5],
        }

    cold = await pass_once("cold")
    warm = await pass_once("warm")
    verdicts = {
        "cold_p95_within_budget": cold["p95_ms"] <= BUDGETS["cold_p95_ms"],
        "warm_p95_within_budget": warm["p95_ms"] <= BUDGETS["warm_p95_ms"],
        "no_errors": cold["error_count"] == 0 and warm["error_count"] == 0,
        "no_payload_violations": not cold["payload_violations"] and not warm["payload_violations"],
    }
    report = {
        "release_id": rid,
        "clients": N_CLIENTS,
        "requests_per_pass": N_REQUESTS,
        "budgets": BUDGETS,
        "cold": cold,
        "warm": warm,
        "verdicts": verdicts,
    }
    print("API_BENCH " + json.dumps(report))
    return 0 if all(verdicts.values()) else 5


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://api:8000"
    return asyncio.run(run(base))


if __name__ == "__main__":
    raise SystemExit(main())
