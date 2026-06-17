from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings, get_settings


@dataclass
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int


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
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def complete(self, *, model: str, system: str, user: str) -> Completion:
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return Completion(
            text=data.get("message", {}).get("content", ""),
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
        )


class AnthropicProvider:
    """Anthropic Messages API (https://api.anthropic.com/v1/messages)."""

    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport

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
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            resp = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
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

    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport

    async def complete(self, *, model: str, system: str, user: str) -> Completion:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
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


def build_provider(settings: Settings) -> LLMProvider:
    """Select a provider by config. `echo` is network-free; the rest proxy a real API."""
    provider = settings.relay_default_provider
    if provider == "echo":
        return EchoProvider()
    if provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key or "")
    if provider == "openai":
        return OpenAIProvider(settings.openai_api_key or "")
    return OllamaProvider(settings.ollama_base_url)


def get_provider() -> LLMProvider:
    """Default FastAPI dependency — overridden with EchoProvider in tests."""
    return build_provider(get_settings())
