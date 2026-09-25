"""Provider failover, circuit breakers, and timeouts (app/routing.py)."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.flags import FlagRule, FlagVariant
from app.main import app
from app.providers import Completion, EchoProvider
from app.repository import InMemoryRepository, PromptVersion, get_repository
from app.routing import (
    AllProvidersFailed,
    CircuitBreaker,
    MidStreamFailure,
    ProviderRouter,
    get_router,
    parse_chain,
)


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.test/v1")
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(code, request=request))


class Failing:
    """A provider that always raises `exc`, counting how often it was called."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls = 0

    async def complete(self, *, model, system, user):
        self.calls += 1
        raise self.exc


class Slow:
    async def complete(self, *, model, system, user):
        await asyncio.sleep(5)
        return Completion("late", 0, 0)


class Streaming:
    """Streams `chunks`, then raises `fail_after` if given."""

    def __init__(self, chunks, fail_after: BaseException | None = None) -> None:
        self.chunks = chunks
        self.fail_after = fail_after
        self.calls = 0

    async def complete(self, *, model, system, user):
        return Completion("".join(self.chunks), 0, len(self.chunks))

    async def stream(self, *, model, system, user):
        self.calls += 1
        for c in self.chunks:
            yield c
        if self.fail_after is not None:
            raise self.fail_after


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _router(providers: dict, chain: str = "", **kw) -> ProviderRouter:
    return ProviderRouter(lambda name: providers[name], parse_chain(chain), **kw)


# ── circuit breaker ─────────────────────────────────────────────────────────


def test_breaker_opens_after_threshold_and_half_opens_after_reset():
    clock = Clock()
    b = CircuitBreaker(failure_threshold=2, reset_after_s=10, clock=clock)
    b.record_failure()
    assert b.state == "closed" and b.allow()
    b.record_failure()
    assert b.state == "open" and not b.allow()

    clock.t = 10
    assert b.state == "half_open"
    assert b.allow()          # one trial call
    assert not b.allow()      # and only one
    b.record_success()
    assert b.state == "closed" and b.allow()


def test_failed_trial_reopens_for_a_full_period():
    clock = Clock()
    b = CircuitBreaker(failure_threshold=1, reset_after_s=10, clock=clock)
    b.record_failure()
    clock.t = 10
    assert b.allow()
    b.record_failure()
    clock.t = 15
    assert b.state == "open" and not b.allow()


def test_a_trial_that_never_reports_back_expires():
    """A cancelled trial must not wedge the breaker shut forever."""
    clock = Clock()
    b = CircuitBreaker(failure_threshold=1, reset_after_s=10, clock=clock)
    b.record_failure()
    clock.t = 10
    assert b.allow()          # trial starts, then its request is cancelled
    clock.t = 15
    assert not b.allow()
    clock.t = 20
    assert b.allow()


# ── routing ────────────────────────────────────────────────────────────────


async def test_provider_failure_moves_to_the_next_provider():
    down = Failing(_status_error(503))
    r = _router({"anthropic": down, "echo": EchoProvider()}, "echo:echo")
    routed = await r.complete("anthropic", "claude", system="s", user="hi")
    assert routed.provider == "echo" and routed.model == "echo"
    assert [(a.provider, a.outcome) for a in routed.attempts] == [
        ("anthropic", "failed"),
        ("echo", "ok"),
    ]
    assert routed.attempts[0].error == "HTTP 503"


