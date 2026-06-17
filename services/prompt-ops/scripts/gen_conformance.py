"""Generate the shared flag-evaluation conformance fixture.

Runs the (verified) Python engine over a spread of (flag, unit) inputs and writes
the expected decisions to packages/flag-core/conformance/cases.json. The TS
(@relay/flag-sdk) and Rust (flag-core) test suites then assert that *their*
engines produce the identical decisions — that's the cross-language "zero drift"
guarantee. Regenerate with:  uv run python scripts/gen_conformance.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.flags import EvalContext, FlagRule, FlagVariant, evaluate  # noqa: E402


def variant(key: str, weight_bps: int, pv: str | None = None) -> dict:
    return {"key": key, "weightBps": weight_bps, "promptVersionId": pv}


def build_specs() -> list[tuple[dict, str]]:
    specs: list[tuple[dict, str]] = []

    even = {"key": "prompt.support-bot", "enabled": True, "rolloutBps": 10000,
            "variants": [variant("A", 5000), variant("B", 5000)]}
    specs += [(even, f"user-{i}") for i in range(10)]

    specs.append(({"key": "prompt.off", "enabled": False, "rolloutBps": 10000,
                   "variants": [variant("A", 10000)]}, "user-1"))
    specs.append(({"key": "prompt.zero", "enabled": True, "rolloutBps": 0,
                   "variants": [variant("A", 10000)]}, "user-1"))
    specs.append(({"key": "prompt.empty", "enabled": True, "rolloutBps": 10000,
                   "variants": []}, "user-1"))

    uneven = {"key": "prompt.tone", "enabled": True, "rolloutBps": 10000,
              "variants": [variant("A", 3000), variant("B", 7000)]}
    specs += [(uneven, f"user-{i}") for i in range(6)]

    partial = {"key": "prompt.beta", "enabled": True, "rolloutBps": 5000,
               "variants": [variant("A", 10000)]}
    specs += [(partial, f"user-{i}") for i in range(6)]

    return specs


def main() -> None:
    cases = []
    for flag, unit in build_specs():
        rule = FlagRule(
            key=flag["key"],
            enabled=flag["enabled"],
            rollout_bps=flag["rolloutBps"],
            variants=[FlagVariant(v["key"], v["weightBps"], v.get("promptVersionId")) for v in flag["variants"]],
        )
        d = evaluate(rule, EvalContext(unit))
        cases.append({
            "flag": flag,
            "unitId": unit,
            "expected": {"enabled": d.enabled, "variant": d.variant, "reason": d.reason},
        })

    out = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..",
                     "packages", "flag-core", "conformance", "cases.json")
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)
        f.write("\n")
    print(f"wrote {len(cases)} cases to {out}")


if __name__ == "__main__":
    main()
