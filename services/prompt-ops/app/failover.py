"""Ordered provider failover with streaming-safe rules.

A request tries its routes in order: the prompt version's provider/model, then the version's
fallbacks, then the gateway-wide fallbacks. It moves to the next route only when the current
one failed in a way that says "this provider is unavailable right now" (a timeout, a
connection failure or drop, 429, or 5xx), and only before any output has reached the client.
Once a stream has sent a token, a later failure ends the stream instead of retrying: the
client already has part of an answer, and a second provider would duplicate or contradict it
and bill twice.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from .providers import Completion, ProviderRegistry, ProviderUnavailable


@dataclass(frozen=True)
class Route:
    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"


class AllRoutesFailed(Exception):
    def __init__(self, attempts: list[str]) -> None:
        super().__init__("; ".join(attempts))
        self.attempts = attempts


class ProviderError(Exception):
    """A failure that failover must not hide, such as a 400 or 401: the next provider would
    get the same bad request or the same misconfiguration."""

    def __init__(self, route: Route, exc: Exception, attempts: list[str]) -> None:
        super().__init__(f"{route}: {describe(exc)}")
        self.attempts = [*attempts, f"{route}: {describe(exc)}"]


def describe(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    return type(exc).__name__


def retry_reason(exc: Exception) -> str | None:
    """Why `exc` justifies trying the next route, or None if it doesn't."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    # Includes a pooled keep-alive connection the server already closed.
    if isinstance(exc, (httpx.NetworkError, httpx.RemoteProtocolError)):
        return "disconnected"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429 or code >= 500:
            return f"http_{code}"
    return None


async def complete(
    routes: list[Route], providers: ProviderRegistry, *, system: str, user: str
) -> tuple[Route, Completion, list[str]]:
    """Returns the route that answered, its completion, and why earlier routes were skipped."""
    skipped: list[str] = []
    for route in routes:
        try:
            provider = providers.get(route.provider)
            return route, await provider.complete(model=route.model, system=system, user=user), skipped
        except ProviderUnavailable as exc:
            skipped.append(f"{route}: {exc.reason}")
        except httpx.HTTPError as exc:
            reason = retry_reason(exc)
            if reason is None:
                raise ProviderError(route, exc, skipped) from exc
            skipped.append(f"{route}: {reason}")
    raise AllRoutesFailed(skipped)


@dataclass
class OpenedStream:
    route: Route
    first: str
    rest: AsyncIterator[str] | None
    skipped: list[str]


async def open_stream(
    routes: list[Route], providers: ProviderRegistry, *, system: str, user: str
) -> OpenedStream:
    """Finds a route that produces a first chunk. Failover is allowed only inside this call;
    the caller streams `first` and then `rest` with no further failover."""
    skipped: list[str] = []
    for route in routes:
        rest = None
        try:
            provider = providers.get(route.provider)
            stream = getattr(provider, "stream", None)
            if stream is None:
                completion = await provider.complete(model=route.model, system=system, user=user)
                return OpenedStream(route, completion.text, None, skipped)
            rest = stream(model=route.model, system=system, user=user)
            try:
                first = await anext(rest)
            except StopAsyncIteration:
                return OpenedStream(route, "", None, skipped)
            return OpenedStream(route, first, rest, skipped)
        except ProviderUnavailable as exc:
            skipped.append(f"{route}: {exc.reason}")
        except httpx.HTTPError as exc:
            if rest is not None:
                await rest.aclose()
            reason = retry_reason(exc)
            if reason is None:
                raise ProviderError(route, exc, skipped) from exc
            skipped.append(f"{route}: {reason}")
    raise AllRoutesFailed(skipped)
