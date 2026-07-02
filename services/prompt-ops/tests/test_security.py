"""API-key auth + rate limiting on the /v1 endpoints (app/security.py)."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.flags import FlagRule, FlagVariant
from app.main import app
from app.providers import EchoProvider, get_provider
from app.repository import InMemoryRepository, PromptVersion, get_repository
from app.security import limiter

PAYLOAD = {"prompt_key": "prompt.support-bot", "unit_id": "user-42", "input": "hi"}


def _seeded() -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.versions["v1"] = PromptVersion("v1", "prompt.support-bot", 1, "Be terse.", "ollama", "llama3.2")
    repo.flags["prompt.support-bot"] = FlagRule(
        key="prompt.support-bot",
        enabled=True,
        rollout_bps=10000,
        variants=[FlagVariant("A", 10000, "v1")],
    )
    return repo


def _client(**settings_overrides) -> TestClient:
    settings = Settings(relay_db_enabled=False, **settings_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_repository] = lambda: _seeded()
    app.dependency_overrides[get_provider] = lambda: EchoProvider()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    limiter.reset()
    yield
    limiter.reset()
    app.dependency_overrides.clear()


def test_open_when_no_keys_configured():
    client = _client()
    assert client.post("/v1/chat", json=PAYLOAD).status_code == 200


def test_rejects_missing_and_wrong_key():
    client = _client(relay_api_keys="secret-1,secret-2")
    assert client.post("/v1/chat", json=PAYLOAD).status_code == 401
    r = client.post("/v1/chat", json=PAYLOAD, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_accepts_bearer_and_x_api_key():
    client = _client(relay_api_keys="secret-1,secret-2")
    r = client.post("/v1/chat", json=PAYLOAD, headers={"Authorization": "Bearer secret-2"})
    assert r.status_code == 200
    r = client.post("/v1/chat", json=PAYLOAD, headers={"x-api-key": "secret-1"})
    assert r.status_code == 200


def test_guard_applies_to_stream_endpoint():
    client = _client(relay_api_keys="secret-1")
    assert client.post("/v1/chat/stream", json=PAYLOAD).status_code == 401


def test_health_stays_open():
    client = _client(relay_api_keys="secret-1")
    assert client.get("/health").status_code == 200


def test_rate_limit_returns_429_with_retry_after():
    client = _client(relay_rate_limit_per_minute=2)
    assert client.post("/v1/chat", json=PAYLOAD).status_code == 200
    assert client.post("/v1/chat", json=PAYLOAD).status_code == 200
    r = client.post("/v1/chat", json=PAYLOAD)
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "60"


def test_rate_limit_is_per_api_key():
    client = _client(relay_api_keys="key-a,key-b", relay_rate_limit_per_minute=1)
    a = {"Authorization": "Bearer key-a"}
    b = {"Authorization": "Bearer key-b"}
    assert client.post("/v1/chat", json=PAYLOAD, headers=a).status_code == 200
    assert client.post("/v1/chat", json=PAYLOAD, headers=a).status_code == 429
    # a different key has its own budget
    assert client.post("/v1/chat", json=PAYLOAD, headers=b).status_code == 200