@pytest.mark.parametrize(
    "exc",
    [_status_error(429), _status_error(500), httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
)
async def test_provider_shaped_failures_fail_over(exc):
    r = _router({"openai": Failing(exc), "echo": EchoProvider()}, "echo:echo")
    assert (await r.complete("openai", "gpt", system="s", user="u")).provider == "echo"


async def test_a_client_error_is_not_retried_elsewhere_or_held_against_the_provider():
    bad = Failing(_status_error(400))
    fallback = Failing(RuntimeError("must not be called"))
    r = _router({"openai": bad, "anthropic": fallback}, "anthropic:claude", failure_threshold=1)
    with pytest.raises(httpx.HTTPStatusError):
        await r.complete("openai", "gpt", system="s", user="u")
    assert fallback.calls == 0
    assert r.breaker("openai").state == "closed"


async def test_a_slow_provider_times_out_and_fails_over():
    r = _router({"ollama": Slow(), "echo": EchoProvider()}, "echo:echo", timeout_s=0.05)
    routed = await r.complete("ollama", "llama", system="s", user="u")
    assert routed.provider == "echo"
    assert routed.attempts[0].error == "timeout"


async def test_an_open_circuit_is_skipped_without_calling_the_provider():
    down = Failing(httpx.ConnectError("refused"))
    r = _router({"ollama": down, "echo": EchoProvider()}, "echo:echo", failure_threshold=2)
    for _ in range(2):
        await r.complete("ollama", "llama", system="s", user="u")
    assert down.calls == 2 and r.breaker("ollama").state == "open"

    routed = await r.complete("ollama", "llama", system="s", user="u")
    assert down.calls == 2
    assert routed.attempts[0].outcome == "circuit_open"


async def test_every_provider_down_raises_with_the_attempts():
    r = _router(
        {"ollama": Failing(httpx.ConnectError("x")), "openai": Failing(_status_error(502))},
        "openai:gpt",
    )
    with pytest.raises(AllProvidersFailed) as info:
        await r.complete("ollama", "llama", system="s", user="u")
    assert [a.provider for a in info.value.attempts] == ["ollama", "openai"]


async def test_the_preferred_provider_is_not_tried_twice_when_it_is_also_in_the_chain():
    down = Failing(httpx.ConnectError("x"))
    r = _router({"ollama": down, "echo": EchoProvider()}, "ollama:llama,echo:echo")
    await r.complete("ollama", "llama", system="s", user="u")
    assert down.calls == 1


# ── streaming ──────────────────────────────────────────────────────────────


async def _drain(router, preferred="ollama"):
    attempts, got = [], []
    async for provider, _model, chunk in router.stream(
        preferred, "m", system="s", user="u", attempts=attempts
    ):
        got.append((provider, chunk))
    return got, attempts


async def test_a_stream_that_fails_before_its_first_chunk_fails_over():
    dead = Streaming([], fail_after=httpx.ConnectError("refused"))
    r = _router({"ollama": dead, "echo": Streaming(["a", "b"])}, "echo:echo")
    got, attempts = await _drain(r)
    assert got == [("echo", "a"), ("echo", "b")]
    assert [a.outcome for a in attempts] == ["failed", "ok"]


async def test_a_stream_that_fails_mid_answer_is_not_retried():
    partial = Streaming(["half "], fail_after=httpx.ReadError("dropped"))
    fallback = Streaming(["whole"])
    r = _router({"ollama": partial, "echo": fallback}, "echo:echo")
    got = []
    with pytest.raises(MidStreamFailure):
        async for provider, _m, chunk in r.stream("ollama", "m", system="s", user="u", attempts=[]):
            got.append(chunk)
    assert got == ["half "]
    assert fallback.calls == 0


# ── config ─────────────────────────────────────────────────────────────────


def test_parse_chain():
    assert parse_chain(" openai:gpt-4o-mini , ollama:llama3.2 ") == [
        ("openai", "gpt-4o-mini"),
        ("ollama", "llama3.2"),
    ]
    assert parse_chain("") == []
    with pytest.raises(ValueError):
        parse_chain("openai")
    with pytest.raises(ValueError):
        parse_chain("bedrock:x")


# ── through the HTTP API ───────────────────────────────────────────────────


def _repo(provider: str | None) -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.versions["v1"] = PromptVersion("v1", "prompt.support-bot", 1, "Be terse.", provider, None)
    repo.flags["prompt.support-bot"] = FlagRule(
        key="prompt.support-bot", enabled=True, rollout_bps=10000,
        variants=[FlagVariant("A", 10000, "v1")],
    )
    return repo


PAYLOAD = {"prompt_key": "prompt.support-bot", "unit_id": "user-42", "input": "hi"}


@pytest.fixture
def gateway():
    def make(providers: dict, chain: str = "", version_provider: str | None = "anthropic", **kw):
        repo = _repo(version_provider)
        router = _router(providers, chain, **kw)
        app.dependency_overrides[get_settings] = lambda: Settings(
            relay_default_provider="ollama", relay_default_model="llama3.2"
        )
        app.dependency_overrides[get_repository] = lambda: repo
        app.dependency_overrides[get_router] = lambda: router
        return repo, router, TestClient(app)

    yield make
    app.dependency_overrides.clear()


def test_simulated_provider_outage_is_routed_around(gateway):
    """The roadmap's done-when: a provider fails and traffic moves to a healthy one."""
    down = Failing(_status_error(503))
    repo, _, client = gateway({"anthropic": down, "echo": EchoProvider()}, "echo:echo",
                              failure_threshold=2)
    for _ in range(3):
        r = client.post("/v1/chat", json=PAYLOAD)
        assert r.status_code == 200
        assert r.json()["provider"] == "echo"
    assert down.calls == 2                                   # third request skipped it
    assert r.json()["routing"][0] == {"provider": "anthropic", "outcome": "circuit_open", "error": None}
    assert [t.provider for t in repo.telemetry] == ["echo"] * 3   # telemetry names who served

    health = client.get("/health/providers").json()["providers"]
    assert health["anthropic"]["state"] == "open"
    assert health["echo"]["state"] == "closed"


def test_the_prompt_versions_provider_is_the_one_called(gateway):
    called = []

    def factory(name):
        called.append(name)
        return EchoProvider()

    repo = _repo("openai")
    app.dependency_overrides[get_settings] = lambda: Settings(relay_default_provider="ollama")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_router] = lambda: ProviderRouter(factory)
    r = TestClient(app).post("/v1/chat", json=PAYLOAD)
    assert r.json()["provider"] == "openai" and called == ["openai"]


