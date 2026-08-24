"""Measures streaming time-to-first-token vs blocking full-response latency
(resume metric #2).

Compares POST /v1/chat (wait for the whole completion) against
POST /v1/chat/stream (SSE, first token as soon as it exists). The point of the
streaming path is perceived latency, so TTFT is the number that matters.

Usage:
    # terminal A - real provider, not EchoProvider (echo returns instantly and
    # would make TTFT meaningless). Ollama is the cheapest honest option:
    ollama serve && ollama pull llama3.2
    cd services/prompt-ops && uv run uvicorn app.main:app --port 8000

    # terminal B
    uv run python bench/bench_ttft.py

Env:
    RELAY_GATEWAY   base URL (default http://localhost:8000)
    BENCH_N         runs per arm (default 20)
    BENCH_PROMPT    prompt_key (default prompt.support-bot)
"""

import json
import os
import statistics
import sys
import time

try:
    import httpx
except ImportError:
    sys.exit("httpx required: uv add httpx")

BASE = os.environ.get("RELAY_GATEWAY", "http://localhost:8000")
N = int(os.environ.get("BENCH_N", "20"))
PROMPT = os.environ.get("BENCH_PROMPT", "prompt.support-bot")
PAYLOAD = {
    "prompt_key": PROMPT,
    "unit_id": "bench-user",
    "input": "Summarize why my order might be delayed.",
}


def pct(s: list[float], p: float) -> float:
    return sorted(s)[min(int(len(s) * p), len(s) - 1)]


def bench_blocking(client: httpx.Client) -> list[float]:
    """Full round-trip latency for the non-streaming endpoint."""
    out = []
    for i in range(N):
        body = dict(PAYLOAD, unit_id=f"bench-{i}")
        t0 = time.perf_counter()
        r = client.post(f"{BASE}/v1/chat", json=body, timeout=120)
        r.raise_for_status()
        out.append((time.perf_counter() - t0) * 1000)
    return out


def bench_stream(client: httpx.Client) -> tuple[list[float], list[float]]:
    """Returns (time_to_first_token, time_to_done) in ms."""
    ttft, total = [], []
    for i in range(N):
        body = dict(PAYLOAD, unit_id=f"bench-{i}")
        t0 = time.perf_counter()
        first = None
        with client.stream(
            "POST", f"{BASE}/v1/chat/stream", json=body, timeout=120
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = json.loads(line[5:].strip())
                # skip the terminal {"done": true} frame when timing first token
                if first is None and not chunk.get("done"):
                    first = (time.perf_counter() - t0) * 1000
        total.append((time.perf_counter() - t0) * 1000)
        ttft.append(first if first is not None else float("nan"))
    return ttft, total


def main() -> None:
    with httpx.Client() as client:
        try:
            client.get(f"{BASE}/health", timeout=5)
        except Exception:
            sys.exit(f"gateway not reachable at {BASE} - start it first")

        print(f"\nStreaming vs blocking, {N} runs each (prompt={PROMPT})\n")
        blocking = bench_blocking(client)
        ttft, stream_total = bench_stream(client)

        b_p50, t_p50 = pct(blocking, 0.5), pct(ttft, 0.5)
        print(f"  blocking /v1/chat  full response  p50 {b_p50:8.1f} ms | p95 {pct(blocking,0.95):8.1f}")
        print(f"  stream   TTFT      first token    p50 {t_p50:8.1f} ms | p95 {pct(ttft,0.95):8.1f}")
        print(f"  stream   complete  all tokens     p50 {pct(stream_total,0.5):8.1f} ms")

        speedup = b_p50 / t_p50 if t_p50 else float("inf")
        print(
            f"\n  => first token arrives {speedup:.1f}x sooner than the blocking "
            f"response ({t_p50:.0f} ms vs {b_p50:.0f} ms p50)"
        )
        print(
            f"  => resume line: \"cut perceived latency {(1 - t_p50/b_p50)*100:.0f}% "
            f"by streaming first token at {t_p50:.0f} ms p50 vs {b_p50:.0f} ms "
            f"for the full response\"\n"
        )
        print(f"  (mean TTFT {statistics.mean(ttft):.1f} ms over {N} runs)\n")


if __name__ == "__main__":
    main()
