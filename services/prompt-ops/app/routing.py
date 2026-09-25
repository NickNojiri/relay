"""Provider routing: per-provider timeouts, circuit breakers, and failover.

A request names a preferred provider (the prompt version's, else the default).
The router tries it first, then the configured fallback chain
(``RELAY_FALLBACK_CHAIN="openai:gpt-4o-mini,ollama:llama3.2"``), skipping any
provider whose circuit is open. With no chain configured the behaviour is the
old one: one provider, one try.

What moves a request to the next provider — and counts against a breaker — is
a failure that says the *provider* is unwell: a timeout, a connection error, a
429, or a 5xx. Any other 4xx means the request or our credentials are wrong; it
would fail the same way everywhere, so it is returned as-is and the breaker
treats the provider as healthy.

Streams fail over only before the first chunk is sent. After that the client
already holds part of one provider's answer, and splicing another provider's
answer onto it would be wrong, so a mid-stream failure ends the stream with an
error event instead of a retry.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

import httpx

from .providers import Completion, LLMProvider

KNOWN_PROVIDERS = ("echo", "ollama", "anthropic", "openai")


class CircuitBreaker:
    """Consecutive-failure breaker: closed → open → half-open → closed.

    Opens after ``failure_threshold`` failures in a row. While open, calls are
    refused until ``reset_after_s`` has passed; then one trial call is let
    through (half-open). Its success closes the circuit, its failure reopens it.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_after_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.reset_after_s = reset_after_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        # When the half-open trial call started. A trial that never reports
        # back (the request was cancelled) expires after reset_after_s, so the
        # breaker cannot wedge itself shut.
        self._trial_started: float | None = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.reset_after_s:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        state = self.state
        if state == "closed":
            return True
        if state == "half_open":
            now = self._clock()
            if self._trial_started is None or now - self._trial_started >= self.reset_after_s:
                self._trial_started = now
                return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._trial_started = None

    def record_failure(self) -> None:
        self._trial_started = None
        if self._opened_at is not None:
            # The half-open trial failed: stay open for another full period.
            self._opened_at = self._clock()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._clock()

    def snapshot(self) -> dict:
        return {"state": self.state, "consecutive_failures": self._failures}


def is_provider_failure(exc: BaseException) -> bool:
    """True when the error says the provider is unwell, so another may succeed."""
    if isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


@dataclass
class Attempt:
    provider: str
    model: str
    outcome: str  # ok | failed | circuit_open
    error: str | None = None


@dataclass
class Routed:
    """What a routed call produced, and how it got there."""

    completion: Completion
    provider: str
    model: str
    attempts: list[Attempt] = field(default_factory=list)


class AllProvidersFailed(Exception):
    def __init__(self, attempts: list[Attempt]) -> None:
        self.attempts = attempts
        summary = "; ".join(f"{a.provider}: {a.outcome}" for a in attempts)
        super().__init__(f"no provider could serve the request ({summary})")


class MidStreamFailure(Exception):
    """A provider failed after chunks were already sent; not retried."""


