"""Stand-in LLM server for load tests: answers Ollama's /api/chat and the OpenAI-compatible
/v1/chat/completions instantly (plus an optional fixed delay), so a benchmark measures the
gateway's own HTTP handling rather than a model.

    STUB_DELAY_MS=0 uv run uvicorn loadtest.stub_upstream:app --port 8766
"""

from __future__ import annotations

import asyncio
import json
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

DELAY_S = float(os.environ.get("STUB_DELAY_MS", "0")) / 1000
REPLY = "ok from stub"


async def _wait() -> None:
    if DELAY_S:
        await asyncio.sleep(DELAY_S)


async def ollama_chat(request: Request) -> Response:
    body = await request.json()
    await _wait()
    if body.get("stream"):
        async def lines():
            for word in REPLY.split():
                yield json.dumps({"message": {"content": word + " "}, "done": False}) + "\n"
            yield json.dumps({"message": {"content": ""}, "done": True}) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")
    return JSONResponse(
        {"message": {"content": REPLY}, "prompt_eval_count": 3, "eval_count": 3, "done": True}
    )


async def openai_chat(request: Request) -> Response:
    await request.json()
    await _wait()
    return JSONResponse(
        {
            "choices": [{"message": {"content": REPLY}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 3},
        }
    )


async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/api/chat", ollama_chat, methods=["POST"]),
        Route("/v1/chat/completions", openai_chat, methods=["POST"]),
        Route("/health", health),
    ]
)
