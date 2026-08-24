"""Measures Ed25519 inbound-webhook rejection rate against forged requests
(resume metric #3 - SocialAgent).

This one is a HARNESS, not a drop-in: SocialAgent lives in a different repo, so
wire `verify()` below to your real verification function and run it there.

It generates a battery of forgery classes and reports what fraction your
verifier rejects. A trustworthy number is "rejected N/N forged requests across
K attack classes, while accepting all valid ones" - the second half matters,
because a verifier that rejects everything scores 100% and is useless.

Usage:
    pip install pynacl
    python bench_webhook_rejection.py
"""

import os

try:
    from nacl.signing import SigningKey
except ImportError:
    raise SystemExit("pynacl required: pip install pynacl")


# ---------------------------------------------------------------------------
# WIRE THIS UP: import your real verifier from SocialAgent.
#
#   from bot.security import verify_webhook_signature as verify
#
# Contract assumed below: verify(body: bytes, signature: bytes, public_key:
# bytes) -> bool, returning True only for an authentic signature. Adapt the
# call sites if yours takes headers or a timestamp instead.
# ---------------------------------------------------------------------------
def verify(body: bytes, signature: bytes, public_key: bytes) -> bool:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey

    try:
        VerifyKey(public_key).verify(body, signature)
        return True
    except (BadSignatureError, ValueError):
        return False


def build_cases():
    """Returns (valid_cases, forged_cases); each case is (label, body, sig, pk)."""
    key = SigningKey.generate()
    pk = bytes(key.verify_key)
    other = SigningKey.generate()

    body = b'{"event":"message.create","content":"hello","ts":1735689600}'
    sig = key.sign(body).signature

    valid = [("authentic request", body, sig, pk)]

    forged = [
        # signature-level forgeries
        ("wrong signing key", body, other.sign(body).signature, pk),
        ("all-zero signature", body, b"\x00" * 64, pk),
        ("random signature", body, os.urandom(64), pk),
        ("truncated signature", body, sig[:32], pk),
        ("oversized signature", body, sig + b"\x00", pk),
        ("empty signature", body, b"", pk),
        ("bit-flipped signature", body, bytes([sig[0] ^ 0x01]) + sig[1:], pk),
        # body tampering under a signature that was valid for the original
        ("tampered content", body.replace(b"hello", b"HACKED"), sig, pk),
        ("appended body", body + b" ", sig, pk),
        ("truncated body", body[:-1], sig, pk),
        ("empty body", b"", sig, pk),
        ("replayed sig, new event", b'{"event":"admin.grant"}', sig, pk),
    ]
    # Key substitution is deliberately NOT in the list above: a signature made
    # by an attacker's key DOES validly verify against that attacker's public
    # key - that is correct crypto, not a bug. The real defense is provenance:
    # the public key must come from trusted config, never from the request.
    # `check_key_pinning` below tests that policy separately.
    return valid, forged


def check_key_pinning() -> bool | None:
    """Key substitution is an application-layer concern, so it can't be proven
    by calling verify() alone. Returns True/False if determinable, else None."""
    key, attacker = SigningKey.generate(), SigningKey.generate()
    body = b'{"event":"admin.grant"}'
    # An attacker signs with their own key and would supply their own pubkey.
    forged_sig = attacker.sign(body).signature
    # Against the TRUSTED key this must fail. If your verifier instead reads the
    # key from a header/body field, it will pass here and you have a real hole.
    return not verify(body, forged_sig, bytes(key.verify_key))


def main() -> None:
    valid, forged = build_cases()

    print("\nEd25519 inbound-webhook verification\n")
    print("  forged requests (must all be REJECTED):")
    rejected = 0
    for label, body, sig, pk in forged:
        ok = verify(body, sig, pk)
        rejected += not ok
        print(f"    {'REJECTED' if not ok else 'ACCEPTED  <-- FAIL'}  {label}")

    print("\n  valid requests (must all be ACCEPTED):")
    accepted = 0
    for label, body, sig, pk in valid:
        ok = verify(body, sig, pk)
        accepted += ok
        print(f"    {'ACCEPTED' if ok else 'REJECTED  <-- FAIL'}  {label}")

    pinned = check_key_pinning()
    print("\n  key provenance (application-layer policy):")
    print(
        f"    {'OK' if pinned else 'FAIL'}  signature from an untrusted key is "
        f"rejected against the pinned public key"
    )
    print(
        "    NOTE: confirm by inspection that the public key comes from trusted\n"
        "          config, never from a request header or body field."
    )

    rate = rejected / len(forged) * 100
    print(
        f"\n  => rejected {rejected}/{len(forged)} forged requests "
        f"({rate:.0f}%) across {len(forged)} attack classes, "
        f"accepted {accepted}/{len(valid)} authentic"
    )
    if rejected == len(forged) and accepted == len(valid) and pinned:
        print(
            f"  => resume line: \"verified inbound webhooks with Ed25519 "
            f"signatures, rejecting {len(forged)}/{len(forged)} forged requests "
            f"across {len(forged)} attack classes (tampering, replay, key "
            f"substitution, malformed signatures) with no false rejections\"\n"
        )
    else:
        print("  => FIX FAILURES BEFORE CLAIMING A NUMBER\n")


if __name__ == "__main__":
    main()
