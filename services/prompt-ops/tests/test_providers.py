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
