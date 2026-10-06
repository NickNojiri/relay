"""Live failover demo: knock out the primary provider during steady load and record which
provider answered each request.

    uv run python -m loadtest.failover_demo --label <machine>

Starts two stand-in servers (stub_upstream.py): an Ollama-compatible primary and an
OpenAI-compatible fallback. The gateway routes to the primary with the fallback configured.
Under closed-loop load, the primary is killed at --kill-at seconds and restarted at
--restore-at. Writes results/<UTC time>-failover-demo[-label]/ with every request, a
per-second timeline, a markdown summary and an SVG chart.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from loadtest.bench import SERVICE_DIR, _serve, manifest, wait_healthy

PRIMARY_PORT, FALLBACK_PORT, GATEWAY_PORT = 8766, 8767, 8765
GATEWAY_ENV = {
    "RELAY_DEFAULT_PROVIDER": "ollama",
    "RELAY_DEFAULT_MODEL": "stub",
    "OLLAMA_BASE_URL": f"http://127.0.0.1:{PRIMARY_PORT}",
    "OPENAI_BASE_URL": f"http://127.0.0.1:{FALLBACK_PORT}",
    "RELAY_FALLBACKS": json.dumps([{"provider": "openai", "model": "stub"}]),
    "RELAY_TIMEOUTS": json.dumps({"ollama": {"connect": 1, "read": 5}}),
    "RELAY_DB_ENABLED": "false",
    "RELAY_API_KEYS": "",
    "RELAY_RATE_LIMIT_PER_MINUTE": "0",
    "RELAY_OTEL_ENABLED": "false",
}


def stub(port: int):
    return _serve("loadtest.stub_upstream:app", port, {"STUB_DELAY_MS": 0})


async def load(url: str, concurrency: int, duration_s: float, rows: list[dict], t0: float) -> None:
    async def worker(w: int) -> None:
        async with httpx.AsyncClient(base_url=url, timeout=30) as client:
            seq = 0
            while time.perf_counter() - t0 < duration_s:
                start = time.perf_counter()
                body = {"prompt_key": "prompt.support-bot", "unit_id": f"user-{w}-{seq}", "input": "hello"}
                row = {"t_s": round(start - t0, 3), "worker": w, "status": 0, "provider": "", "fallback_reason": ""}
                try:
                    resp = await client.post("/v1/chat", json=body)
                    row["status"] = resp.status_code
                    if resp.status_code == 200:
                        data = resp.json()
                        row["provider"] = data["provider"]
                        row["fallback_reason"] = data.get("fallback_reason") or ""
                except httpx.HTTPError as exc:
                    row["fallback_reason"] = type(exc).__name__
                row["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
                rows.append(row)
                seq += 1

    await asyncio.gather(*(worker(w) for w in range(concurrency)))


async def run(args) -> list[dict]:
    rows: list[dict] = []
    t0 = time.perf_counter()
    loader = asyncio.create_task(load(f"http://127.0.0.1:{GATEWAY_PORT}", args.concurrency, args.duration, rows, t0))
    await asyncio.sleep(args.kill_at)
    args.primary.terminate()
    await asyncio.to_thread(args.primary.wait)
    print(f"t={time.perf_counter() - t0:.1f}s primary killed", flush=True)
    await asyncio.sleep(args.restore_at - (time.perf_counter() - t0))
    args.primary = stub(PRIMARY_PORT)
    await asyncio.to_thread(wait_healthy, f"http://127.0.0.1:{PRIMARY_PORT}")
    print(f"t={time.perf_counter() - t0:.1f}s primary back", flush=True)
    await loader
    return rows


def timeline(rows: list[dict], duration: float) -> list[dict]:
    seconds = [{"second": s, "ollama": 0, "openai": 0, "errors": 0} for s in range(int(duration) + 1)]
    for r in rows:
        bucket = seconds[min(int(r["t_s"]), len(seconds) - 1)]
        if r["status"] == 200:
            bucket[r["provider"]] += 1
        else:
            bucket["errors"] += 1
    return seconds


def chart_svg(seconds: list[dict], kill_at: float, restore_at: float) -> str:
    w, h, left, bottom, top = 640, 260, 48, 32, 16
    peak = max(s["ollama"] + s["openai"] + s["errors"] for s in seconds) or 1
    bar = (w - left - 8) / len(seconds)
    scale = (h - bottom - top) / peak
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="11">',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
    ]
    for s in seconds:
        x, y = left + s["second"] * bar, h - bottom
        for key, color in (("ollama", "#0d7766"), ("openai", "#b45f06"), ("errors", "#c0262d")):
            height = s[key] * scale
            if height:
                parts.append(f'<rect x="{x + 1:.1f}" y="{y - height:.1f}" width="{bar - 2:.1f}" height="{height:.1f}" fill="{color}"/>')
                y -= height
    for at, label in ((kill_at, "primary killed"), (restore_at, "primary back")):
        x = left + at * bar
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{h - bottom}" stroke="#18211e" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{x + 4:.1f}" y="{top + 10}" fill="#18211e">{label}</text>')
    parts.append(f'<line x1="{left}" y1="{h - bottom}" x2="{w - 8}" y2="{h - bottom}" stroke="#59655f"/>')
    parts.append(f'<text x="{left}" y="{h - 10}" fill="#59655f">requests answered per second →</text>')
    for i, (label, color) in enumerate((("ollama (primary)", "#0d7766"), ("openai (fallback)", "#b45f06"), ("errors", "#c0262d"))):
        x = left + 200 + i * 130
        parts.append(f'<rect x="{x}" y="{h - 19}" width="10" height="10" fill="{color}"/><text x="{x + 14}" y="{h - 10}" fill="#18211e">{label}</text>')
    parts.append(f'<text x="{left - 6}" y="{top + 4}" text-anchor="end" fill="#59655f">{peak}</text>')
    parts.append(f'<text x="{left - 6}" y="{h - bottom}" text-anchor="end" fill="#59655f">0</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--duration", type=float, default=21.0)
    parser.add_argument("--kill-at", type=float, default=7.0)
    parser.add_argument("--restore-at", type=float, default=14.0)
    parser.add_argument("--label")
    parser.add_argument("--out", type=Path, default=SERVICE_DIR / "loadtest/results")
    args = parser.parse_args()

    procs = [stub(FALLBACK_PORT)]
    args.primary = stub(PRIMARY_PORT)
    try:
        wait_healthy(f"http://127.0.0.1:{FALLBACK_PORT}")
        wait_healthy(f"http://127.0.0.1:{PRIMARY_PORT}")
        procs.append(_serve("app.main:app", GATEWAY_PORT, GATEWAY_ENV))
        wait_healthy(f"http://127.0.0.1:{GATEWAY_PORT}")
        settings = {k: vars(args)[k] for k in ("concurrency", "duration", "kill_at", "restore_at")}
        man = manifest({"name": "failover-demo", "demo": settings, "gateway_env": GATEWAY_ENV}, f"http://127.0.0.1:{GATEWAY_PORT}", True)
        rows = asyncio.run(run(args))
    finally:
        for p in [*procs, args.primary]:
            p.terminate()
            p.wait(timeout=10)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out / "-".join(filter(None, [stamp, "failover-demo", args.label]))
    out.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with open(out / "requests.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["t_s", "worker", "status", "provider", "fallback_reason", "latency_ms"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r["t_s"]))
    seconds = timeline(rows, args.duration)
    with open(out / "timeline.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["second", "ollama", "openai", "errors"])
        writer.writeheader()
        writer.writerows(seconds)
    (out / "chart.svg").write_text(chart_svg(seconds, args.kill_at, args.restore_at))

    total = len(rows)
    errors = sum(1 for r in rows if r["status"] != 200)
    failed_over = sum(1 for r in rows if r["status"] == 200 and r["provider"] == "openai")
    lines = [
        f"Primary (ollama stand-in) killed at {args.kill_at:g} s and restarted at {args.restore_at:g} s, "
        f"{args.concurrency} requests in flight throughout.",
        "",
        f"**{total - errors:,} of {total:,} requests succeeded** ({errors} errors); "
        f"{failed_over:,} were answered by the fallback.",
        "",
        "| Second | Primary | Fallback | Errors |",
        "|---|---|---|---|",
        *(f"| {s['second']} | {s['ollama']} | {s['openai']} | {s['errors']} |" for s in seconds),
        "",
        "![requests per second by provider](chart.svg)",
    ]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))
    print(f"Results: {out}")


if __name__ == "__main__":
    main()
