# prompt-ops

Relay's LLM gateway (FastAPI). For each request it:

1. resolves which prompt **variant** the caller gets — via the flag engine (`app/flags.py`,
   a Python port of `@relay/flag-sdk`'s FNV-1a evaluation; Phase 4 replaces it with the
   native `flag-py` PyO3 binding),
2. loads that prompt version,
3. proxies the completion to the version's provider (else the default), failing over to
   the next healthy provider if it is down — see **Provider routing** below,
4. logs `{variant, provider, model, tokens, latency}` telemetry, naming the provider that
   actually served the request.

## Run

```bash
uv sync                       # create venv + install deps
uv run pytest                 # tests (no network — uses EchoProvider + in-memory repo)
uv run uvicorn app.main:app --reload --port 8000
# then: POST /v1/chat {"prompt_key":"prompt.support-bot","unit_id":"user-42","input":"hi"}
```

The default in-memory repository is seeded with a demo `prompt.support-bot` flag that
splits 50/50 between two prompt versions, so the service is runnable standalone before
`apps/studio` writes real prompts/flags to Postgres.

## Provider routing (`app/routing.py`)

- **Order.** The prompt version's provider first, then `RELAY_FALLBACK_CHAIN`
  (`provider:model,...`). With no chain set, a request gets one provider and one try.
- **Timeouts.** Every attempt is capped at `RELAY_PROVIDER_TIMEOUT_S`. For a stream the cap
  is on the time to the first chunk, so a long answer is not cut off.
- **Circuit breakers.** Each provider has one. `RELAY_BREAKER_FAILURES` failures in a row
  open it, and while it is open the provider is skipped without being called. After
  `RELAY_BREAKER_RESET_S` a single trial request goes through: success closes the circuit,
  failure reopens it. `GET /health/providers` shows the state of every circuit.
- **What fails over.** A timeout, a connection error, a 429 or a 5xx. Any other 4xx means
  the request or our credentials are wrong. It would fail the same way on every provider,
  so it is returned as-is and does not count against the breaker.
- **Streams never retry after the first chunk.** The client already has part of one
  provider's answer, so a mid-stream failure ends the stream with an
  `{"error": "provider failed mid-stream"}` event instead of splicing in another answer.
- **Visible.** `/v1/chat` returns `routing: [{provider, outcome, error}]` and the stream's
  final event carries the same list; the OTel `provider.complete` span records
  `llm.served_by` and `llm.fallbacks`. Errors are recorded as a class (`HTTP 503`,
  `timeout`, `ConnectError`), never as prompt text.

All four providers stream real tokens (Ollama NDJSON; Anthropic and OpenAI SSE), and each
provider reuses one pooled HTTP client, which is closed at shutdown.

## Graceful shutdown

On SIGTERM uvicorn stops accepting connections, lets in-flight requests and open streams
finish for up to 30 s (`--timeout-graceful-shutdown 30` in the Dockerfile), then closes
the provider clients and the database pool. `fly.toml` sends SIGTERM and waits 35 s, so
Fly doesn't cut a stream off mid-answer. `tests/test_shutdown.py` runs a real uvicorn,
sends SIGTERM mid-stream, and checks that the stream completes and new connections are
refused.

Breaker state lives in the process, so with several gateway instances each one keeps its
own breakers. That fits a single-instance deploy; a shared store would be needed to scale
out.
