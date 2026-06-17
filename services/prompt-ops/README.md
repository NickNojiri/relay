# prompt-ops

Relay's LLM gateway (FastAPI). For each request it:

1. resolves which prompt **variant** the caller gets — via the flag engine (`app/flags.py`,
   a Python port of `@relay/flag-sdk`'s FNV-1a evaluation; Phase 4 replaces it with the
   native `flag-py` PyO3 binding),
2. loads that prompt version,
3. proxies the completion to a provider (Ollama by default; OpenAI/Anthropic later),
4. logs `{variant, provider, model, tokens, latency}` telemetry.

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
