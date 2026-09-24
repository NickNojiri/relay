# Relay studio (Next.js). Build context = repo root, like the sync-server:
#   docker build -f apps/studio/Dockerfile -t relay-studio .
# Production hosting is Vercel; this image exists for the local demo (infra/demo).
FROM node:22-alpine
RUN corepack enable
WORKDIR /repo

COPY . .
RUN corepack pnpm install --frozen-lockfile --filter studio...
RUN corepack pnpm --filter studio build

WORKDIR /repo/apps/studio
ENV NODE_ENV=production
EXPOSE 3000
CMD ["corepack", "pnpm", "start"]
