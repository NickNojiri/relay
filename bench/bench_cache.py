"""Measures the TTL cache's effect on flag-lookup latency (resume metric #1).

Runs the same lookup workload twice against real Postgres — once straight through
PostgresRepository, once through CachedRepository — and reports the delta.

Usage:
    docker compose -f infra/docker-compose.yml up -d
    pnpm --filter @relay/db db:migrate
    cd services/prompt-ops
    uv run python ../../bench/bench_cache.py

Env:
    RELAY_DATABASE_URL   postgres DSN (default: local docker compose)
    BENCH_N              lookups per arm (default 2000)
    BENCH_FLAG           flag key to look up (default prompt.support-bot)
"""

import asyncio
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "prompt-ops"))

from app.repository import CachedRepository, PostgresRepository  # noqa: E402

DSN = os.environ.get(
    "RELAY_DATABASE_URL", "postgresql://relay:relay@localhost:5432/relay"
)
N = int(os.environ.get("BENCH_N", "2000"))
FLAG = os.environ.get("BENCH_FLAG", "prompt.support-bot")


async def time_lookups(repo, n: int) -> list[float]:
    """Returns per-call latencies in milliseconds."""
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        await repo.get_flag(FLAG)
        samples.append((time.perf_counter() - t0) * 1000)
    return samples


def report(name: str, s: list[float]) -> dict:
    s_sorted = sorted(s)
    stats = {
        "mean": statistics.mean(s),
        "p50": s_sorted[len(s) // 2],
        "p95": s_sorted[int(len(s) * 0.95)],
        "p99": s_sorted[int(len(s) * 0.99)],
    }
    print(
        f"  {name:<28} mean {stats['mean']:7.3f} ms | "
        f"p50 {stats['p50']:7.3f} | p95 {stats['p95']:7.3f} | p99 {stats['p99']:7.3f}"
    )
    return stats


async def main() -> None:
    try:
        import asyncpg
    except ImportError:
        sys.exit("asyncpg required: uv add asyncpg")

    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=4)
    try:
        raw = PostgresRepository(pool)
        cached = CachedRepository(PostgresRepository(pool), ttl_seconds=5.0)

        # Warm the connection pool so arm 1 isn't charged for connect cost.
        await raw.get_flag(FLAG)
        await cached.get_flag(FLAG)

        print(f"\nFlag-lookup latency over {N} calls (flag={FLAG})\n")
        uncached = await time_lookups(raw, N)
        c_stats = await time_lookups(cached, N)

        u = report("PostgresRepository", uncached)
        c = report("CachedRepository (5s TTL)", c_stats)

        drop_mean = (1 - c["mean"] / u["mean"]) * 100
        drop_p95 = (1 - c["p95"] / u["p95"]) * 100
        print(
            f"\n  => cache cuts mean flag-lookup latency {drop_mean:.1f}% "
            f"({u['mean']:.3f} ms -> {c['mean']:.3f} ms); p95 {drop_p95:.1f}%"
        )
        print(
            f"  => resume line: \"cut flag-lookup latency {drop_mean:.0f}% "
            f"({u['mean']:.2f} ms -> {c['mean']:.2f} ms p50-mean over {N} calls)\"\n"
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
