from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .flags import FlagRule, FlagVariant


@dataclass
class PromptVersion:
    id: str
    prompt_key: str
    version: int
    body: str
    provider: str | None = None
    model: str | None = None


@dataclass
class TelemetryEvent:
    prompt_version_id: str | None
    flag_key: str | None
    variant: str | None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class Repository(Protocol):
    async def get_flag(self, key: str) -> FlagRule | None: ...
    async def get_prompt_version(self, version_id: str) -> PromptVersion | None: ...
    async def get_default_version_id(self, prompt_key: str) -> str | None: ...
    async def record_telemetry(self, event: TelemetryEvent) -> None: ...


class InMemoryRepository:
    """Standalone repo for tests + the seeded demo. A Postgres-backed impl arrives
    once apps/studio is writing prompts/flags (same Protocol, drop-in)."""

    def __init__(self) -> None:
        self.flags: dict[str, FlagRule] = {}
        self.versions: dict[str, PromptVersion] = {}
        self.telemetry: list[TelemetryEvent] = []

    async def get_flag(self, key: str) -> FlagRule | None:
        return self.flags.get(key)

    async def get_prompt_version(self, version_id: str) -> PromptVersion | None:
        return self.versions.get(version_id)

    async def get_default_version_id(self, prompt_key: str) -> str | None:
        candidates = [v for v in self.versions.values() if v.prompt_key == prompt_key]
        if not candidates:
            return None
        return max(candidates, key=lambda v: v.version).id

    async def record_telemetry(self, event: TelemetryEvent) -> None:
        self.telemetry.append(event)


def seed_demo() -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.versions["v1"] = PromptVersion(
        "v1", "prompt.support-bot", 1, "You are a terse support agent.", "ollama", "llama3.2"
    )
    repo.versions["v2"] = PromptVersion(
        "v2", "prompt.support-bot", 2, "You are a warm, empathetic support agent.", "ollama", "llama3.2"
    )
    repo.flags["prompt.support-bot"] = FlagRule(
        key="prompt.support-bot",
        enabled=True,
        rollout_bps=10000,
        variants=[FlagVariant("A", 5000, "v1"), FlagVariant("B", 5000, "v2")],
    )
    return repo


_default_repo = seed_demo()


def get_repository() -> Repository:
    """Default FastAPI dependency — overridden with a fresh repo in tests."""
    return _default_repo
