from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

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
    """Standalone repo for tests + the seeded demo (no DB required)."""

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


def _parse_variants(raw: Any) -> list[FlagVariant]:
    items = json.loads(raw) if isinstance(raw, str) else (raw or [])
    # Stored by studio via Drizzle in the TS FlagVariant shape (camelCase keys).
    return [FlagVariant(v["key"], v["weightBps"], v.get("promptVersionId")) for v in items]


class PostgresRepository:
    """Reads prompts/flags and writes telemetry against the shared Postgres
    (same schema @relay/db owns). Used when RELAY_DB_ENABLED is set."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def get_flag(self, key: str) -> FlagRule | None:
        row = await self._pool.fetchrow(
            "SELECT key, enabled, rollout_bps, variants FROM flags WHERE key = $1", key
        )
        if row is None:
            return None
        return FlagRule(
            key=row["key"],
            enabled=row["enabled"],
            rollout_bps=row["rollout_bps"],
            variants=_parse_variants(row["variants"]),
        )

    async def get_prompt_version(self, version_id: str) -> PromptVersion | None:
        row = await self._pool.fetchrow(
            "SELECT pv.id::text AS id, p.key AS prompt_key, pv.version, pv.body, "
            "pv.provider, pv.model FROM prompt_versions pv "
            "JOIN prompts p ON p.id = pv.prompt_id WHERE pv.id = $1::uuid",
            version_id,
        )
        if row is None:
            return None
        return PromptVersion(
            id=row["id"],
            prompt_key=row["prompt_key"],
            version=row["version"],
            body=row["body"],
            provider=row["provider"],
            model=row["model"],
        )

    async def get_default_version_id(self, prompt_key: str) -> str | None:
        row = await self._pool.fetchrow(
            "SELECT pv.id::text AS id FROM prompt_versions pv "
            "JOIN prompts p ON p.id = pv.prompt_id WHERE p.key = $1 "
            "ORDER BY pv.version DESC LIMIT 1",
            prompt_key,
        )
        return row["id"] if row else None

    async def record_telemetry(self, event: TelemetryEvent) -> None:
        await self._pool.execute(
            "INSERT INTO telemetry (prompt_version_id, flag_key, variant, provider, "
            "model, prompt_tokens, completion_tokens, latency_ms) "
            "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)",
            event.prompt_version_id,
            event.flag_key,
            event.variant,
            event.provider,
            event.model,
            event.prompt_tokens,
            event.completion_tokens,
            event.latency_ms,
        )


class CachedRepository:
    """Wraps a repository with a short in-process TTL cache on flag lookups —
    flags change rarely but are read on every request."""

    def __init__(self, inner: Repository, ttl_seconds: float = 5.0) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._flags: dict[str, tuple[float, FlagRule | None]] = {}

    async def get_flag(self, key: str) -> FlagRule | None:
        now = time.monotonic()
        cached = self._flags.get(key)
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        value = await self._inner.get_flag(key)
        self._flags[key] = (now, value)
        return value

    async def get_prompt_version(self, version_id: str) -> PromptVersion | None:
        return await self._inner.get_prompt_version(version_id)

    async def get_default_version_id(self, prompt_key: str) -> str | None:
        return await self._inner.get_default_version_id(prompt_key)

    async def record_telemetry(self, event: TelemetryEvent) -> None:
        await self._inner.record_telemetry(event)


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
_cached_repo: Repository | None = None


def set_pool(pool: Any) -> None:
    """Called by the app lifespan when RELAY_DB_ENABLED is set."""
    global _cached_repo
    _cached_repo = CachedRepository(PostgresRepository(pool))


def get_repository() -> Repository:
    """Default FastAPI dependency: cached Postgres when a pool exists, else the
    seeded demo. Overridden with a fresh in-memory repo in tests."""
    return _cached_repo if _cached_repo is not None else _default_repo
