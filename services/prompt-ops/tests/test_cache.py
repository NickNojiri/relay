import pytest

from app.repository import CachedRepository


class CountingRepo:
    def __init__(self) -> None:
        self.flag_calls = 0

    async def get_flag(self, key):
        self.flag_calls += 1
        return None

    async def get_prompt_version(self, version_id):
        return None

    async def get_default_version_id(self, prompt_key):
        return None

    async def record_telemetry(self, event):
        return None


@pytest.mark.asyncio
async def test_caches_repeated_flag_lookups():
    inner = CountingRepo()
    repo = CachedRepository(inner, ttl_seconds=60)
    await repo.get_flag("k")
    await repo.get_flag("k")
    assert inner.flag_calls == 1


@pytest.mark.asyncio
async def test_refetches_after_ttl_expiry():
    inner = CountingRepo()
    repo = CachedRepository(inner, ttl_seconds=0)
    await repo.get_flag("k")
    await repo.get_flag("k")
    assert inner.flag_calls == 2
