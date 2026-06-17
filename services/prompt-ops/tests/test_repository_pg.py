"""Postgres repository smoke test. Skips automatically when no DB is reachable,
so it's safe in CI without a database but runs once Postgres + migrations are up."""

import os

import pytest

from app.repository import PostgresRepository

asyncpg = pytest.importorskip("asyncpg")


@pytest.mark.asyncio
async def test_postgres_missing_flag_returns_none():
    dsn = os.environ.get("DATABASE_URL", "postgres://relay:relay@localhost:5432/relay")
    try:
        pool = await asyncpg.create_pool(dsn=dsn, timeout=2, min_size=1, max_size=1)
    except Exception:
        pytest.skip("no Postgres reachable")
    try:
        repo = PostgresRepository(pool)
        assert await repo.get_flag("nonexistent-flag-key") is None
    finally:
        await pool.close()
