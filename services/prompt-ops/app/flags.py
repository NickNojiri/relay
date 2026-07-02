"""Python port of @relay/flag-sdk evaluation.

Deliberately byte-for-byte equivalent to the TypeScript engine: same FNV-1a hash over
UTF-8 bytes, same `flag:salt:unit` bucket keys, same basis-point logic. When the native
`relay-flag-py` wheel (PyO3 over the Rust flag-core, Phase 4b) is installed, `evaluate`
routes through it; this pure-Python port stays as the fallback. The shared conformance
suite pins every path to identical decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

try:  # optional native engine — `uv sync --group native` builds the wheel
    import relay_flag_py as _native
except ImportError:  # pragma: no cover - depends on the environment
    _native = None

_FNV_OFFSET = 0x811C9DC5
_FNV_PRIME = 0x01000193
_MASK = 0xFFFFFFFF


def fnv1a(value: str) -> int:
    """FNV-1a, 32-bit, over UTF-8 bytes. Returns an unsigned 32-bit int."""
    h = _FNV_OFFSET
    for byte in value.encode("utf-8"):
        h ^= byte
        h = (h * _FNV_PRIME) & _MASK
    return h


def _bucket(flag_key: str, unit_id: str, salt: str) -> int:
    return fnv1a(f"{flag_key}:{salt}:{unit_id}") % 10000


@dataclass(frozen=True)
class FlagVariant:
    key: str
    weight_bps: int
    prompt_version_id: str | None = None


@dataclass(frozen=True)
class FlagRule:
    key: str
    enabled: bool
    rollout_bps: int
    variants: list[FlagVariant] = field(default_factory=list)


@dataclass(frozen=True)
class EvalContext:
    unit_id: str


@dataclass(frozen=True)
class Decision:
    enabled: bool
    variant: str | None
    reason: str


def native_engine_active() -> bool:
    return _native is not None


def _rule_to_wire(rule: FlagRule) -> str:
    """The camelCase JSON wire format shared by every flag-core binding."""
    return json.dumps(
        {
            "key": rule.key,
            "enabled": rule.enabled,
            "rolloutBps": rule.rollout_bps,
            "variants": [
                {
                    "key": v.key,
                    "weightBps": v.weight_bps,
                    "promptVersionId": v.prompt_version_id,
                }
                for v in rule.variants
            ],
        }
    )


def evaluate(rule: FlagRule, ctx: EvalContext) -> Decision:
    if _native is not None:
        raw = json.loads(_native.evaluate_json(_rule_to_wire(rule), ctx.unit_id))
        return Decision(raw["enabled"], raw["variant"], raw["reason"])
    return evaluate_py(rule, ctx)


def evaluate_py(rule: FlagRule, ctx: EvalContext) -> Decision:
    """Pure-Python reference evaluation (the fallback engine)."""
    if not rule.enabled:
        return Decision(False, None, "flag_disabled")
    if _bucket(rule.key, ctx.unit_id, "gate") >= rule.rollout_bps:
        return Decision(False, None, "out_of_rollout")
    if not rule.variants:
        return Decision(True, None, "no_variants")

    vb = _bucket(rule.key, ctx.unit_id, "variant")
    cumulative = 0
    for variant in rule.variants:
        cumulative += variant.weight_bps
        if vb < cumulative:
            return Decision(True, variant.key, "rollout")
    return Decision(True, rule.variants[-1].key, "rollout")
