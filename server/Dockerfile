FROM oven/bun:1.1-alpine AS deps
WORKDIR /app
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile || bun install

FROM oven/bun:1.1-alpine AS runtime
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY package.json tsconfig.json ./
COPY src ./src
COPY templates ./templates

ENV NODE_ENV=production
ENV PORT=8787
EXPOSE 8787

# Migrate on start, then serve.
CMD ["sh", "-c", "bun src/db/migrate.ts && bun src/index.ts"]
