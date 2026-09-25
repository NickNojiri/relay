from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .config import Settings, get_settings
from .flags import Decision, EvalContext, evaluate
from .routing import (
    KNOWN_PROVIDERS,
    AllProvidersFailed,
    Attempt,
    MidStreamFailure,
    ProviderRouter,
    get_router,
)
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


@app.get("/health/providers")
def provider_health(router: ProviderRouter = Depends(get_router)) -> dict:
    """Circuit state per provider, as observed from real traffic (passive health)."""
    return {"providers": router.health()}


def _target(version: PromptVersion, settings: Settings) -> tuple[str, str]:
    """The provider and model this prompt version asks for, else the defaults."""
    name = version.provider or settings.relay_default_provider
    if name not in KNOWN_PROVIDERS:
        raise HTTPException(status_code=502, detail=f"prompt version names unknown provider {name!r}")
    return name, version.model or settings.relay_default_model


def _routing(attempts: list[Attempt]) -> list[dict]:
    return [{"provider": a.provider, "outcome": a.outcome, "error": a.error} for a in attempts]


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
    router: ProviderRouter = Depends(get_router),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    version, decision = await _resolve(req, repo)
    preferred, model = _target(version, settings)

    start = time.perf_counter()
    with span("provider.complete", **{"llm.provider": preferred, "llm.model": model}) as s:
        try:
            routed = await router.complete(preferred, model, system=version.body, user=req.input)
        except AllProvidersFailed as exc:
            raise HTTPException(
                status_code=503,
                detail={"error": "no provider available", "routing": _routing(exc.attempts)},
            ) from exc
        completion = routed.completion
        set_attributes(
            s,
            **{
                "llm.served_by": routed.provider,
                "llm.fallbacks": len(routed.attempts) - 1,
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
            provider=routed.provider,
            model=routed.model,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            latency_ms=latency_ms,
        )
    )
    return ChatResponse(
        variant=decision.variant,
        provider=routed.provider,
        model=routed.model,
        output=completion.text,
        usage=Usage(
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        ),
        latency_ms=latency_ms,
        routing=_routing(routed.attempts),
    )


@app.post("/v1/chat/stream", dependencies=[Depends(gateway_guard)])
async def chat_stream(
    req: ChatRequest,
    repo: Repository = Depends(get_repository),
    router: ProviderRouter = Depends(get_router),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    version, decision = await _resolve(req, repo)
    preferred, model = _target(version, settings)

    async def event_stream() -> AsyncIterator[str]:
        start = time.perf_counter()
        parts: list[str] = []
        attempts: list[Attempt] = []
        served_by, served_model = preferred, model
        error: str | None = None
        try:
            async for served_by, served_model, chunk in router.stream(
                preferred, model, system=version.body, user=req.input, attempts=attempts
            ):
                parts.append(chunk)
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
        except AllProvidersFailed:
            error = "no provider available"
        except MidStreamFailure:
            # Part of an answer is already on the wire; it is not retried.
            error = "provider failed mid-stream"

        latency_ms = int((time.perf_counter() - start) * 1000)
        routing = _routing(attempts)
        if error is not None:
            yield f"data: {json.dumps({'error': error, 'routing': routing})}\n\n"
            return
        text = "".join(parts)
        await repo.record_telemetry(
            TelemetryEvent(
                prompt_version_id=version.id,
                flag_key=req.prompt_key,
                variant=decision.variant,
                provider=served_by,
                model=served_model,
                prompt_tokens=0,
                completion_tokens=len(text.split()),
                latency_ms=latency_ms,
            )
        )
        done = {
            "done": True,
            "variant": decision.variant,
            "provider": served_by,
            "latencyMs": latency_ms,
            "routing": routing,
        }
        yield f"data: {json.dumps(done)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
