import json

import httpx
import pytest

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.providers import (
    AnthropicProvider,
    EchoProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderRegistry,
)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_registry_builds_each_provider_once():
    registry = ProviderRegistry(Settings(anthropic_api_key="k", openai_api_key="k"))
    assert isinstance(registry.get("echo"), EchoProvider)
    assert isinstance(registry.get("ollama"), OllamaProvider)
    assert isinstance(registry.get("anthropic"), AnthropicProvider)
    assert isinstance(registry.get("openai"), OpenAIProvider)
    assert registry.get("ollama") is registry.get("ollama")


@pytest.mark.asyncio
async def test_provider_calls_reuse_the_registry_client(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "hi"}, "done": True})

    registry = ProviderRegistry(
        Settings(ollama_base_url="http://ollama.test"), transport=httpx.MockTransport(handler)
    )
    provider = registry.get("ollama")
    created = []
    original_init = httpx.AsyncClient.__init__

    def counting_init(self, *args, **kwargs):
        created.append(1)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", counting_init)
    for _ in range(3):
        await provider.complete(model="m", system="s", user="u")
    async for _ in provider.stream(model="m", system="s", user="u"):
        pass
    assert created == []
    await registry.aclose()


def test_app_lifespan_opens_and_closes_provider_clients():
    with TestClient(app):
        registry = app.state.providers
        ollama = registry.get("ollama")
    assert ollama._client.is_closed


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

    provider = AnthropicProvider("secret", _client(handler))
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

    provider = OpenAIProvider("secret", _client(handler))
    c = await provider.complete(model="gpt-4o-mini", system="s", user="u")
    assert c.text == "yo"
    assert (c.prompt_tokens, c.completion_tokens) == (7, 1)


@pytest.mark.asyncio
async def test_openai_compatible_server_without_a_key_gets_no_auth_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "llm.local"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"choices": [{"message": {"content": "local"}}], "usage": {}})

    provider = OpenAIProvider("", _client(handler), base_url="http://llm.local")
    assert (await provider.complete(model="m", system="s", user="u")).text == "local"


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

    provider = OllamaProvider("http://ollama.test", _client(handler))
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

    provider = OllamaProvider("http://ollama.test", _client(handler))
    chunks = [c async for c in provider.stream(model="m", system="s", user="u")]
    assert chunks == ["a"]
