# Yjs CRDT sync server. Build context = repo root:
#   docker build -f services/sync-server/Dockerfile -t relay-sync .
FROM node:22-alpine
RUN corepack enable
WORKDIR /repo

COPY . .
RUN corepack pnpm install --frozen-lockfile --filter sync-server...

WORKDIR /repo/services/sync-server
ENV SYNC_SERVER_PORT=1234
EXPOSE 1234
CMD ["corepack", "pnpm", "start"]
