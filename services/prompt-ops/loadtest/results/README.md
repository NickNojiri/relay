# Gateway load-test results

Raw output of `loadtest/run_all.sh` (one JSON file per run), measured 2026-09-25 on
commit `claude/relay-provider-resilience`.

## Setup

| | |
|---|---|
| Machine | 4 vCPU Intel Xeon @ 2.80 GHz, 15 GB RAM, Linux 6.18 (a cloud dev container) |
| Software | Python 3.11.15, uvicorn 0.49.0 (1 worker), FastAPI 0.137.1, httpx 0.28.1 |
| Workload | `loadtest/bench.py`: closed loop, N concurrent clients, `POST /v1/chat` on the seeded `prompt.support-bot` flag (50/50 A/B), random `unit_id`, 20 s per run, 3 runs per cell |
| Healthy | The version's provider (`ollama`) answered by `stub_ollama.py`, an instant fake Ollama on the same machine: every request makes a real HTTP call through the provider |
| Failover | Ollama pointed at a closed port, `RELAY_FALLBACK_CHAIN=echo:echo`: the first 3 requests fail, the circuit opens, and every later request skips Ollama and is served by `echo` |

The gateway, the stub, and the load generator share the same 4 vCPUs, so these numbers
measure the gateway's own overhead on one worker. They are **not** production numbers and
leave out model latency entirely.

## Results (mean of 3 runs; range in brackets)

| Scenario | Concurrency | Throughput | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|---|
| Healthy | 10 | 346 req/s [344–347] | 27.6 ms | 38.6 ms | 47.3 ms | 0 / 20,769 |
| Healthy | 50 | 225 req/s [191–244] | 153 ms | 661 ms | 1,092 ms | 0 / 13,599 |
| Failover (primary down) | 10 | 594 req/s [589–601] | 10.4 ms | 51.2 ms | 92.9 ms | 0 / 35,635 |
| Failover (primary down) | 50 | 307 req/s [293–326] | 105 ms | 487 ms | 900 ms | 0 / 18,522 |

Every failover run ended with `ollama` open and `echo` closed in `GET /health/providers`
(`*.health.json`): no request was lost to the dead provider after the circuit opened.

## What the numbers found

- **A client per request capped the gateway at ~16 req/s.** Before this branch every
  provider call built a new `httpx.AsyncClient`, and building one costs about 64 ms of
  CPU for the TLS context. One 20 s run of the healthy path on the old code measured
  16 req/s at a 618 ms p50 (c=10); that run's output was not kept. With one pooled client per provider: 346 req/s at 27.6 ms, about 21× the
  throughput. The earlier README figure (623 req/s) never saw this cost, because a bug
  sent every request to `echo` whatever provider the prompt version named.
- **One worker saturates by c=50.** Throughput falls and tail latency grows, as it did
  before. The next step is more uvicorn workers, which would split the circuit breakers
  across processes (see `app/routing.py`).
- **Failover is cheaper than a healthy call** here, because `echo` makes no network hop.
  It shows that an open circuit adds no measurable delay, not that failover is fast in
  general.
