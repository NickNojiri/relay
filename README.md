# Relay Monorepo

## Current State
**Phase 0 (Scaffolding)** and **Phase 1 (Shared Foundation)** are complete.

- **Monorepo:** Configured using `pnpm` workspaces and Turborepo.
- **Packages:**
  - `@relay/db`: Drizzle ORM schema defined with Postgres integration (`prompts`, `promptVersions`, `flags`, `telemetry`).
  - `@relay/core`: Shared Zod environment variables and Typescript types.
  - `@relay/ui`: Tailwind CSS + shadcn foundational setup ready for Next.js usage.
  - `@relay/typescript-config`: Centralized `tsconfig.json` bases.

## Next Steps: Phase 2 (Walking Skeleton)
Future models should pick up at **Phase 2**, which involves:
1. **`flag-sdk`**: Scaffold a pure-TypeScript stub for the feature flag evaluation engine.
2. **`apps/studio`**: Create a Next.js (App Router) application.
   - Build a prompt editor to save to the DB.
   - Build an admin view to create a rollout flag.
   - Build a telemetry dashboard.
3. **`services/prompt-ops`**: Scaffold a FastAPI LLM gateway (Python) to proxy requests to an LLM provider, evaluate flags (using a Python stub), and log telemetry.

See `.gemini/antigravity-ide/brain/.../task.md` and `implementation_plan.md` in the conversation artifacts for the full checklist and design documentation.
