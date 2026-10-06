"""Provider failover (app/failover.py) through the real endpoints and provider HTTP code,
with faults injected at the HTTP layer."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.failover import Route
from app.flags import FlagRule, FlagVariant
from app.main import app
from app.providers import ProviderRegistry, Timeouts, get_providers
from app.repository import InMemoryRepository, PromptVersion, get_repository

PRIMARY = "ollama/llama3.2"
FALLBACK = Route("openai", "gpt-4o-mini")
PAYLOAD = {"prompt_key": "prompt.support-bot", "unit_id": "user-42", "input": "where is my order"}


def ok(request: httpx.Request) -> httpx.Response:
    if request.url.host == "ollama.test":
        if json.loads(request.content).get("stream"):
            lines = b'{"message":{"content":"from "},"done":false}\n{"message":{"content":"ollama"},"done":true}\n'
            return httpx.Response(200, content=lines)
        return httpx.Response(200, json={"message": {"content": "from ollama"}, "done": True})
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": "from openai"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 2}},
    )


def status(code: int):
    return lambda request: httpx.Response(code, json={"error": "injected"})


def raises(exc_type: type[httpx.HTTPError]):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("injected", request=request)

    return handler


def drops_after_first_token(request: httpx.Request) -> httpx.Response:
    async def body():
        yield b'{"message":{"content":"Hello"},"done":false}\n'
        raise httpx.ReadError("connection reset", request=request)

    return httpx.Response(200, content=body())


class Gateway:
    def __init__(self, ollama, openai, version: PromptVersion, settings: Settings) -> None:
        self.behaviors = {"ollama": ollama, "openai": openai}
        self.calls = {"ollama": 0, "openai": 0}
        self.repo = InMemoryRepository()
        self.repo.versions[version.id] = version
        self.repo.flags["prompt.support-bot"] = FlagRule(
            key="prompt.support-bot", enabled=True, rollout_bps=10000, variants=[FlagVariant("A", 10000, version.id)]
        )
        self.registry = ProviderRegistry(settings, transport=httpx.MockTransport(self._handle))
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_repository] = lambda: self.repo
        app.dependency_overrides[get_providers] = lambda: self.registry
        self.client = TestClient(app)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        name = "ollama" if request.url.host == "ollama.test" else "openai"
        self.calls[name] += 1
        return self.behaviors[name](request)

    def stream_events(self) -> tuple[int, list[dict]]:
        resp = self.client.post("/v1/chat/stream", json=PAYLOAD)
        events = [json.loads(line[len("data: "):]) for line in resp.text.splitlines() if line.startswith("data: ")]
        return resp.status_code, events


def settings(**overrides) -> Settings:
    base = dict(
        relay_db_enabled=False,
        relay_default_provider="ollama",
        relay_default_model="llama3.2",
        ollama_base_url="http://ollama.test",
        openai_base_url="http://openai.test",
        openai_api_key="k",
    )
    return Settings(**{**base, **overrides})


def version(**overrides) -> PromptVersion:
    base = dict(id="v1", prompt_key="prompt.support-bot", version=1, body="Be terse.", fallbacks=[FALLBACK])
    return PromptVersion(**{**base, **overrides})


@pytest.fixture(autouse=True)
def _clean():
    yield
    app.dependency_overrides.clear()


def test_routes_to_the_versions_own_provider():
    gw = Gateway(ok, ok, version(provider="openai", model="gpt-4o-mini", fallbacks=[]), settings())
    body = gw.client.post("/v1/chat", json=PAYLOAD).json()
    assert (body["provider"], body["output"], body["fallback_reason"]) == ("openai", "from openai", None)
    assert gw.calls == {"ollama": 0, "openai": 1}
    assert gw.repo.telemetry[0].provider == "openai"


@pytest.mark.parametrize(
    ("primary", "reason"),
    [
        (raises(httpx.ReadTimeout), "timeout"),
        (raises(httpx.ConnectTimeout), "timeout"),
        (raises(httpx.ConnectError), "connect_error"),
        (raises(httpx.RemoteProtocolError), "disconnected"),
        (status(429), "http_429"),
        (status(500), "http_500"),
        (status(503), "http_503"),
    ],
)
def test_fails_over_on_unavailable_provider(primary, reason):
    gw = Gateway(primary, ok, version(), settings())
    resp = gw.client.post("/v1/chat", json=PAYLOAD)
    body = resp.json()
    assert resp.status_code == 200
    assert (body["provider"], body["model"], body["output"]) == ("openai", "gpt-4o-mini", "from openai")
    assert body["fallback_reason"] == f"{PRIMARY}: {reason}"
    event = gw.repo.telemetry[0]
    assert (event.provider, event.fallback_reason) == ("openai", f"{PRIMARY}: {reason}")


@pytest.mark.parametrize("code", [400, 401, 404, 422])
def test_client_errors_do_not_fail_over(code):
    gw = Gateway(status(code), ok, version(), settings())
    resp = gw.client.post("/v1/chat", json=PAYLOAD)
    assert resp.status_code == 502
    assert resp.json()["detail"]["attempts"] == [f"{PRIMARY}: http_{code}"]
    assert gw.calls["openai"] == 0
    assert gw.repo.telemetry == []


def test_every_route_failing_returns_502_listing_each_attempt():
    gw = Gateway(status(500), raises(httpx.ConnectError), version(), settings())
    resp = gw.client.post("/v1/chat", json=PAYLOAD)
    assert resp.status_code == 502
    assert resp.json()["detail"]["attempts"] == [f"{PRIMARY}: http_500", "openai/gpt-4o-mini: connect_error"]


def test_unconfigured_and_unknown_providers_are_skipped():
    v = version(fallbacks=[Route("anthropic", "claude-haiku-4-5"), Route("nonsense", "m"), FALLBACK])
    gw = Gateway(status(500), ok, v, settings())
    body = gw.client.post("/v1/chat", json=PAYLOAD).json()
    assert body["provider"] == "openai"
    assert body["fallback_reason"] == (
        f"{PRIMARY}: http_500; anthropic/claude-haiku-4-5: not_configured; nonsense/m: unknown_provider"
    )


def test_gateway_wide_fallbacks_follow_the_versions_own():
    s = settings(relay_fallbacks=[{"provider": "openai", "model": "gpt-4o-mini"}])
    gw = Gateway(raises(httpx.ReadTimeout), ok, version(fallbacks=[]), s)
    body = gw.client.post("/v1/chat", json=PAYLOAD).json()
    assert (body["provider"], body["fallback_reason"]) == ("openai", f"{PRIMARY}: timeout")


def test_no_fallback_configured_means_the_failure_is_returned():
    gw = Gateway(status(503), ok, version(fallbacks=[]), settings())
    resp = gw.client.post("/v1/chat", json=PAYLOAD)
    assert resp.status_code == 502
    assert gw.calls["openai"] == 0


def test_stream_fails_over_before_the_first_token():
    gw = Gateway(status(500), ok, version(), settings())
    code, events = gw.stream_events()
    assert code == 200
    assert "".join(e.get("delta", "") for e in events) == "from openai"
    done = events[-1]
    assert done["servedBy"] == "openai/gpt-4o-mini"
    assert done["fallbackReason"] == f"{PRIMARY}: http_500"
    assert "error" not in done


def test_stream_never_fails_over_after_the_first_token():
    gw = Gateway(drops_after_first_token, ok, version(), settings())
    code, events = gw.stream_events()
    assert code == 200
    assert [e["delta"] for e in events if "delta" in e] == ["Hello"]
    done = events[-1]
    assert done["servedBy"] == PRIMARY
    assert done["error"] == f"{PRIMARY}: stream interrupted (ReadError)"
    assert gw.calls["openai"] == 0
    assert gw.repo.telemetry[0].provider == "ollama"


def test_stream_returns_502_when_no_route_produces_output():
    gw = Gateway(raises(httpx.ConnectError), status(500), version(), settings())
    code, _ = gw.stream_events()
    assert code == 502


def test_streams_from_the_primary_when_it_works():
    gw = Gateway(ok, ok, version(), settings())
    code, events = gw.stream_events()
    assert "".join(e.get("delta", "") for e in events) == "from ollama"
    assert events[-1]["servedBy"] == PRIMARY and "fallbackReason" not in events[-1]
    assert gw.calls["openai"] == 0


def test_each_provider_gets_its_own_timeouts():
    registry = ProviderRegistry(settings(relay_timeouts={"ollama": {"connect": 1, "read": 5}}))
    assert registry.timeouts("ollama") == Timeouts(connect=1, read=5)
    assert registry.timeouts("openai") == Timeouts(connect=5.0, read=60.0)
    ollama_timeout = registry.get("ollama")._client.timeout
    assert (ollama_timeout.connect, ollama_timeout.read) == (1, 5)
    assert registry.get("openai")._client.timeout.read == 60.0
