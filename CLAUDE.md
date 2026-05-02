# CLAUDE.md — Scriptorium developer guide

Project memory for Claude Code sessions working **on this repo** (the Scriptorium plugin + server). For the wiki-content schema (the `SCHEMA.md` that lives inside each *served* wiki collection), see `server/templates/SCHEMA.md.tpl`.

## What this repo is

A Claude Code plugin **and** a Bun-based server, packaged as a GitHub Template. One repo = one wiki product. Users hit "Use this template" to spin up a wiki for their team.

The plugin half lives at the repo root (`.claude-plugin/`, `skills/`, `commands/`, `hooks/`, `.mcp.json`). The server half lives in `server/`. They share `LICENSE.md`, `README.md`, `CLAUDE.md`.

## Architecture invariants (don't break these)

1. **Plugin is a thin client.** All wiki state lives on the server. The plugin contains zero markdown content of any wiki — only workflow instructions and `.mcp.json` pointing at a remote endpoint. If you find yourself writing wiki files into `~/Documents/.../wiki/`, you're going wrong.
2. **MCP is the contract.** The server speaks the Model Context Protocol over streamable HTTP at `POST/GET/DELETE /mcp`. There is no separate REST API surface and no local stdio shim — the plugin's `.mcp.json` connects directly. Adding a non-MCP HTTP endpoint requires explicit justification (only `/health` and `/whoami` exist today).
3. **Schema is data, not code.** Page-type frontmatter rules live in `server/src/schema/frontmatter.ts` (Zod). Each collection's `SCHEMA.md` is editable per-wiki and stored in the `collections.schema_md` column.
4. **Frontmatter is the API.** New page types: edit `frontmatter.ts` (server-side validation) and the relevant `templates/SCHEMA-*.md.tpl` (so new collections seed correctly). Don't sprinkle `'concept' | 'entity' | …` enums elsewhere.
5. **Auth: tokens are collection-scoped.** A token grants `r` / `rw` / `admin` on specific collection slugs (or `*`). Never short-circuit `verifyBearer` "for now". (See user's global rule: no `for simplicity` in security boundaries.)
6. **Concurrent writes use CAS.** `update_page` requires `base_version`. Conflict → return error → client must `get_page` and retry. Never blindly overwrite.
7. **Audit log is append-only.** Every state-changing tool writes to the `logs` table. Never `DELETE` or `UPDATE` rows in `logs`.

## Tech choices

| Layer | Choice | Why |
|---|---|---|
| Runtime | **Bun** | Fast, native TS, matches the user's existing web template |
| HTTP | **`node:http` (raw)** | The MCP streamable-HTTP transport wants Node `IncomingMessage`/`ServerResponse`; raw http avoids fighting framework lifecycles |
| MCP | **@modelcontextprotocol/sdk** | Official SDK, `StreamableHTTPServerTransport` |
| DB | **PostgreSQL 16** | `tsvector` FTS, `JSONB`, future `pgvector` upgrade path |
| Validation | **Zod** | Single source of truth for frontmatter shapes |
| Migrations | **Plain SQL files** in `server/src/db/migrations/` | No ORM, no magic, append-only |

## Repo layout

```
scriptorium/
├── .claude-plugin/             # plugin + marketplace manifests
│   ├── plugin.json
│   └── marketplace.json
├── .mcp.json                   # MCP HTTP transport → server's /mcp
├── skills/scriptorium/         # workflow skill (SKILL.md + reference/)
├── commands/                   # slash commands (thin delegations to skill)
├── hooks/                      # UserPromptSubmit + Stop nudges
└── server/                     # the wiki server
    ├── src/
    │   ├── index.ts            # raw http server, /health /whoami /mcp
    │   ├── auth/middleware.ts  # bearer-token verification
    │   ├── db/
    │   │   ├── client.ts       # pg Pool
    │   │   ├── migrate.ts      # migration runner
    │   │   └── migrations/     # NNN_*.sql, append-only
    │   ├── mcp/
    │   │   ├── server.ts       # createMcpServer(auth) factory
    │   │   ├── util.ts         # ok() / err() / collection lookup
    │   │   └── tools/          # one file per tool group
    │   │       ├── health.ts
    │   │       ├── collections.ts
    │   │       ├── pages.ts
    │   │       ├── search.ts
    │   │       ├── log.ts
    │   │       ├── raw.ts
    │   │       └── lint.ts
    │   ├── schema/frontmatter.ts   # Zod frontmatter (per page type)
    │   └── cli/index.ts            # admin CLI: token issue/list/revoke
    ├── templates/
    │   ├── SCHEMA.md.tpl
    │   └── index.md.tpl
    ├── Dockerfile
    ├── docker-compose.yml
    ├── package.json
    ├── tsconfig.json
    └── .env.example
```

## Working in this repo

### Plugin side

- Slash commands are **thin** — they only delegate to the skill. All workflow lives in `skills/scriptorium/SKILL.md` + `reference/*`. Don't put logic in `commands/*.md`.
- The skill must run a connection-check (call `scriptorium.health` then `scriptorium.get_schema`) before any wiki op.
- Detailed flow per verb lives in `skills/scriptorium/reference/<verb>.md`. Keep `SKILL.md` itself under ~250 lines (Claude reads it every time).
- Hooks must stay **fast** (<1s) and **never block** (`set +e` + `exit 0` on any failure).

### Server side

- Run locally: `cd server && bun install && bun run migrate && bun run dev`.
- New tool: add a file under `server/src/mcp/tools/<name>.ts` exporting `register<Name>(server, auth)`, wire it in `server/src/mcp/server.ts`, then update `skills/scriptorium/reference/api-spec.md`.
- New migration: append `server/src/db/migrations/NNN_description.sql`. Never edit applied migrations.
- Auth: every tool handler that mutates state must call `canWrite(auth)`; every tool that reads/writes a collection must call `canAccessCollection(auth, slug)` (via `getCollectionIdBySlug`).

### Adding a new page type

1. Add the Zod variant to `server/src/schema/frontmatter.ts` and include it in `FrontmatterSchema`.
2. Document it in the relevant `server/templates/SCHEMA-*.md.tpl`.
3. Mention it in `skills/scriptorium/reference/frontmatter-schemas.md`.
4. No DB migration needed — frontmatter is `JSONB`.

## Rules (load-bearing)

1. **No `for simplicity` in security.** Auth checks, token scoping, CAS — solve right or refuse. The cost of weakening today is a PII incident in 90 days.
2. **No silent ingests in the skill.** Always discuss with the user before writing pages. Schema drift is the worst form of decay.
3. **Concurrent-write safety from day 1.** All `update_page` paths use CAS. No exceptions.
4. **Audit log is mandatory.** Every state-changing tool writes to `logs`. No "minor" ops slip past.
5. **Plugin and server stay loosely coupled.** They share the MCP tool contract — nothing else. The server can ship without redeploying the plugin and vice versa.

## Things to investigate later (not blockers)

- pgvector for >100K-page wikis (semantic search alongside `ts_rank`).
- MCP `list_changed` notifications when pages are written by other tokens, so concurrent Claude sessions stay synced.
- Per-page ACL (currently collection-level only).
- A small web UI for non-Claude readers (read-only).
- Integration tests with testcontainers spinning up a real Postgres.

## Conventional commits

- `feat(server):` / `feat(plugin):` / `feat(skill):` for new behaviour.
- `fix(...)` / `refactor(...)` / `docs(...)` / `chore(...)` for the rest.
- Keep them in English, with personality. e.g. `fix(server): stop ts_rank from sorting orphans to the top`.
