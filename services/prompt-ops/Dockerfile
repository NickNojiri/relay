# Relay LLM gateway. Build context = services/prompt-ops
FROM python:3.13-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY scripts ./scripts

ENV PROMPT_OPS_PORT=8000
EXPOSE 8000

# Run uvicorn straight from the synced venv rather than via `uv run`. `uv run`
# re-reads pyproject.toml at startup, including the `native` group's source
# `../../packages/flag-py` — a path outside this build context, and above / once
# WORKDIR is /app. Newer uv rejects that ("cannot normalize a relative path
# beyond the base directory") and the container exits before binding the port.
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
