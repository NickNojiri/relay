from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException

from .config import Settings, get_settings
from .flags import Decision, EvalContext, evaluate
from .providers import LLMProvider, get_provider
from .repository import Repository, TelemetryEvent, get_repository, set_pool
from .schemas import ChatRequest, ChatResponse, Usage


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    repo: Repository = Depends(get_repository),
    provider: LLMProvider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    flag = await repo.get_flag(req.prompt_key)
    decision: Decision = (
        evaluate(flag, EvalContext(unit_id=req.unit_id))
        if flag is not None
        else Decision(False, None, "flag_disabled")
    )

    # Map the chosen variant to its prompt version; fall back to the latest version.
    version_id: str | None = None
    if flag is not None and decision.variant is not None:
        version_id = next(
            (v.prompt_version_id for v in flag.variants if v.key == decision.variant),
            None,
        )
    if version_id is None:
        version_id = await repo.get_default_version_id(req.prompt_key)

    version = await repo.get_prompt_version(version_id) if version_id else None
    if version is None:
        raise HTTPException(status_code=404, detail="no prompt version available")

    provider_name = version.provider or settings.relay_default_provider
    model = version.model or settings.relay_default_model

    start = time.perf_counter()
    completion = await provider.complete(model=model, system=version.body, user=req.input)
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
