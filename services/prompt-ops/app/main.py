from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .config import Settings, get_settings
from .flags import Decision, EvalContext, evaluate
from .providers import LLMProvider, get_provider
from .repository import (
    PromptVersion,
    Repository,
    TelemetryEvent,
    get_repository,
    set_pool,
)
from .schemas import ChatRequest, ChatResponse, Usage
from .security import gateway_guard
from .telemetry_otel import init_tracing, instrument_app, set_attributes, span


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = None
    if settings.relay_db_enabled:
        import asyncpg

        pool = await asyncpg.create_pool(dsn=settings.database_url)
        set_pool(pool)
    yield
    if pool is not None:
        await pool.close()


app = FastAPI(title="Relay prompt-ops", version="0.1.0", lifespan=lifespan)
# Opt-in distributed tracing (RELAY_OTEL_ENABLED); no-op otherwise.
init_tracing(get_settings())
instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _resolve(req: ChatRequest, repo: Repository) -> tuple[PromptVersion, Decision]:
    """Pick the variant via the flag engine and load its prompt version."""
    with span("flag.resolve", **{"flag.key": req.prompt_key, "flag.unit_id": req.unit_id}) as s:
        flag = await repo.get_flag(req.prompt_key)
        decision = (
            evaluate(flag, EvalContext(unit_id=req.unit_id))
            if flag is not None
            else Decision(False, None, "flag_disabled")
        )
        set_attributes(s, **{"flag.variant": decision.variant, "flag.reason": decision.reason})
    version_id: str | None = None
    if flag is not None and decision.variant is not None:
        version_id = next(
            (v.prompt_version_id for v in flag.variants if v.key == decision.variant), None
        )
    if version_id is None:
        version_id = await repo.get_default_version_id(req.prompt_key)
    version = await repo.get_prompt_version(version_id) if version_id else None
    if version is None:
        raise HTTPException(status_code=404, detail="no prompt version available")
    return version, decision


@app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(gateway_guard)])
async def chat(
    req: ChatRequest,
    repo: Repository = Depends(get_repository),
    provider: LLMProvider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    version, decision = await _resolve(req, repo)
    provider_name = version.provider or settings.relay_default_provider
    model = version.model or settings.relay_default_model

    start = time.perf_counter()
    with span("provider.complete", **{"llm.provider": provider_name, "llm.model": model}) as s:
        completion = await provider.complete(model=model, system=version.body, user=req.input)
        set_attributes(
            s,
            **{
                "llm.prompt_tokens": completion.prompt_tokens,
                "llm.completion_tokens": completion.completion_tokens,
            },
        )
    latency_ms = int((time.perf_counter() - start) * 1000)

    await repo.record_telemetry(
        TelemetryEvent(
            prompt_version_id=version.id,
            flag_key=req.prompt_key,
            variant=decision.variant,
            provider=provider_name,
            model=model,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            latency_ms=latency_ms,
        )
    )
    return ChatResponse(
        variant=decision.variant,
        provider=provider_name,
        model=model,
        output=completion.text,
        usage=Usage(
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        ),
        latency_ms=latency_ms,
    )


@app.post("/v1/chat/stream", dependencies=[Depends(gateway_guard)])
async def chat_stream(
    req: ChatRequest,
    repo: Repository = Depends(get_repository),
    provider: LLMProvider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    version, decision = await _resolve(req, repo)
    provider_name = version.provider or settings.relay_default_provider
    model = version.model or settings.relay_default_model

    async def event_stream() -> AsyncIterator[str]:
        start = time.perf_counter()
        parts: list[str] = []
        stream = getattr(provider, "stream", None)
        if stream is not None:
            async for chunk in stream(model=model, system=version.body, user=req.input):
                parts.append(chunk)
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
        else:
            completion = await provider.complete(model=model, system=version.body, user=req.input)
            parts.append(completion.text)
            yield f"data: {json.dumps({'delta': completion.text})}\n\n"

        latency_ms = int((time.perf_counter() - start) * 1000)
        text = "".join(parts)
        await repo.record_telemetry(
            TelemetryEvent(
                prompt_version_id=version.id,
                flag_key=req.prompt_key,
                variant=decision.variant,
                provider=provider_name,
                model=model,
                prompt_tokens=0,
                completion_tokens=len(text.split()),
                latency_ms=latency_ms,
            )
        )
        yield f"data: {json.dumps({'done': True, 'variant': decision.variant, 'latencyMs': latency_ms})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
