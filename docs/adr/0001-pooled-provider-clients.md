# ADR 0001: One pooled HTTP client per provider

**Status:** accepted · **Roadmap item:** R2

## Problem

`services/prompt-ops/app/providers.py` opened a new `httpx.AsyncClient` inside every provider
call. Each client builds its own SSL context (loading the CA bundle) and connection pool, then
throws both away, so no connection was ever reused and every call paid the setup cost.

## Evidence

`loadtest/bench.py --config loadtest/configs/ollama-stub.toml`: the gateway calls a stand-in
Ollama server that answers instantly, so the numbers are the gateway's own cost of a provider
call. Same 4-vCPU machine, medians of 3 repeats, 0 errors in every run.

| Concurrency | Before (`44eb911`) | After (`8d86307`) |
|---|---|---|
| 1 | 31 req/s · p50 28.1 ms · p99 59.5 ms | **239 req/s · p50 3.9 ms · p99 7.8 ms** |
| 10 | 34 req/s · p50 279 ms · p99 442 ms | **320 req/s · p50 29.9 ms · p99 57.5 ms** |
| 50 | 37 req/s · p50 1,354 ms | 178 req/s · p50 206 ms (past saturation; not a comparison point) |

Raw data: `services/prompt-ops/loadtest/results/*-ollama-stub-{before,after}-r2-*`.

## Decision

A `ProviderRegistry` builds each provider once, with its own `AsyncClient`, inside the FastAPI
lifespan, and closes every client on shutdown. Providers receive the client instead of
creating one. Pool limits: 100 connections, 20 kept alive, per provider.

## Rejected alternatives

- **One client shared by all providers.** Fewer objects, but timeouts and connection limits
  would have to be the same for a local Ollama and a remote API. Per-provider clients let
  failover (R3) give each provider its own timeouts.
- **Module-level global clients.** Simpler, but nothing closes them on shutdown, and tests
  can't swap them.

## Consequences

- Any code that calls a provider outside the app (scripts, tests) must build a registry or
  pass a client, and close it.
- A real model's latency (seconds) still dwarfs the 24 ms saved per call. The gain matters for
  fast providers and for gateway CPU under load: before, one worker capped out near 35 req/s
  toward any provider.
