# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy the monorepo structure
COPY package.json pnpm-lock.yaml ./
COPY apps/studio ./apps/studio
COPY packages ./packages

# Install dependencies using pnpm
RUN npm install -g pnpm@9.15.0
RUN pnpm install --frozen-lockfile

# Build the studio
WORKDIR /app/apps/studio
RUN pnpm run build

# Runtime stage
FROM node:20-alpine

WORKDIR /app

# Install pnpm in runtime image
RUN npm install -g pnpm@9.15.0

# Copy only necessary files from builder
COPY package.json pnpm-lock.yaml ./
COPY apps/studio/package.json ./apps/studio/package.json
COPY --from=builder /app/apps/studio/.next ./apps/studio/.next
COPY --from=builder /app/apps/studio/public ./apps/studio/public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/apps/studio/node_modules ./apps/studio/node_modules

WORKDIR /app/apps/studio

EXPOSE 3000

ENV NODE_ENV=production

CMD ["node_modules/.bin/next", "start"]
