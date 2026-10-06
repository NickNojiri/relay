# prompt-ops

Relay's LLM gateway (FastAPI). For each request it:

1. resolves which prompt **variant** the caller gets — via the flag engine (`app/flags.py`,
   a Python port of `@relay/flag-sdk`'s FNV-1a evaluation; Phase 4 replaces it with the
   native `flag-py` PyO3 binding),
2. loads that prompt version,
3. calls the version's provider (Ollama, Anthropic, OpenAI or any OpenAI-compatible server),
   falling back in order to the version's `fallbacks`, then `RELAY_FALLBACKS`, when a provider
   times out, can't be reached, or returns 429/5xx, and never after a stream's first token
   ([ADR 0002](../../docs/adr/0002-streaming-safe-failover.md)),
4. logs `{variant, provider, model, tokens, latency, fallback_reason}` telemetry.

Each provider keeps one pooled HTTP client for the life of the app
([ADR 0001](../../docs/adr/0001-pooled-provider-clients.md)), with its own timeouts
(`RELAY_TIMEOUTS`).

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
