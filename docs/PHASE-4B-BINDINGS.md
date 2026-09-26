# Phase 4b — Native flag-engine bindings (✅ SHIPPED)

**Status:** implemented (2026-07-02) on a Linux environment, exactly as this plan prescribed.
All three bindings are thin wrappers over `flag_core::evaluate_json` (the `serde` feature adds
the shared camelCase wire format to the core), and CI's `bindings` job builds each one and runs
every conformance suite. The original deferral rationale below is kept for the record.

## What this is
The Rust `flag-core` engine (`packages/flag-core`) ships as **one verified core with three
language bindings**, so every runtime evaluates flags with byte-identical logic:

| Crate | Tool | Consumer |
|-------|------|----------|
| `packages/flag-node` | napi-rs | `@relay/flag-sdk` (replaces the pure-TS eval) |
| `packages/flag-wasm` | wasm-bindgen | edge / browser SDK |
| `packages/flag-py` | PyO3 + maturin | `services/prompt-ops` (replaces the Python port) |

Each binding is a thin wrapper over `flag_core::evaluate`. All three — plus a Rust test that
reads `packages/flag-core/conformance/cases.json` — must produce the SAME decisions as the
existing TS (`flag-sdk`) and Python (`prompt-ops`) suites. That is the "one verified core,
zero SDK drift" story from the plan.

## Why it's deferred (blocked on the current dev machine, not a code problem)
1. **`cargo` cannot reach crates.io** — the network does TLS interception and Git/cargo's
   Windows schannel backend fails the certificate revocation check
   (`CRYPT_E_NO_REVOCATION_CHECK`), so napi-rs / wasm-bindgen / pyo3 can't be fetched.
2. **No MSVC linker** (`link.exe`) — native artifacts (`.node`, wheel/`.pyd`, `.wasm`) can't
   be linked locally without VS Build Tools.

The engine itself is done: `flag-core` is written, `cargo check` + `clippy` are clean, and its
unit tests run on CI (Linux).

## How to implement (when unblocked — do it on Linux / GitHub Actions)
1. **`flag-core`** — add a serde-based `tests/conformance.rs` that reads `conformance/cases.json`
   and asserts every case (mirrors the TS/Python conformance tests).
2. **`flag-node`** (napi-rs) — `#[napi]` wrapper exporting `evaluate(rule, unitId) -> Decision`,
   `build.rs`, `package.json` napi config; wire into `@relay/flag-sdk` behind the existing
   `evaluate()` signature, keeping the pure-TS path as a fallback.
3. **`flag-wasm`** (wasm-bindgen) — `#[wasm_bindgen] evaluate(ruleJson, unitId)`, built with
   `wasm-pack`; use as the edge/browser fallback in `flag-sdk`.
4. **`flag-py`** (PyO3 + maturin) — `#[pymodule]` exposing `evaluate`; build a wheel, add to
   `services/prompt-ops`, swap `app/flags.py` for the native call (keep the port as fallback).
5. **CI** — add jobs to build each binding and run the cross-binding conformance suite.

## Acceptance — met
`cargo test --workspace --features flag-core/serde` green (incl. the fixture conformance test),
and TS / Python / Rust — plus the napi addon, the wasm build, and the PyO3 wheel — all assert
the same `cases.json` decisions:

- Rust: `packages/flag-core/tests/conformance.rs` (struct + JSON-boundary paths)
- napi: `packages/flag-sdk/src/native.test.ts` (conformance + 500-case TS-parity)
- wasm: `packages/flag-wasm/test/conformance.test.mjs`
- PyO3: `services/prompt-ops/tests/test_native_engine.py` (conformance + 500-case parity)

The native paths are opt-in with verified fallbacks: `enableNativeEngine()` in the TS SDK
(pure-TS otherwise, always in browsers), `uv sync --group native` for the gateway (Python port
otherwise).
