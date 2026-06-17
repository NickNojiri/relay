"""The Python engine must match the shared conformance fixture
(packages/flag-core/conformance/cases.json). The TS and Rust suites assert the
same fixture, so all three engines provably agree."""

import json
import os

from app.flags import EvalContext, FlagRule, FlagVariant, evaluate

CASES = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "packages", "flag-core", "conformance", "cases.json",
    )
)


def test_conformance_fixture_matches():
    with open(CASES, encoding="utf-8") as f:
        cases = json.load(f)
    assert len(cases) > 0
    for c in cases:
        flag = c["flag"]
        rule = FlagRule(
            key=flag["key"],
            enabled=flag["enabled"],
            rollout_bps=flag["rolloutBps"],
            variants=[
                FlagVariant(v["key"], v["weightBps"], v.get("promptVersionId"))
                for v in flag["variants"]
            ],
        )
        d = evaluate(rule, EvalContext(c["unitId"]))
        actual = {"enabled": d.enabled, "variant": d.variant, "reason": d.reason}
        assert actual == c["expected"], (flag["key"], c["unitId"], actual, c["expected"])