def parse_chain(raw: str) -> list[tuple[str, str]]:
    """``"openai:gpt-4o-mini, ollama:llama3.2"`` → ``[("openai", "gpt-4o-mini"), ...]``."""
    chain: list[tuple[str, str]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        name, sep, model = item.partition(":")
        name = name.strip()
        if not sep or not model.strip():
            raise ValueError(f"fallback entry {item!r} must be provider:model")
        if name not in KNOWN_PROVIDERS:
            raise ValueError(f"unknown provider {name!r} in fallback chain")
        chain.append((name, model.strip()))
    return chain


class ProviderRouter:
    def __init__(
        self,
        factory: Callable[[str], LLMProvider],
        fallback_chain: list[tuple[str, str]] | None = None,
        timeout_s: float = 60.0,
        failure_threshold: int = 3,
        reset_after_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self._providers: dict[str, LLMProvider] = {}
        self.fallback_chain = fallback_chain or []
        self.timeout_s = timeout_s
        self._breaker_args = (failure_threshold, reset_after_s, clock)
        self.breakers: dict[str, CircuitBreaker] = {}

    def breaker(self, name: str) -> CircuitBreaker:
        if name not in self.breakers:
            threshold, reset, clock = self._breaker_args
            self.breakers[name] = CircuitBreaker(threshold, reset, clock)
        return self.breakers[name]

    def provider(self, name: str) -> LLMProvider:
        if name not in self._providers:
            self._providers[name] = self._factory(name)
        return self._providers[name]

    async def aclose(self) -> None:
        """Close every provider's pooled HTTP client (called at shutdown)."""
        for provider in self._providers.values():
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()

    def plan(self, preferred: str, model: str) -> list[tuple[str, str]]:
        """Preferred provider first, then the fallback chain, each provider once."""
        out = [(preferred, model)]
        out += [(n, m) for n, m in self.fallback_chain if n != preferred]
        return out

    def health(self) -> dict[str, dict]:
        """Passive health: each provider's breaker, as seen by real traffic."""
        names = {n for n, _ in self.fallback_chain} | set(self.breakers)
        return {n: self.breaker(n).snapshot() for n in sorted(names)}

    async def complete(self, preferred: str, model: str, *, system: str, user: str) -> Routed:
        attempts: list[Attempt] = []
        for name, mdl in self.plan(preferred, model):
            breaker = self.breaker(name)
            if not breaker.allow():
                attempts.append(Attempt(name, mdl, "circuit_open"))
                continue
            try:
                async with asyncio.timeout(self.timeout_s):
                    completion = await self.provider(name).complete(
                        model=mdl, system=system, user=user
                    )
            except Exception as exc:
                if not is_provider_failure(exc):
                    breaker.record_success()  # the provider answered; the request was bad
                    raise
                breaker.record_failure()
                attempts.append(Attempt(name, mdl, "failed", _describe(exc)))
                continue
            breaker.record_success()
            attempts.append(Attempt(name, mdl, "ok"))
            return Routed(completion, name, mdl, attempts)
        raise AllProvidersFailed(attempts)

    async def stream(
        self, preferred: str, model: str, *, system: str, user: str, attempts: list[Attempt]
    ) -> AsyncIterator[tuple[str, str, str]]:
        """Yield ``(provider, model, chunk)``; fail over only before the first chunk.

        ``attempts`` is filled in as the router goes, so the caller can report
        it even when the stream ends in an error.
        """
        for name, mdl in self.plan(preferred, model):
            breaker = self.breaker(name)
            if not breaker.allow():
                attempts.append(Attempt(name, mdl, "circuit_open"))
                continue
            provider = self.provider(name)
            stream_fn = getattr(provider, "stream", None)
            sent_any = False
            try:
                if stream_fn is None:
                    async with asyncio.timeout(self.timeout_s):
                        completion = await provider.complete(model=mdl, system=system, user=user)
                    chunks: AsyncIterator[str] = _one(completion.text)
                else:
                    chunks = stream_fn(model=mdl, system=system, user=user)
                iterator = chunks.__aiter__()
                # The timeout covers time-to-first-chunk; once a stream is
                # flowing it is not cut off for being long.
                async with asyncio.timeout(self.timeout_s):
                    first = await anext(iterator, None)
                if first is not None:
                    sent_any = True
                    yield name, mdl, first
                    async for chunk in iterator:
                        yield name, mdl, chunk
            except Exception as exc:
                if not is_provider_failure(exc):
                    breaker.record_success()
                    raise
                breaker.record_failure()
                attempts.append(Attempt(name, mdl, "failed", _describe(exc)))
                if sent_any:
                    raise MidStreamFailure(_describe(exc)) from exc
                continue
            breaker.record_success()
            attempts.append(Attempt(name, mdl, "ok"))
            return
        raise AllProvidersFailed(attempts)


async def _one(text: str) -> AsyncIterator[str]:
    yield text


def _describe(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    return type(exc).__name__


_router: ProviderRouter | None = None


def build_router(settings) -> ProviderRouter:
    from .providers import build_named_provider

    return ProviderRouter(
        factory=lambda name: build_named_provider(name, settings),
        fallback_chain=parse_chain(settings.relay_fallback_chain),
        timeout_s=settings.relay_provider_timeout_s,
        failure_threshold=settings.relay_breaker_failures,
        reset_after_s=settings.relay_breaker_reset_s,
    )


def get_router() -> ProviderRouter:
    """FastAPI dependency. One router per process, so breaker state persists
    across requests; tests override this with their own router."""
    global _router
    if _router is None:
        from .config import get_settings

        _router = build_router(get_settings())
    return _router


async def close_router() -> None:
    """Shut down the process-wide router's HTTP clients, if one was built."""
    global _router
    if _router is not None:
        await _router.aclose()
        _router = None
