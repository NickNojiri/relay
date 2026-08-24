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
