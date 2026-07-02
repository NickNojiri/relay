# Deploying Relay (Phase 6)

Production topology:

| Component | Host | Notes |
|-----------|------|-------|
| `apps/studio` (Next.js) | **Vercel** | auto-deploys on push via the Vercel GitHub app |
| `services/prompt-ops` (FastAPI) | **Fly.io** | Docker; `services/prompt-ops/Dockerfile` |
| `services/sync-server` (Yjs WS) | **Fly.io** | Docker; build context = repo root |
| Postgres | **Neon** | serverless; `@relay/db` owns the schema/migrations |
| Redis | **Upstash** | flag cache + sync presence |

Everything is already env-driven (localhost fallbacks for dev), so deploying is configuration,
not code changes. The configs are committed: `apps/studio/vercel.json`,
`services/*/fly.toml`, `services/*/Dockerfile`, `.dockerignore`.

## 0. Prerequisites
Accounts: Vercel, Fly.io, Neon, Upstash. CLIs: `vercel`, `flyctl`, `gh`.

## 1. Provision data
- **Neon** → create a project → copy `DATABASE_URL`.
- **Upstash** → create a Redis database → copy the `rediss://` `REDIS_URL`.
- Apply the schema:
  ```bash
  DATABASE_URL="<neon-url>" corepack pnpm --filter @relay/db db:migrate
  ```

## 2. Gateway → Fly (`services/prompt-ops`)
```bash
cd services/prompt-ops
flyctl launch --no-deploy --copy-config --name relay-prompt-ops   # first time only
flyctl secrets set \
  DATABASE_URL="<neon-url>" \
  REDIS_URL="<upstash-url>" \
  ANTHROPIC_API_KEY="<key>" \
  RELAY_DB_ENABLED=true \
  RELAY_DEFAULT_PROVIDER=anthropic \
  RELAY_API_KEYS="<generate-a-long-random-key>" \
  RELAY_RATE_LIMIT_PER_MINUTE=60
flyctl deploy
```
→ `https://relay-prompt-ops.fly.dev` (health: `GET /health`).

## 3. Sync server → Fly (`services/sync-server`)
The Dockerfile expects the **repo root** as build context:
```bash
flyctl deploy --config services/sync-server/fly.toml \
  --dockerfile services/sync-server/Dockerfile .
```
→ `wss://relay-sync.fly.dev`.

## 4. Studio → Vercel (`apps/studio`)
Import the repo in Vercel (root directory `apps/studio`; `vercel.json` sets the build/install
commands). Set **Production** environment variables:

| Var | Value |
|-----|-------|
| `PROMPT_OPS_URL` | `https://relay-prompt-ops.fly.dev` |
| `PROMPT_OPS_API_KEY` | the key from `RELAY_API_KEYS` (the proxy authenticates server-side) |
| `NEXT_PUBLIC_SYNC_URL` | `wss://relay-sync.fly.dev` |
| `DATABASE_URL` | `<neon-url>` (for the editor/flags/telemetry Server Actions) |

Then `vercel --prod`, or just push to `main` (the Vercel GitHub app auto-deploys).

## 5. Smoke-test the live deployment
- `/playground` → **Run** → tokens stream from the Fly gateway.
- `/editor` → the collaborative draft syncs through the Fly sync-server (open two tabs).
- `/editor` + `/flags` write to Neon; `/telemetry` reads per-variant aggregates back.

## CI/CD
`.github/workflows/deploy.yml` deploys the two Fly services on push to `main`
(needs the `FLY_API_TOKEN` repo secret). Studio is deployed by Vercel's own GitHub integration.

## Env reference
See `.env.example` for the full list. Secrets live in Fly (`flyctl secrets`) and Vercel
(Project → Settings → Environment Variables) — never in the repo.
