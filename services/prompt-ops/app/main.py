from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from . import failover
from .config import Settings, get_settings
from .failover import AllRoutesFailed, ProviderError, Route
from .flags import Decision, EvalContext, evaluate
from .providers import ProviderRegistry, get_providers
from .repository import (
    PromptVersion,
    Repository,
    TelemetryEvent,
    get_repository,
    parse_routes,
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
    app.state.providers = ProviderRegistry(settings)
    yield
    await app.state.providers.aclose()
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


def _routes(version: PromptVersion, settings: Settings) -> list[Route]:
    primary = Route(
        version.provider or settings.relay_default_provider,
        version.model or settings.relay_default_model,
    )
    chain = [primary, *version.fallbacks, *parse_routes(settings.relay_fallbacks)]
    return list(dict.fromkeys(chain))


def _bad_gateway(exc: AllRoutesFailed | ProviderError) -> HTTPException:
    return HTTPException(
        status_code=502, detail={"error": "no provider could answer", "attempts": exc.attempts}
    )


@app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(gateway_guard)])
async def chat(
    req: ChatRequest,
    repo: Repository = Depends(get_repository),
    providers: ProviderRegistry = Depends(get_providers),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    version, decision = await _resolve(req, repo)
    routes = _routes(version, settings)

    start = time.perf_counter()
    with span("provider.complete", **{"llm.provider": routes[0].provider, "llm.model": routes[0].model}) as s:
        try:
            route, completion, skipped = await failover.complete(
                routes, providers, system=version.body, user=req.input
            )
        except (AllRoutesFailed, ProviderError) as exc:
            raise _bad_gateway(exc) from exc
        set_attributes(
            s,
            **{
                "llm.served_by": str(route),
                "llm.prompt_tokens": completion.prompt_tokens,
                "llm.completion_tokens": completion.completion_tokens,
            },
        )
    latency_ms = int((time.perf_counter() - start) * 1000)
    fallback_reason = "; ".join(skipped) or None

    await repo.record_telemetry(
        TelemetryEvent(
            prompt_version_id=version.id,
            flag_key=req.prompt_key,
            variant=decision.variant,
            provider=route.provider,
            model=route.model,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            latency_ms=latency_ms,
            fallback_reason=fallback_reason,
        )
    )
    return ChatResponse(
        variant=decision.variant,
        provider=route.provider,
        model=route.model,
        output=completion.text,
        usage=Usage(
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        ),
        latency_ms=latency_ms,
        fallback_reason=fallback_reason,
    )


@app.post("/v1/chat/stream", dependencies=[Depends(gateway_guard)])
async def chat_stream(
    req: ChatRequest,
    repo: Repository = Depends(get_repository),
    providers: ProviderRegistry = Depends(get_providers),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    version, decision = await _resolve(req, repo)
    start = time.perf_counter()
    # Failover happens here, before the response starts; once a chunk is sent it's final.
    try:
        opened = await failover.open_stream(
            _routes(version, settings), providers, system=version.body, user=req.input
        )
    except (AllRoutesFailed, ProviderError) as exc:
        raise _bad_gateway(exc) from exc
    fallback_reason = "; ".join(opened.skipped) or None

    async def event_stream() -> AsyncIterator[str]:
        parts = [opened.first]
        if opened.first:
            yield f"data: {json.dumps({'delta': opened.first})}\n\n"
        error = None
        if opened.rest is not None:
            try:
                async for chunk in opened.rest:
                    parts.append(chunk)
                    yield f"data: {json.dumps({'delta': chunk})}\n\n"
            except httpx.HTTPError as exc:
                error = f"{opened.route}: stream interrupted ({failover.describe(exc)})"

        latency_ms = int((time.perf_counter() - start) * 1000)
        text = "".join(parts)
        await repo.record_telemetry(
            TelemetryEvent(
                prompt_version_id=version.id,
                flag_key=req.prompt_key,
                variant=decision.variant,
                provider=opened.route.provider,
                model=opened.route.model,
                prompt_tokens=0,
                completion_tokens=len(text.split()),
                latency_ms=latency_ms,
                fallback_reason=fallback_reason,
            )
        )
        done = {"done": True, "variant": decision.variant, "latencyMs": latency_ms, "servedBy": str(opened.route)}
        if fallback_reason:
            done["fallbackReason"] = fallback_reason
        if error:
            done["error"] = error
        yield f"data: {json.dumps(done)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
