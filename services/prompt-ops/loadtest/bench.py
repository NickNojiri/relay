"""Dependency-light async load test for the Relay gateway's flag-eval + proxy path.

A portable alternative to `flag-eval.k6.js` for environments without k6 — same
target (`POST /v1/chat` with the seeded `prompt.support-bot` flag) and the same
intent: measure the flag engine + gateway overhead under concurrency, not a real
LLM. Uses only httpx (already a gateway dependency).

    # Terminal A — gateway with the network-free echo provider, no DB needed:
    RELAY_DEFAULT_PROVIDER=echo uv run uvicorn app.main:app --port 8000
    # Terminal B:
    uv run python loadtest/bench.py --concurrency 50 --duration 30

Prints throughput and p50/p95/p99 latency as JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time

import httpx


async def _worker(
    client: httpx.AsyncClient, url: str, deadline: float, latencies: list[float], errors: list[int]
) -> None:
    while time.monotonic() < deadline:
        body = {
            "prompt_key": "prompt.support-bot",
            "unit_id": f"user-{random.randint(0, 100_000)}",
            "input": "hello",
        }
        start = time.perf_counter()
        try:
            resp = await client.post(url, json=body)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if resp.status_code == 200 and resp.json().get("variant") is not None:
                latencies.append(elapsed_ms)
            else:
                errors.append(resp.status_code)
        except httpx.HTTPError:
            errors.append(0)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(round(pct / 100 * (len(sorted_values) - 1))))
    return sorted_values[idx]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--api-key", default=None, help="sent as Authorization: Bearer")
    args = parser.parse_args()

    url = f"{args.gateway}/v1/chat"
    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}
    latencies: list[float] = []
    errors: list[int] = []

    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(timeout=30, headers=headers, limits=limits) as client:
        started = time.monotonic()
        deadline = started + args.duration
        await asyncio.gather(
            *(_worker(client, url, deadline, latencies, errors) for _ in range(args.concurrency))
        )
        wall = time.monotonic() - started

    latencies.sort()
    total = len(latencies) + len(errors)
    report = {
        "concurrency": args.concurrency,
        "duration_s": round(wall, 2),
        "requests": total,
        "ok": len(latencies),
        "errors": len(errors),
        "error_rate": round(len(errors) / total, 5) if total else 0.0,
        "throughput_rps": round(len(latencies) / wall, 1) if wall else 0.0,
        "latency_ms": {
            "p50": round(_percentile(latencies, 50), 2),
            "p95": round(_percentile(latencies, 95), 2),
            "p99": round(_percentile(latencies, 99), 2),
            "max": round(latencies[-1], 2) if latencies else 0.0,
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
