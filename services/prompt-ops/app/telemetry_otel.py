"""Opt-in OpenTelemetry tracing for the gateway.

Off by default so local dev and tests need nothing. Enable by installing the
`otel` dependency group and setting `RELAY_OTEL_ENABLED=true`; point it at a
collector with the standard `OTEL_EXPORTER_OTLP_ENDPOINT`. When enabled, every
request gets a FastAPI span and the resolve→provider→telemetry path is broken
into child spans (`flag.resolve`, `provider.complete`) with useful attributes
(flag key, chosen variant, provider, model), so the "which version, how slow,
how expensive" story is visible in any OTLP backend (Jaeger, Tempo, Honeycomb).

Everything degrades gracefully: if the packages aren't installed, `get_tracer`
returns a no-op and `instrument_app` does nothing.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from .config import Settings

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI

_ENABLED = False
_tracer: Any = None


def _noop_span():  # matches the `with tracer.start_as_current_span(...)` shape
    @contextmanager
    def _cm(*_args: Any, **_kwargs: Any):
        yield None

    return _cm


def init_tracing(settings: Settings) -> bool:
    """Wire up the OTLP tracer provider. Returns True if tracing is live."""
    global _ENABLED, _tracer
    if not settings.relay_otel_enabled:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:  # group not installed — stay off, no crash
        return False

    provider = TracerProvider(resource=Resource.create({"service.name": "relay-prompt-ops"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("relay.prompt_ops")
    _ENABLED = True
    return True


def instrument_app(app: FastAPI) -> None:
    """Add the FastAPI ASGI instrumentation (server spans) when enabled."""
    if not _ENABLED:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:  # pragma: no cover
        return
    FastAPIInstrumentor.instrument_app(app)


def span(name: str, **attributes: Any):
    """Start a child span (or a no-op context manager when tracing is off)."""
    if not _ENABLED or _tracer is None:
        return _noop_span()()

    cm = _tracer.start_as_current_span(name)

    @contextmanager
    def _wrap():
        with cm as s:
            for key, value in attributes.items():
                if value is not None:
                    s.set_attribute(key, value)
            yield s

    return _wrap()


def set_attributes(scope_span: Any, **attributes: Any) -> None:
    """Set attributes on an active span, ignoring no-op spans."""
    if scope_span is None:
        return
    for key, value in attributes.items():
        if value is not None:
            scope_span.set_attribute(key, value)
