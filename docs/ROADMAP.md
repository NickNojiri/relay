# Roadmap — finishing Relay for maximum resume impact

**Goal:** turn the remaining work into interview-getting material. One honest framing up front:
an ATS scans *your resume text*, not your GitHub. So the plan below does two things at once —
(1) finishes the project in the order that produces **live URLs and real numbers**, and
(2) ends with **draft resume bullets** that use those URLs/numbers and hit the keywords
recruiters and ATS filters actually search for.

Priority = resume ROI per hour of work, not engineering completeness.

---

## Where we are

Phases 0–6 are done (see README status table): the product works end-to-end locally, the
3-language conformance story is real, security audit is clean, and deploy configs + runbook +
CD workflow are committed. What's missing is everything a recruiter can *verify in 30 seconds*:
a live URL, measured numbers, and the deferred native-bindings flagship.

---

## Phase 7 — Ship it live (highest ROI, do first)

A deployed product beats any amount of code. "Live demo" link on a resume is the single
strongest differentiator for a personal project.

- [ ] Execute **[docs/DEPLOY.md](DEPLOY.md)** end-to-end: Neon (Postgres) → Upstash (Redis) →
      Fly.io (gateway + sync-server) → Vercel (studio). All free tiers.
- [ ] Set the `FLY_API_TOKEN` repo secret so `.github/workflows/deploy.yml` gives you real
      **CI/CD on push to main** (that's a resume line, not just a convenience).
- [ ] Smoke-test per the runbook (streaming playground, two-tab collab, telemetry round-trip).
- [ ] Put the live URL at the top of the README + add a seeded demo prompt/flag so a visitor
      sees the A/B split working without setup.

**Effort:** ~half a day (accounts + copy-paste runbook). **Unlocks:** every bullet below can say
*"deployed"* instead of *"built"*.

## Phase 8 — Measure it (numbers make bullets believable)

ATS matches keywords; humans shortlist **quantified** bullets. Everything here already exists
as scaffolding — it just needs to be *run* against the live deployment and written down.

- [ ] Run the existing **k6** load-test script against the Fly gateway; record throughput,
      p95/p99 latency, and error rate. Re-run with the flag cache cold vs warm and record the
      delta (that's your "improved latency X%" bullet).
- [ ] Record telemetry over a synthetic A/B run: cost-per-request delta between two prompt
      versions (that's your "reduced LLM cost X%" bullet — the product's whole pitch).
- [ ] Publish the numbers in the README (small "Performance" section) so bullets are auditable.

**Effort:** ~half a day. **Rule:** no number goes on the resume before it's measured here.

## Phase 9 — Phase 4b native bindings (the flagship engineering story)

Already fully planned in **[docs/PHASE-4B-BINDINGS.md](PHASE-4B-BINDINGS.md)**; it was blocked
only by the old dev machine, and the plan itself says to do it on Linux/GitHub Actions — which
is now exactly where this work runs. This is the deepest keyword vein in the project: **Rust,
FFI, WebAssembly, napi-rs, PyO3, cross-language testing**.

- [x] `flag-core`: serde-based `tests/conformance.rs` over `conformance/cases.json`.
- [x] `flag-node` (napi-rs) → wired into `@relay/flag-sdk` with the pure-TS path as fallback.
- [x] `flag-wasm` (wasm-bindgen / wasm-pack) → edge/browser path.
- [x] `flag-py` (PyO3 + maturin) → swapped into `prompt-ops` with the Python port as fallback.
- [x] CI jobs building all three bindings + running the cross-binding conformance suite.

**✅ Done** — acceptance met: TS, Python, Rust, and all three bindings assert identical
decisions on the shared fixture file (see the updated [4b doc](PHASE-4B-BINDINGS.md)).

## Phase 10 — Hardening & presentation (interview-talk-track material)

Each item here is a common interview question ("how would you productionize this?") answered
in code, plus a keyword ATS filters look for.

- [x] **Auth:** opt-in API-key auth on the gateway (`RELAY_API_KEYS`, Bearer / x-api-key,
      constant-time compare); the studio proxy authenticates server-side
      (keywords: authentication, authorization, middleware).
- [x] **Rate limiting** on the gateway (`RELAY_RATE_LIMIT_PER_MINUTE`, per-key sliding
      window, 429 + Retry-After; in-process per instance — Redis-backed is the
      scale-out follow-up).
- [ ] **Observability:** OpenTelemetry traces on the request path gateway → provider, surfaced
      in the telemetry dashboard (keywords: OpenTelemetry, distributed tracing, observability).
- [ ] **E2E tests:** one Playwright flow — create prompt → flag it → run playground → see
      telemetry (keywords: Playwright, end-to-end testing).
- [ ] **Presentation:** 30–60s demo GIF in the README, CI + coverage badges, pinned repo with
      a description + topics set on GitHub (recruiters *do* click).

**Effort:** 2–3 days, items independent — cherry-pick if time is short. Priority within the
phase: presentation > auth > observability > rate limiting > e2e.

---

## Draft resume bullets (fill the ⟨numbers⟩ from Phase 8)

XYZ format — *accomplished X, measured by Y, by doing Z*. Every claim below is true today or
becomes true at the marked phase; never put a bullet on the resume before its phase is done.

- Built and **deployed** (P7) a full-stack LLM prompt-deployment platform — collaborative
  editor, feature-flag A/B rollouts, and per-version cost/latency telemetry — in a polyglot
  monorepo (**TypeScript/Next.js, Python/FastAPI, Rust**) on Vercel, Fly.io, Neon, and Upstash.
- Designed a deterministic **feature-flag engine in Rust** with TypeScript and Python ports,
  proving byte-identical behavior across all three via a **shared conformance test suite**
  (zero SDK drift).
- Shipped the engine as **native bindings — napi-rs (Node), WebAssembly, and PyO3
  (Python)** — so every runtime evaluates flags with one verified Rust core, with
  CI running the cross-binding conformance suite on every push.
- Built **real-time collaborative editing** with CRDTs (**Yjs**) over WebSockets, supporting
  concurrent multi-user prompt drafting with presence/awareness.
- Engineered a **multi-provider LLM gateway** (Anthropic Claude, OpenAI, Ollama) with **SSE
  token streaming** and a TTL flag cache; (P8) load-tested with **k6** to ⟨N⟩ req/s at
  p95 ⟨X⟩ ms.
- (P8) Instrumented per-request token/latency **telemetry** enabling data-driven prompt A/B
  tests; demonstrated a ⟨Y⟩% cost difference between prompt variants in production.
- Hardened the public gateway with **API-key authentication** and per-key **rate limiting**
  (constant-time comparison, sliding-window 429s with Retry-After), keeping keys
  server-side behind a Next.js proxy.
- Automated **CI/CD with GitHub Actions and Docker** (lint, typecheck, five test suites
  across three languages, deploy-on-push to Fly.io); drove `pnpm audit` from 8 advisories
  to **0 known vulnerabilities** via dependency upgrades (Next 15, React 19, Drizzle 0.45).

## ATS keyword coverage → where the project proves it

| Keyword cluster | Evidence |
|---|---|
| TypeScript, React, Next.js, Node.js | `apps/studio` (App Router, Server Actions) |
| Python, FastAPI | `services/prompt-ops` |
| Rust, WebAssembly, FFI | `packages/flag-core` + Phase 9 bindings |
| PostgreSQL, Redis, ORM | Drizzle + Neon, Upstash cache |
| WebSockets, real-time, CRDT | `services/sync-server`, Yjs |
| LLM / GenAI / prompt engineering, A/B testing | the whole product; Anthropic/OpenAI providers |
| CI/CD, GitHub Actions, Docker | `.github/workflows`, Dockerfiles, Fly deploy |
| Microservices, distributed systems | studio + gateway + sync-server topology |
| Testing (unit, integration, E2E), Vitest, pytest, Playwright | 3 suites today + Phase 10 |
| Cloud (Vercel, Fly.io, serverless), performance/load testing | Phases 7–8 |
| Authentication, rate limiting | `services/prompt-ops/app/security.py` + studio proxy |
| Observability, OpenTelemetry | Phase 10 (remaining) |

**Sequence:** 7 → 8 → 9 → 10. If you only have one weekend: do 7 and 8, then put the live URL
and the measured numbers on the resume — that's most of the value.
