from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import get_settings


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


class OllamaProvider:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def complete(self, *, model: str, system: str, user: str) -> Completion:
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return Completion(
            text=data.get("message", {}).get("content", ""),
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
        )


def get_provider() -> LLMProvider:
    """Default FastAPI dependency — overridden with EchoProvider in tests."""
    return OllamaProvider(get_settings().ollama_base_url)
