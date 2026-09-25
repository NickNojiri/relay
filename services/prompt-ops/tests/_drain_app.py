"""The gateway with a deliberately slow streaming provider, for test_shutdown.py."""

import asyncio

from app.main import app
from app.repository import InMemoryRepository, PromptVersion, get_repository
from app.routing import ProviderRouter, get_router


class SlowStream:
    async def complete(self, *, model, system, user):  # pragma: no cover - unused
        raise NotImplementedError

    async def stream(self, *, model, system, user):
        for i in range(10):
            await asyncio.sleep(0.2)
            yield f"t{i} "


_repo = InMemoryRepository()
_repo.versions["v1"] = PromptVersion("v1", "slow", 1, "s", "echo", "echo")
_router = ProviderRouter(lambda name: SlowStream())

app.dependency_overrides[get_repository] = lambda: _repo
app.dependency_overrides[get_router] = lambda: _router
