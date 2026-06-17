from app.flags import EvalContext, FlagRule, FlagVariant, evaluate, fnv1a


def _rule(**over) -> FlagRule:
    base = dict(
        key="prompt.support-bot",
        enabled=True,
        rollout_bps=10000,
        variants=[FlagVariant("A", 5000), FlagVariant("B", 5000)],
    )
    base.update(over)
    return FlagRule(**base)


def test_fnv1a_canonical_vectors():
    # The exact numbers @relay/flag-sdk asserts — cross-language parity, no Rust needed.
    assert fnv1a("") == 2166136261
    assert fnv1a("a") == 3826002220


def test_disabled():
    d = evaluate(_rule(enabled=False), EvalContext("u1"))
    assert (d.enabled, d.variant, d.reason) == (False, None, "flag_disabled")


def test_stable_for_unit():
    assert evaluate(_rule(), EvalContext("user-42")) == evaluate(_rule(), EvalContext("user-42"))


def test_zero_rollout():
    d = evaluate(_rule(rollout_bps=0), EvalContext("user-42"))
    assert d.enabled is False
    assert d.reason == "out_of_rollout"


def test_split_is_roughly_even():
    n = 10_000
    a = sum(1 for i in range(n) if evaluate(_rule(), EvalContext(f"user-{i}")).variant == "A")
    assert 0.45 < a / n < 0.55
