# Relay

**An end-to-end prompt-deployment platform.** Author a system prompt collaboratively,
deploy it through an LLM gateway, A/B-test it with feature flags, and track cost &
latency per variant. Polyglot monorepo: **Rust** (flag engine) + **TypeScript** (web +
SDK) + **Python** (LLM gateway).

## Status

| Phase | Scope | State |
|------|-------|-------|
| 0 | Polyglot monorepo scaffold (pnpm + Turborepo + cargo) | ✅ done |
| 1 | Shared foundation: `@relay/db`, `@relay/core`, `@relay/ui` | ✅ done |
| 2 | Walking skeleton (TS-stub engine + studio + gateway) | 🚧 in progress |
| 3 | Real-time collab editing (Yjs CRDT + sync-server) | ⬜ |
| 4 | Rust `flag-core` + 3 bindings (napi-rs / wasm / PyO3) + conformance | ⬜ |
| 5 | Depth & ops (caching, multi-provider, A/B analytics, load test) | ⬜ |
| 6 | Polish & deploy | ⬜ |

### Phase 2 progress
- ✅ `@relay/flag-sdk` — pure-TS flag-eval engine: FNV-1a deterministic bucketing,
  basis-point rollout gate, weighted variant split, and a `FlagClient`. 6 passing tests.
  (Phase 4 swaps the eval internals for the native Rust binding behind the same API.)
- ⬜ `apps/studio` — Next.js: prompt editor → save version, flag admin, telemetry dashboard.
- ⬜ `services/prompt-ops` — FastAPI gateway: resolve variant, proxy LLM, log telemetry.

## Flag model (single source of truth)
A flag has `enabled`, `rolloutBps` (0..10000 basis points), and weighted `variants`
(each mapping to a `promptVersionId`). Evaluation is deterministic on a stable `unitId`,
so the same user always lands in the same variant — and the TS engine and the future
Rust engine produce identical decisions (verified by a conformance suite in Phase 4).

## Packages
- `@relay/flag-sdk` — feature-flag client + evaluation (standalone, no `@relay/*` deps).
- `@relay/db` — Drizzle schema (`prompts`, `prompt_versions`, `flags`, `telemetry`) + client.
- `@relay/core` — zod-validated env + shared domain types.
- `@relay/ui` — Tailwind + shadcn design-system foundation.
- `@relay/typescript-config`, `@relay/eslint-config` — shared tooling.

## Develop

```bash
corepack pnpm install                                # JS deps (pnpm via corepack)
docker compose -f infra/docker-compose.yml up -d     # Postgres + Redis
corepack pnpm test                                   # run workspace tests
corepack pnpm typecheck                              # typecheck workspace
```

The Rust flag engine (Phase 4) builds via the root `cargo` workspace; the Python gateway
(`services/prompt-ops`) is managed with `uv`.
