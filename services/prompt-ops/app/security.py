"""API-key auth + rate limiting for the gateway's /v1 endpoints.

Both are opt-in via settings so local dev stays zero-config:
- ``RELAY_API_KEYS`` (comma-separated) requires ``Authorization: Bearer <key>``
  or ``x-api-key: <key>`` on every /v1 call.
- ``RELAY_RATE_LIMIT_PER_MINUTE`` caps requests per key (per client IP when
  auth is off). The window lives in-process, i.e. the cap is per gateway
  instance — the right trade for a single-region Fly deployment; swap the
  store for Redis when the gateway scales horizontally.
"""

from __future__ import annotations

import hmac
import time
from collections import deque

from fastapi import Depends, HTTPException, Request

from .config import Settings, get_settings


class SlidingWindowLimiter:
    """In-process sliding-window counter: at most `limit` hits per `window_s`."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= window_s:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()


def _presented_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


async def gateway_guard(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    """Dependency guarding the /v1 routes: 401 on bad key, 429 over the cap."""
    presented = _presented_key(request)

    keys = [k.strip() for k in settings.relay_api_keys.split(",") if k.strip()]
    if keys and (
        presented is None or not any(hmac.compare_digest(presented, k) for k in keys)
    ):
        raise HTTPException(status_code=401, detail="invalid or missing API key")

    limit = settings.relay_rate_limit_per_minute
    if limit > 0:
        client = presented or (request.client.host if request.client else "anonymous")
        if not limiter.allow(client, limit):
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": "60"},
            )
