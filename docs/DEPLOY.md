# Deploying Relay

## Status: Deployment Paused

Relay was successfully deployed to production (Vercel, Fly.io, Neon) and verified working end-to-end.
The live deployment has been taken down to avoid ongoing hosting costs. This guide provides exact
redeploy steps (all secrets as placeholders) for when you're ready to ship.

For demos and development, use the **local docker-compose setup** (see below) with Echo and Ollama —
no cloud spend, instant startup, perfect for screen-recording.

## Production topology (when redeployed)

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

---

## Demo Locally (Fast, Zero Cost)

Use docker-compose to bring up the full stack with Echo and Ollama (instant startup, perfect for
screen-recording and testing). No cloud accounts, no secrets needed.

```bash
make demo
```

This starts:
- **Studio** → http://localhost:3000
- **Gateway** → http://localhost:8000 (Echo provider, instant responses)
- **Sync server** → ws://localhost:3001
- **Postgres** (in container)
- **Ollama** (optional; for local LLM experimentation)

The demo uses in-process flag cache and rate limiter — no Redis needed. Create a prompt in `/editor`,
set flags in `/flags`, and run in `/playground` — all writes go to the containerized Postgres.

See `docker-compose.yml` and `.env.example` for config options.

---

## Redeploy to Production

When you're ready to ship live again, follow these exact steps. All secrets shown as placeholders —
fill in with your real values. Never commit secrets to the repo.

### 0. Prerequisites
- Accounts: **Vercel**, **Fly.io**, **Neon**, **Upstash**
- CLIs installed: `vercel`, `flyctl`
- Generate a strong API key for the gateway:
  ```bash
  openssl rand -hex 32
  ```

### 1. Provision data
- **Neon** → create a project → copy `DATABASE_URL` (format: `postgresql://...?sslmode=require`)
- **Upstash** → create a Redis database → copy the `rediss://...` `REDIS_URL`
- Apply the schema:
  ```bash
  DATABASE_URL="postgresql://user:pass@host/db?sslmode=require" \
  corepack pnpm --filter @relay/db db:migrate
  ```

### 2. Deploy gateway to Fly (`services/prompt-ops`)
```bash
# First time only: create the app
flyctl launch --no-deploy --copy-config --name relay-prompt-ops

# Set secrets (use your real values)
flyctl secrets set --app relay-prompt-ops \
  DATABASE_URL="postgresql://user:pass@host/db?sslmode=require" \
  REDIS_URL="rediss://default:password@host:port" \
  ANTHROPIC_API_KEY="sk-ant-..." \
  RELAY_DB_ENABLED=true \
  RELAY_DEFAULT_PROVIDER=anthropic \
  RELAY_DEFAULT_MODEL=claude-3-5-haiku-latest \
  RELAY_API_KEYS="your-generated-key-here" \
  RELAY_RATE_LIMIT_PER_MINUTE=60

# Deploy
flyctl deploy --remote-only \
  --config services/prompt-ops/fly.toml \
  --dockerfile services/prompt-ops/Dockerfile services/prompt-ops
```

Health check: `curl https://relay-prompt-ops.fly.dev/health` → `{"status":"ok"}`

### 3. Deploy sync server to Fly (`services/sync-server`)
```bash
# First time only: create the app
flyctl launch --no-deploy --copy-config --name relay-sync-nojiri

# Deploy (no secrets needed; runs in-memory)
flyctl deploy --remote-only \
  --config services/sync-server/fly.toml \
  --dockerfile services/sync-server/Dockerfile .
```

Result: `wss://relay-sync-nojiri.fly.dev`

### 4. Deploy studio to Vercel (`apps/studio`)
Import the repository in the [Vercel dashboard](https://vercel.com):
1. Root directory: `apps/studio`
2. Framework preset auto-detects (Next.js via `vercel.json`)
3. Set **Production** environment variables:

| Variable | Value |
|----------|-------|
| `PROMPT_OPS_URL` | `https://relay-prompt-ops.fly.dev` |
| `PROMPT_OPS_API_KEY` | (same as `RELAY_API_KEYS` above) |
| `NEXT_PUBLIC_SYNC_URL` | `wss://relay-sync-nojiri.fly.dev` |
| `DATABASE_URL` | (same Neon URL from step 1) |

4. Deploy: either push to `main` (auto-deploy via Vercel GitHub app) or `vercel --prod`

### 5. Smoke-test
- **`/playground`** → send a message → tokens stream from the live gateway
- **`/editor`** → open in two browser tabs → edits sync in real-time via the sync-server
- **`/flags`** → create a flag (writes to Neon)
- **`/telemetry`** → after a few playground runs, see per-variant token/latency aggregates

### 6. CI/CD (optional)
`.github/workflows/deploy.yml` auto-deploys both Fly services on push to `main`. To enable:
1. Generate a deploy token: `flyctl tokens create deploy`
2. Add to GitHub → Settings → Secrets → `FLY_API_TOKEN`
3. Studio redeploys via Vercel's own GitHub integration (no manual secret needed)

---

## Environment reference
See `.env.example` for the complete list of tunable environment variables. Production secrets
live in Fly (`flyctl secrets`) and Vercel (Project → Settings → Environment Variables) — never
commit them to the repo.
