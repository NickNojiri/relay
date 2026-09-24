# Deploying Relay

## Status: taken down to avoid hosting cost

Relay ran in production on **Vercel** (studio), **Fly.io** (gateway + sync server) and **Neon**
(Postgres), deployed from GitHub Actions. Post-deploy checks from CI confirmed the gateway served
authenticated traffic from Fly (`/health`: 5.7 s cold start, 0.18 s warm). The deployment has since
been torn down so it costs nothing while idle. Everything needed to bring it back is committed; the
steps below recreate it exactly, with every secret shown as a `<placeholder>`.

To show Relay without any cloud spend, run it locally instead: [Local demo](#local-demo).

| Component | Host | Build |
|-----------|------|-------|
| `apps/studio` (Next.js) | Vercel | Vercel GitHub integration, `apps/studio/vercel.json` |
| `services/prompt-ops` (FastAPI gateway) | Fly.io app `relay-prompt-ops` | `services/prompt-ops/Dockerfile`, context = that directory |
| `services/sync-server` (Yjs WebSocket) | Fly.io app `relay-sync-nojiri` | `services/sync-server/Dockerfile`, context = repo root |
| Postgres | Neon | schema owned by `@relay/db` (`packages/db/drizzle/`) |

No Redis is needed: the gateway's flag cache and rate limiter are in-process
(`services/prompt-ops/app/repository.py`, `app/security.py`) and the sync server keeps rooms in
memory. Both Fly apps therefore run as single machines.

---

## Local demo

Needs only Docker (Docker Desktop on Windows/macOS).

```bash
make demo              # Linux/macOS
.\scripts\demo.ps1     # Windows PowerShell
```

This builds and starts Postgres, the gateway, the sync server and the studio from
`infra/demo/compose.yml`, waits until every service is healthy, and prints:

| Service | URL |
|---------|-----|
| Studio | http://localhost:3000 |
| Gateway | http://localhost:8000 (API key `demo-key`) |
| Sync server | ws://localhost:1234 |

The database is seeded (`infra/demo/seed.sql`) with a `prompt.support-bot` prompt, two versions
(terse vs. empathetic) and a 50/50 A/B flag, so every page works on first load:

- **/playground**: Run. Change the unit ID (`user-1`, `user-2`, …) to land on variant A or B.
- **/telemetry**: per-variant request count, tokens and latency from those runs.
- **/editor**: open it in two windows; edits sync live through the sync server.
- **/flags**: change the split or roll a variant out to 100%.

**Providers.** The gateway uses one provider for all requests, set by `RELAY_DEFAULT_PROVIDER`.

- `make demo` uses **Echo**: it streams your input back instantly and needs no model or key. It
  shows the routing, the A/B split and the telemetry, but both variants print the same text, so it
  won't show that the prompts behave differently.
- `make demo-ollama` (or `.\scripts\demo.ps1 -Ollama`) also starts **Ollama** and pulls
  `llama3.2:1b` (about 1.3 GB on first run), so responses come from a real model on your machine
  and the terse and empathetic variants visibly differ. Use this mode for recordings. Use
  `OLLAMA_MODEL=<model>` (or `-OllamaModel <model>`) for another model.

`make demo-down` stops the stack and keeps its data. `make demo-reset` also wipes the data, and the
next `make demo` re-seeds it. `make demo-logs` follows the logs.

---

## Redeploy to production

Deploys run from GitHub Actions (`.github/workflows/deploy.yml`), so no local CLI is required. The
workflow is **manual-only**, so merging to `main` can't quietly recreate paid infrastructure.

### 1. Create the accounts and keys

| What | Where | Placeholder used below |
|------|-------|------------------------|
| Postgres database | Neon → New project | `<DATABASE_URL>` (`postgresql://…?sslmode=require`) |
| Fly access token | Fly → Account → Access Tokens → **org** token (it has to create apps) | `<FLY_API_TOKEN>` |
| Anthropic key | console.anthropic.com → API Keys | `<ANTHROPIC_API_KEY>` |
| Gateway API key | any long random string, e.g. `openssl rand -hex 32` | `<GATEWAY_KEY>` |

### 2. Apply the schema to Neon

Either paste `packages/db/drizzle/0000_right_domino.sql` into Neon's SQL Editor and run it, or:

```bash
DATABASE_URL="<DATABASE_URL>" corepack pnpm --filter @relay/db db:migrate
```

The database starts empty. To start with the demo prompt and flag, also run
`infra/demo/seed.sql` there.

### 3. Add the GitHub Actions secrets

Repo → Settings → Secrets and variables → Actions → **Secrets**:

| Secret | Value |
|--------|-------|
| `FLY_API_TOKEN` | `<FLY_API_TOKEN>` |
| `DATABASE_URL` | `<DATABASE_URL>` |
| `ANTHROPIC_API_KEY` | `<ANTHROPIC_API_KEY>` |
| `RELAY_API_KEYS` | `<GATEWAY_KEY>` (comma-separate several to rotate) |

Under **Variables**, set `FLY_ORG` to your Fly org slug if it isn't `personal`.

The workflow refuses to deploy without `RELAY_API_KEYS`. An empty key list turns gateway auth off
and would expose the Anthropic key to anyone.

### 4. Deploy the gateway and sync server

Actions → **Deploy services** → Run workflow. It creates both Fly apps if they don't exist, stages
the gateway secrets, deploys both services, then probes `/health` twice and prints both apps' status
and logs. Expected:

```
https://relay-prompt-ops.fly.dev/health  ->  {"status":"ok"}
wss://relay-sync-nojiri.fly.dev
```

Fly app names are global. If `relay-prompt-ops` or `relay-sync-nojiri` is taken, change `app =` in
`services/*/fly.toml` and the names in `deploy.yml`.

<details>
<summary>Same thing from a terminal with <code>flyctl</code></summary>

```bash
flyctl apps create relay-prompt-ops --org <FLY_ORG>
flyctl apps create relay-sync-nojiri --org <FLY_ORG>

flyctl secrets set --app relay-prompt-ops --stage \
  DATABASE_URL="<DATABASE_URL>" \
  ANTHROPIC_API_KEY="<ANTHROPIC_API_KEY>" \
  RELAY_API_KEYS="<GATEWAY_KEY>" \
  RELAY_DB_ENABLED=true \
  RELAY_DEFAULT_PROVIDER=anthropic \
  RELAY_DEFAULT_MODEL=claude-3-5-haiku-latest \
  RELAY_RATE_LIMIT_PER_MINUTE=60

# flyctl resolves --config relative to the app directory: run from inside it.
(cd services/prompt-ops && flyctl deploy --remote-only --config fly.toml --dockerfile Dockerfile)

# The sync server's build context is the repo root.
flyctl deploy --remote-only \
  --config services/sync-server/fly.toml \
  --dockerfile services/sync-server/Dockerfile .
```
</details>

### 5. Deploy the studio to Vercel

Vercel → Add New → Project → import this repo. Set **Root Directory** to `apps/studio` (the
framework and build commands come from `apps/studio/vercel.json`). Add these Production
environment variables, then deploy:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `<DATABASE_URL>` |
| `PROMPT_OPS_URL` | `https://relay-prompt-ops.fly.dev` |
| `PROMPT_OPS_API_KEY` | `<GATEWAY_KEY>` (must be one of `RELAY_API_KEYS`) |
| `NEXT_PUBLIC_SYNC_URL` | `wss://relay-sync-nojiri.fly.dev` |

The studio calls the gateway from its server-side route (`apps/studio/app/api/chat/`), so the
gateway key never reaches the browser. `NEXT_PUBLIC_SYNC_URL` is compiled into the build, so
redeploy after changing it.

### 6. Smoke test

1. `curl https://relay-prompt-ops.fly.dev/health` → `{"status":"ok"}`. The first request can take a
   few seconds while Fly starts the machine.
2. `curl -X POST https://relay-prompt-ops.fly.dev/v1/chat` → `401` (auth is on).
3. Studio **/playground** → Run → tokens stream from Anthropic through the gateway.
4. **/editor** in two windows → edits sync.
5. **/telemetry** → the playground runs appear, split by variant.

---

## Tear down

What was deleted to stop the costs. Do the same after a temporary redeploy:

- **Fly**: `flyctl apps destroy relay-prompt-ops` and `flyctl apps destroy relay-sync-nojiri`,
  or Dashboard → app → Settings → Delete app.
- **Vercel**: Project → Settings → Delete Project.
- **Neon**: Project settings → Delete project.
- **Secrets**: revoke the Fly token and the Anthropic key, and delete the GitHub Actions secrets.
