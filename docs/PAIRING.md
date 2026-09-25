# Pairing — Claude Code and Codex on Relay

Two agents, one repo. Each one owns a **lane** (a set of files). Don't edit a file in the
other agent's lane until that lane's branch has merged. If you need a change there, write
it under "Asks" below and hand it over.

The shared base is the branch named below, not `main`. `main` and
`claude/resume-project-planning-qvj08h` had split apart; they were merged back together in
`76eb8f4`, and that merge is the base both lanes start from.

## Live state

```text
BASE:            claude/relay-provider-resilience @ 76eb8f4 (the merge commit)
TESTS:           prompt-ops: uv run pytest -> 52 passed, 3 skipped
LANE 1 (Claude): DONE, awaiting review. Failover, breakers, timeouts, passive health,
                 streaming on all four providers, graceful shutdown (real SIGTERM test),
                 pooled provider clients (16 -> 346 req/s), re-benchmark with raw
                 results in services/prompt-ops/loadtest/results/
LANE 2 (Codex):  observability: request IDs, Prometheus /metrics, Grafana: NOT STARTED
```

## Lanes

| Lane | Owner | Roadmap items | Files it owns |
|---|---|---|---|
| 1 Reliability | Claude Code | per-provider timeouts, circuit breakers, no retry on partial streams, passive health, failover routing, provider-failure test, streaming on all providers, graceful shutdown, load test rerun | `app/routing.py`, `app/providers.py`, the `/v1/chat*` handlers, `/health/providers` and the lifespan in `app/main.py`, `tests/test_routing.py`, `tests/test_shutdown.py`, `loadtest/` |
| 2 Observability | Codex | request IDs and trace-context propagation, Prometheus metrics (latency, tokens, provider errors, routing decisions), Grafana dashboard | new `app/request_id.py`, new `app/metrics.py`, new `infra/grafana/`, `tests/test_metrics.py`, the middleware and `/metrics` lines in `app/main.py` just after `instrument_app(app)` |

`app/main.py` is shared. Lane 1 touches only the route handlers. Lane 2 touches only the
app-setup block at the top (middleware, `/metrics`). Keep your edits inside your own block.

## Asks between lanes

- **To Codex, from Claude.** Routing decisions are already exposed, so you don't need to
  edit `routing.py`. `Routed.attempts`, `AllProvidersFailed.attempts` and the stream's
  `attempts` list each hold `Attempt(provider, model, outcome, error)`, and
  `ProviderRouter.health()` returns the breaker states. Build the metrics from those in the
  handlers' callers, or ask for a hook here.

## Not yet claimed

Active health probes (they would spend paid-API calls, so they need a budget decision
first), cost- or latency-based routing, a data-retention doc, Rust profiling (the Rust
code is only the flag decision, and only in native builds), Kubernetes. After Lane 2
lands, rerun `loadtest/run_all.sh` to measure what /metrics costs.
Claim one here before starting it.
