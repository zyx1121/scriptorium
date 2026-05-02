# scriptorium server

PostgreSQL + MCP server (over streamable HTTP). One server instance per wiki.

## Run locally

```bash
cd server
cp .env.example .env
# fill in DATABASE_URL + ADMIN_TOKEN

bun install
bun run migrate
bun run dev   # http://localhost:8787
```

## Run with docker-compose

```bash
cp .env.example .env  # set ADMIN_TOKEN
docker compose up -d --build
```

The `server` service depends on `db` (Postgres 16). Migrations run automatically on container start.

## Endpoints

| Path | Method | Purpose | Auth |
|---|---|---|---|
| `/health` | GET | Liveness + DB ping | none |
| `/whoami` | GET | Identify the bearer token | Bearer |
| `/mcp` | POST/GET/DELETE | MCP streamable HTTP transport | Bearer |

## Issuing a token

```bash
# inside the container
docker compose exec server bun run cli token issue --name daisy-rw --scope rw --collection my-wiki

# locally (with ADMIN_TOKEN set)
bun run cli token issue --name daisy-rw --scope rw --collection my-wiki
```

The raw token is shown **once** — copy it. The DB only stores its sha256 hash.

Other CLI subcommands:

```bash
bun run cli token list
bun run cli token revoke --id <token-id>
```

## Token model

- `scopes`: `r`, `rw`, `admin` (admin implies all collections)
- `collection_slugs`: empty array = wildcard (any collection); otherwise restricted to listed slugs
- `expires_at`: optional; expired tokens fail auth

## Schema overview

```
collections      ── one per wiki; holds SCHEMA.md + version
pages            ── markdown body + JSONB frontmatter + tsvector for FTS
page_versions    ── append-only history of every page write
raw_sources      ── immutable raw inputs (papers, articles, URLs)
logs             ── append-only audit (ingest/query/lint/init/etc.)
tokens           ── bearer-token table (sha256 hashed)
```

See `src/db/migrations/001_init.sql` for the canonical schema.

## MCP tools exposed

| Tool | Purpose |
|---|---|
| `health`, `whoami` | Connection / identity |
| `list_collections`, `create_collection`, `get_schema`, `update_schema` | Collection ops |
| `get_page`, `list_pages`, `create_page`, `update_page`, `delete_page` | Page ops (CAS on update) |
| `search` | PG `ts_rank` + `ts_headline` snippets |
| `append_log`, `get_recent` | Audit log |
| `upload_raw`, `get_raw`, `list_raw` | Raw sources |
| `lint` | Dead wikilinks, orphans, stale, schema, confidence inflation |

Plugin clients connect via the `.mcp.json` declared in the Scriptorium plugin (root of this repo).

## Production deploy notes

- **TLS**: terminate at your reverse proxy (Caddy / nginx / Traefik). The server speaks plain HTTP.
- **Backups**: `pg_dump` the `scriptorium` database. The git of the host repo is **not** the source of truth — the database is.
- **Concurrency**: `update_page` uses optimistic concurrency (CAS on `version`). Clients must retry on 409 by re-reading and merging.
- **Audit**: every state-changing op writes to `logs`. Don't `DELETE` from this table.

## Rules

- Don't bypass `verifyBearer` on any state-changing path. No `// for simplicity` shortcuts.
- New routes: add a Zod schema in `src/schema/` first, then wire the route, then add the MCP tool wrapper.
- New migrations: append a new file to `src/db/migrations/` (`NNN_description.sql`). Never edit applied migrations.
