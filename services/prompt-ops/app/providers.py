from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import httpx
from fastapi import Request

from .config import Settings


@dataclass
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int


class ProviderUnavailable(Exception):
    """The registry can't offer this provider at all (unknown name, or no API key)."""

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"{name}: {reason}")
        self.reason = reason


@dataclass(frozen=True)
class Timeouts:
    connect: float
    read: float


# A local Ollama may need a long first read while it loads a model into memory.
DEFAULT_TIMEOUTS = {
    "ollama": Timeouts(connect=3.0, read=120.0),
    "anthropic": Timeouts(connect=5.0, read=60.0),
    "openai": Timeouts(connect=5.0, read=60.0),
}


class LLMProvider(Protocol):
    async def complete(self, *, model: str, system: str, user: str) -> Completion: ...


class EchoProvider:
    """Deterministic, network-free provider for tests and local demos."""

    async def complete(self, *, model: str, system: str, user: str) -> Completion:
        text = f"[{model}] system={system!r} -> {user}"
        return Completion(
            text=text,
            prompt_tokens=len(system.split()) + len(user.split()),
            completion_tokens=len(user.split()),
        )

    async def stream(self, *, model: str, system: str, user: str):
        for token in user.split():
            yield token + " "


class OllamaProvider:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def complete(self, *, model: str, system: str, user: str) -> Completion:
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = await self._client.post(f"{self._base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return Completion(
            text=data.get("message", {}).get("content", ""),
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
        )

    async def stream(self, *, model: str, system: str, user: str):
        """Yields content deltas as Ollama produces them.

        Ollama's streaming mode returns newline-delimited JSON, one object per
        token-ish chunk. Without this, /v1/chat/stream falls back to complete()
        and emits the whole response as a single frame — which is SSE in shape
        only: time-to-first-token equals total latency.
        """
        payload = {
            "model": model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with self._client.stream("POST", f"{self._base_url}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break


class AnthropicProvider:
    """Anthropic Messages API (https://api.anthropic.com/v1/messages)."""

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._client = client

    async def complete(self, *, model: str, system: str, user: str) -> Completion:
        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        resp = await self._client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        return Completion(
            text=text,
            prompt_tokens=int(usage.get("input_tokens", 0)),
            completion_tokens=int(usage.get("output_tokens", 0)),
        )


class OpenAIProvider:
    """OpenAI Chat Completions API."""

    def __init__(
        self, api_key: str, client: httpx.AsyncClient, base_url: str = "https://api.openai.com"
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def complete(self, *, model: str, system: str, user: str) -> Completion:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        resp = await self._client.post(
            f"{self._base_url}/v1/chat/completions", headers=headers, json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or [{}]
        text = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return Completion(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )


class ProviderRegistry:
    """One instance per provider, each holding a pooled httpx client for the app's lifetime.

    Built in the FastAPI lifespan and closed on shutdown. Creating an AsyncClient per call
    rebuilds its SSL context and connection pool every time, which dominated the cost of a
    provider call.
    """

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        providers: dict[str, LLMProvider] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._providers: dict[str, LLMProvider] = dict(providers or {})
        self._clients: list[httpx.AsyncClient] = []

    def get(self, name: str) -> LLMProvider:
        if name not in self._providers:
            self._providers[name] = self._build(name)
        return self._providers[name]

    def timeouts(self, name: str) -> Timeouts:
        override = self._settings.relay_timeouts.get(name, {})
        default = DEFAULT_TIMEOUTS.get(name, Timeouts(connect=5.0, read=60.0))
        return Timeouts(
            connect=override.get("connect", default.connect), read=override.get("read", default.read)
        )

    def _client(self, name: str) -> httpx.AsyncClient:
        t = self.timeouts(name)
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(t.read, connect=t.connect),
            transport=self._transport,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self._clients.append(client)
        return client

    def _build(self, name: str) -> LLMProvider:
        s = self._settings
        if name == "echo":
            return EchoProvider()
        if name == "ollama":
            return OllamaProvider(s.ollama_base_url, self._client(name))
        if name == "anthropic":
            if not s.anthropic_api_key:
                raise ProviderUnavailable(name, "not_configured")
            return AnthropicProvider(s.anthropic_api_key, self._client(name))
        if name == "openai":
            # A self-hosted OpenAI-compatible server may not need a key.
            if not s.openai_api_key and s.openai_base_url == "https://api.openai.com":
                raise ProviderUnavailable(name, "not_configured")
            return OpenAIProvider(s.openai_api_key or "", self._client(name), s.openai_base_url)
        raise ProviderUnavailable(name, "unknown_provider")

    async def aclose(self) -> None:
        for client in self._clients:
            await client.aclose()


def get_providers(request: Request) -> ProviderRegistry:
    """FastAPI dependency: the registry built in the app lifespan. Tests override it."""
    return request.app.state.providers
