import pytest
from fastapi.testclient import TestClient

from app.flags import FlagRule, FlagVariant
from app.main import app
from app.providers import EchoProvider, get_provider
from app.repository import InMemoryRepository, PromptVersion, get_repository


def _seeded() -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.versions["v1"] = PromptVersion("v1", "prompt.support-bot", 1, "Be terse.", "ollama", "llama3.2")
    repo.versions["v2"] = PromptVersion("v2", "prompt.support-bot", 2, "Be warm.", "ollama", "llama3.2")
    repo.flags["prompt.support-bot"] = FlagRule(
        key="prompt.support-bot",
        enabled=True,
        rollout_bps=10000,
        variants=[FlagVariant("A", 5000, "v1"), FlagVariant("B", 5000, "v2")],
    )
    return repo


@pytest.fixture
def seeded():
    repo = _seeded()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_provider] = lambda: EchoProvider()
    yield repo, TestClient(app)
    app.dependency_overrides.clear()


def test_health(seeded):
    _, client = seeded
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_resolves_variant_and_logs(seeded):
    repo, client = seeded
    r = client.post(
        "/v1/chat",
        json={"prompt_key": "prompt.support-bot", "unit_id": "user-42", "input": "hi"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["variant"] in {"A", "B"}
    assert body["provider"] == "ollama"
    assert body["output"].endswith("hi")
    assert len(repo.telemetry) == 1
    assert repo.telemetry[0].variant == body["variant"]


def test_chat_is_deterministic_per_unit(seeded):
    _, client = seeded
    r1 = client.post(
        "/v1/chat",
        json={"prompt_key": "prompt.support-bot", "unit_id": "user-7", "input": "a"},
    )
    r2 = client.post(
        "/v1/chat",
        json={"prompt_key": "prompt.support-bot", "unit_id": "user-7", "input": "b"},
    )
    assert r1.json()["variant"] == r2.json()["variant"]


def test_chat_stream_emits_deltas_and_logs(seeded):
    repo, client = seeded
    r = client.post(
        "/v1/chat/stream",
        json={"prompt_key": "prompt.support-bot", "unit_id": "user-42", "input": "hi there friend"},
    )
    assert r.status_code == 200
    body = r.text
    assert "delta" in body
    assert "done" in body
    assert len(repo.telemetry) == 1
