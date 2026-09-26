"""Reproducible load test for the Relay gateway. See loadtest/README.md.

    uv run python loadtest/bench.py --config loadtest/configs/echo.toml

Starts the gateway with the settings pinned in the config (or targets --gateway URL),
runs every concurrency level `repeats` times after a warmup, and writes a run directory
under loadtest/results/: config.toml, manifest.json, requests.csv.gz (one row per
request), summary.csv (one row per level x repeat) and summary.md (medians + ranges).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import importlib.metadata
import json
import math
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

SERVICE_DIR = Path(__file__).resolve().parents[1]
RAW_FIELDS = ["concurrency", "repeat", "worker", "seq", "start_ms", "latency_ms", "status", "variant", "unit_id", "error"]
SUMMARY_FIELDS = ["concurrency", "repeat", "requests", "ok", "errors", "wall_s", "throughput_rps", "p50_ms", "p95_ms", "p99_ms", "max_ms"]


@dataclass
class Row:
    concurrency: int
    repeat: int
    worker: int
    seq: int
    start_ms: float
    latency_ms: float
    status: int
    variant: str
    unit_id: str
    error: str


def percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile: the smallest value with at least pct% of samples at or below it."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


async def _worker(
    client: httpx.AsyncClient,
    load: dict,
    concurrency: int,
    repeat: int,
    worker: int,
    phase_start: float,
    deadline: float,
    rows: list[Row] | None,
) -> None:
    # String seeds are hashed deterministically (unlike hash()), so every rerun of a level
    # sends the same unit-id sequence, and therefore the same A/B mix.
    rng = random.Random(f"{load['seed']}-{concurrency}-{worker}")
    seq = 0
    while time.perf_counter() < deadline:
        unit_id = f"user-{rng.randrange(load['unit_ids'])}"
        body = {"prompt_key": load["prompt_key"], "unit_id": unit_id, "input": load["input"]}
        start = time.perf_counter()
        status, variant, error = 0, "", ""
        try:
            resp = await client.post(load["endpoint"], json=body)
            status = resp.status_code
            if status == 200:
                variant = resp.json().get("variant") or ""
        except httpx.HTTPError as exc:
            error = type(exc).__name__
        latency_ms = (time.perf_counter() - start) * 1000
        if rows is not None:
            rows.append(
                Row(concurrency, repeat, worker, seq, round((start - phase_start) * 1000, 3),
                    round(latency_ms, 3), status, variant, unit_id, error)
            )
        seq += 1


async def run_phase(
    client: httpx.AsyncClient, load: dict, concurrency: int, repeat: int, duration_s: float, record: bool = True
) -> tuple[list[Row], float]:
    """Run `concurrency` closed-loop workers for duration_s. Returns (rows, wall seconds)."""
    rows: list[Row] | None = [] if record else None
    start = time.perf_counter()
    deadline = start + duration_s
    await asyncio.gather(
        *(_worker(client, load, concurrency, repeat, w, start, deadline, rows) for w in range(concurrency))
    )
    return rows or [], time.perf_counter() - start


def summarize(rows: list[Row], concurrency: int, repeat: int, wall_s: float) -> dict:
    ok = sorted(r.latency_ms for r in rows if r.status == 200 and r.variant)
    return {
        "concurrency": concurrency,
        "repeat": repeat,
        "requests": len(rows),
        "ok": len(ok),
        "errors": len(rows) - len(ok),
        "wall_s": round(wall_s, 3),
        "throughput_rps": round(len(ok) / wall_s, 1) if wall_s else 0.0,
        "p50_ms": round(percentile(ok, 50), 2),
        "p95_ms": round(percentile(ok, 95), 2),
        "p99_ms": round(percentile(ok, 99), 2),
        "max_ms": round(ok[-1], 2) if ok else 0.0,
    }


def summary_markdown(summaries: list[dict]) -> str:
    """Median across repeats, with the min-max range, per concurrency level."""
    lines = [
        "| Concurrency | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Errors |",
        "|---|---|---|---|---|---|",
    ]
    for level in sorted({s["concurrency"] for s in summaries}):
        runs = [s for s in summaries if s["concurrency"] == level]

        def cell(key: str) -> str:
            vals = [r[key] for r in runs]
            return f"{statistics.median(vals):g} ({min(vals):g}–{max(vals):g})"

        errors = sum(r["errors"] for r in runs)
        total = sum(r["requests"] for r in runs)
        lines.append(
            f"| {level} | {cell('throughput_rps')} | {cell('p50_ms')} | {cell('p95_ms')} | "
            f"{cell('p99_ms')} | {errors} / {total:,} |"
        )
    n = len({s["repeat"] for s in summaries})
    lines.append("")
    lines.append(f"Median of {n} repeats per level, (min–max) in parentheses. Percentiles are nearest-rank over successful requests.")
    return "\n".join(lines) + "\n"


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    if sys.platform == "darwin":
        try:
            return subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return platform.processor() or "unknown"


def _memory_gb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return None


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=SERVICE_DIR, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def manifest(config: dict, gateway_url: str, launched: bool) -> dict:
    versions = {}
    for pkg in ("fastapi", "starlette", "uvicorn", "httpx", "pydantic"):
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = None
    return {
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": _git("rev-parse", "HEAD"),
        # Earlier runs' output doesn't change what is measured, so it doesn't count as dirty.
        "git_dirty": bool(_git("status", "--porcelain", "--", ":/", ":(exclude)loadtest/results")),
        "gateway_url": gateway_url,
        "gateway_launched_by_bench": launched,
        "client_and_gateway_same_host": launched,
        "machine": {
            "cpu_model": _cpu_model(),
            "logical_cpus": os.cpu_count(),
            "memory_gb": _memory_gb(),
            "os": platform.platform(),
            "python": platform.python_version(),
        },
        "packages": versions,
        "config": config,
    }


def start_gateway(gw: dict) -> subprocess.Popen:
    env = {**os.environ, **{k: str(v) for k, v in gw["env"].items()}}
    cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", str(gw["port"]),
        "--workers", str(gw["workers"]), "--log-level", "warning",
    ]
    if not gw.get("access_log", False):
        cmd.append("--no-access-log")
    return subprocess.Popen(cmd, cwd=SERVICE_DIR, env=env)


def wait_healthy(url: str, timeout_s: float = 30) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise SystemExit(f"gateway at {url} did not become healthy within {timeout_s}s")


async def run_all(config: dict, url: str, api_key: str | None) -> tuple[list[Row], list[dict]]:
    load = config["load"]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    all_rows: list[Row] = []
    summaries: list[dict] = []
    for level in load["concurrency"]:
        limits = httpx.Limits(max_connections=level, max_keepalive_connections=level)
        async with httpx.AsyncClient(base_url=url, headers=headers, limits=limits, timeout=load["timeout_s"]) as client:
            await run_phase(client, load, level, -1, load["warmup_s"], record=False)
            for repeat in range(load["repeats"]):
                rows, wall = await run_phase(client, load, level, repeat, load["duration_s"])
                summary = summarize(rows, level, repeat, wall)
                print(
                    f"c={level:<4} repeat={repeat}  {summary['throughput_rps']:>8} req/s  "
                    f"p50={summary['p50_ms']}ms p95={summary['p95_ms']}ms p99={summary['p99_ms']}ms  "
                    f"errors={summary['errors']}/{summary['requests']}",
                    flush=True,
                )
                all_rows.extend(rows)
                summaries.append(summary)
    return all_rows, summaries


def write_results(out_dir: Path, config_path: Path, man: dict, rows: list[Row], summaries: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(config_path, out_dir / "config.toml")
    (out_dir / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with gzip.open(out_dir / "requests.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RAW_FIELDS)
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    with open(out_dir / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        w.writeheader()
        w.writerows(summaries)
    (out_dir / "summary.md").write_text(summary_markdown(summaries))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=SERVICE_DIR / "loadtest/configs/echo.toml")
    parser.add_argument("--gateway", help="target an already-running gateway instead of launching one")
    parser.add_argument("--api-key", help="sent as Authorization: Bearer (for --gateway)")
    parser.add_argument("--out", type=Path, default=SERVICE_DIR / "loadtest/results")
    parser.add_argument("--label", help="suffix for the run directory name, e.g. the machine")
    args = parser.parse_args()

    config = tomllib.loads(args.config.read_text())
    launched = args.gateway is None
    url = args.gateway or f"http://127.0.0.1:{config['gateway']['port']}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out / "-".join(filter(None, [stamp, config["name"], args.label]))

    proc = start_gateway(config["gateway"]) if launched else None
    try:
        wait_healthy(url)
        man = manifest(config, url, launched)
        rows, summaries = asyncio.run(run_all(config, url, args.api_key))
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=10)

    write_results(out_dir, args.config, man, rows, summaries)
    print()
    print(summary_markdown(summaries))
    print(f"Results: {out_dir}")


if __name__ == "__main__":
    main()