def test_no_provider_left_is_a_503_with_the_routing_trail(gateway):
    _, _, client = gateway({"anthropic": Failing(httpx.ConnectError("x"))})
    r = client.post("/v1/chat", json=PAYLOAD)
    assert r.status_code == 503
    assert r.json()["detail"]["routing"] == [
        {"provider": "anthropic", "outcome": "failed", "error": "ConnectError"}
    ]


def test_unknown_provider_on_a_version_is_a_502(gateway):
    _, _, client = gateway({}, version_provider="bedrock")
    assert client.post("/v1/chat", json=PAYLOAD).status_code == 502


def _events(body: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]


def test_stream_fails_over_before_first_chunk(gateway):
    dead = Streaming([], fail_after=httpx.ConnectError("refused"))
    repo, _, client = gateway({"anthropic": dead, "echo": EchoProvider()}, "echo:echo")
    events = _events(client.post("/v1/chat/stream", json=PAYLOAD).text)
    assert events[-1]["done"] and events[-1]["provider"] == "echo"
    assert repo.telemetry[0].provider == "echo"


def test_stream_that_breaks_mid_answer_ends_with_an_error_event(gateway):
    partial = Streaming(["half "], fail_after=httpx.ReadError("dropped"))
    fallback = Streaming(["whole"])
    repo, _, client = gateway({"anthropic": partial, "echo": fallback}, "echo:echo")
    events = _events(client.post("/v1/chat/stream", json=PAYLOAD).text)
    assert events[0] == {"delta": "half "}
    assert events[-1]["error"] == "provider failed mid-stream"
    assert fallback.calls == 0
    assert repo.telemetry == []
