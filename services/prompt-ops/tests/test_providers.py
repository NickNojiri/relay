import json

import httpx
import pytest

from app.config import Settings
from app.providers import (
    AnthropicProvider,
    EchoProvider,
    OllamaProvider,
    OpenAIProvider,
    build_provider,
)


def test_build_provider_selects_by_config():
    assert isinstance(build_provider(Settings(relay_default_provider="echo")), EchoProvider)
    assert isinstance(build_provider(Settings(relay_default_provider="ollama")), OllamaProvider)
    assert isinstance(
        build_provider(Settings(relay_default_provider="anthropic", anthropic_api_key="k")),
        AnthropicProvider,
    )
    assert isinstance(
        build_provider(Settings(relay_default_provider="openai", openai_api_key="k")),
        OpenAIProvider,
    )


@pytest.mark.asyncio
async def test_anthropic_request_and_parse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "secret"
        assert request.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "hi there"}],
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )

    provider = AnthropicProvider("secret", transport=httpx.MockTransport(handler))
    c = await provider.complete(model="claude-haiku-4-5", system="be terse", user="hello")
    assert c.text == "hi there"
    assert (c.prompt_tokens, c.completion_tokens) == (5, 2)


@pytest.mark.asyncio
async def test_openai_request_and_parse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "yo"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 1},
            },
        )

    provider = OpenAIProvider("secret", transport=httpx.MockTransport(handler))
    c = await provider.complete(model="gpt-4o-mini", system="s", user="u")
    assert c.text == "yo"
    assert (c.prompt_tokens, c.completion_tokens) == (7, 1)


@pytest.mark.asyncio
async def test_ollama_stream_yields_incremental_chunks():
    """The streaming path must emit deltas as they arrive, not one final blob —
    otherwise time-to-first-token equals total latency and SSE buys nothing."""
    ndjson = (
        b'{"message":{"content":"Hello"},"done":false}\n'
        b'{"message":{"content":" there"},"done":false}\n'
        b'\n'
        b'{"message":{"content":"!"},"done":false}\n'
        b'{"message":{"content":""},"done":true}\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=ndjson)

    provider = OllamaProvider("http://ollama.test", transport=httpx.MockTransport(handler))
    chunks = [c async for c in provider.stream(model="llama3.2", system="s", user="u")]
    assert chunks == ["Hello", " there", "!"]


@pytest.mark.asyncio
async def test_ollama_stream_stops_on_done_and_skips_malformed_lines():
    ndjson = (
        b'not-json\n'
        b'{"message":{"content":"a"},"done":false}\n'
        b'{"message":{"content":""},"done":true}\n'
        b'{"message":{"content":"never"},"done":false}\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson)

    provider = OllamaProvider("http://ollama.test", transport=httpx.MockTransport(handler))
    chunks = [c async for c in provider.stream(model="m", system="s", user="u")]
    assert chunks == ["a"]


def _sse(*events: str) -> bytes:
    return "".join(f"data: {e}\n\n" for e in events).encode()


@pytest.mark.asyncio
async def test_anthropic_stream_yields_text_deltas():
    body = (
        b"event: message_start\n"
        + _sse('{"type":"message_start","message":{}}')
        + _sse('{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}')
        + _sse('{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hel"}}')
        + _sse('{"type":"ping"}')
        + _sse('{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"lo"}}')
        + _sse('{"type":"message_stop"}')
        + _sse('{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"never"}}')
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=body)

    provider = AnthropicProvider("secret", transport=httpx.MockTransport(handler))
    chunks = [c async for c in provider.stream(model="m", system="s", user="u")]
    assert chunks == ["Hel", "lo"]


@pytest.mark.asyncio
async def test_anthropic_in_stream_error_raises_a_retryable_status():
    body = _sse('{"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}')
    provider = AnthropicProvider(
        "secret", transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    )
    with pytest.raises(httpx.HTTPStatusError) as info:
        [c async for c in provider.stream(model="m", system="s", user="u")]
    assert info.value.response.status_code == 529


@pytest.mark.asyncio
async def test_openai_stream_yields_deltas_until_done():
    body = _sse(
        '{"choices":[{"delta":{"role":"assistant"}}]}',
        '{"choices":[{"delta":{"content":"yo"}}]}',
        "not-json",
        '{"choices":[{"delta":{"content":" there"}}]}',
        '{"choices":[{"delta":{},"finish_reason":"stop"}]}',
        "[DONE]",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=body)

    provider = OpenAIProvider("secret", transport=httpx.MockTransport(handler))
    chunks = [c async for c in provider.stream(model="m", system="s", user="u")]
    assert chunks == ["yo", " there"]


@pytest.mark.asyncio
async def test_stream_raises_on_http_error_so_the_router_can_fail_over():
    provider = OpenAIProvider(
        "secret", transport=httpx.MockTransport(lambda r: httpx.Response(503))
    )
    with pytest.raises(httpx.HTTPStatusError):
        [c async for c in provider.stream(model="m", system="s", user="u")]


@pytest.mark.asyncio
async def test_a_provider_reuses_one_http_client_across_requests():
    """A client per request cost ~60 ms of TLS setup each and capped a worker near
    16 req/s; the provider must build it once."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "ok"}})

    provider = OllamaProvider("http://ollama.test", transport=httpx.MockTransport(handler))
    for _ in range(3):
        await provider.complete(model="m", system="s", user="u")
        seen.append(provider.client)
    assert seen[0] is seen[1] is seen[2]

    await provider.aclose()
    assert seen[0].is_closed
