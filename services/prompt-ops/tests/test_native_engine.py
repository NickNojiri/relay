"""Conformance + parity for the native flag engine (relay-flag-py, PyO3).

Runs only when the wheel is installed (`uv sync --group native`); CI builds it
and exercises this. Without the wheel the suite skips rather than fails.
"""

import json
import os

import pytest

from app.flags import (
    EvalContext,
    FlagRule,
    FlagVariant,
    evaluate,
    evaluate_py,
    native_engine_active,
)

pytestmark = pytest.mark.skipif(
    not native_engine_active(), reason="relay-flag-py wheel not installed"
)

CASES = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "packages", "flag-core", "conformance", "cases.json",
    )
)


def _rule(flag: dict) -> FlagRule:
    return FlagRule(
        key=flag["key"],
        enabled=flag["enabled"],
        rollout_bps=flag["rolloutBps"],
        variants=[
            FlagVariant(v["key"], v["weightBps"], v.get("promptVersionId"))
            for v in flag["variants"]
        ],
    )


def test_native_engine_matches_conformance_fixture():
    with open(CASES, encoding="utf-8") as f:
        cases = json.load(f)
    assert len(cases) > 0
    for c in cases:
        d = evaluate(_rule(c["flag"]), EvalContext(c["unitId"]))
        actual = {"enabled": d.enabled, "variant": d.variant, "reason": d.reason}
        assert actual == c["expected"], (c["flag"]["key"], c["unitId"], actual)


def test_native_engine_agrees_with_python_port():
    rule = FlagRule(
        key="prompt.native-parity",
        enabled=True,
        rollout_bps=7500,
        variants=[FlagVariant("A", 2500), FlagVariant("B", 7500)],
    )
    for i in range(500):
        ctx = EvalContext(f"unit-{i}-{i * 2654435761}")
        assert evaluate(rule, ctx) == evaluate_py(rule, ctx)
