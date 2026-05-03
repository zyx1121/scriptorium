# Contributing to scriptorium

Thanks for showing up. The scriptorium has room for more scribes.

## Quick start

```bash
git clone https://github.com/zyx1121/scriptorium.git
cd scriptorium/server
cp .env.example .env   # set ADMIN_TOKEN + DATABASE_URL
bun install
bun run migrate
bun run dev            # server on :8787
```

For end-to-end testing with Postgres, prefer `docker compose up -d`.

## Project layout

See `CLAUDE.md` (root) for the full repo map. TL;DR:

- `/server` — TypeScript + Bun + PostgreSQL + MCP-over-HTTP
- `/skills`, `/commands`, `/hooks`, `.mcp.json` — Claude Code plugin
- `/docs` — architecture and onboarding guides
- `/assets` — README banner only

## Conventions

- **Conventional Commits**: `feat(scope):`, `fix(scope):`, `refactor(scope):`, `docs:`, `chore:`. The `scope` is `server`, `plugin`, `skill`, or omitted.
- Commit messages may have personality. `fix(server): stop ts_rank from sorting orphans to the top` beats `fix typo`.
- One logical change per commit. Atomic commits make `git bisect` actually useful.
- Update `CHANGELOG.md` under `## [Unreleased]` for any user-visible change.

## Code style

- TypeScript: `strict: true`, no implicit `any`. `bun run typecheck` must pass.
- No comments unless the **why** is non-obvious. Don't narrate the code.
- Zod schemas live in `server/src/schema/`. Do not duplicate type definitions across files.
- New SQL goes in `server/src/db/migrations/NNN_description.sql`. **Never edit applied migrations.**

## Adding a new MCP tool

1. New file in `server/src/mcp/tools/<name>.ts` exporting `register<Name>(server, auth)`.
2. Wire it in `server/src/mcp/server.ts`.
3. Document it in `skills/scriptorium/reference/api-spec.md`.
4. Bump `version` in both `.claude-plugin/plugin.json` and `server/package.json`.

## Adding a new page type

1. Add a Zod variant to `server/src/schema/frontmatter.ts` and include it in `FrontmatterSchema`.
2. Document it in `server/templates/SCHEMA.md.tpl` and `skills/scriptorium/reference/frontmatter-schemas.md`.
3. No DB migration needed — frontmatter is `JSONB`.

## Architecture invariants

These are **load-bearing**. Don't break them without an RFC.

1. The plugin is a thin client. Wiki state lives only on the server.
2. The server speaks MCP-over-HTTP at `/mcp`. The plugin's `.mcp.json` connects directly. No bundled stdio shim.
3. Auth is bearer-token, collection-scoped, sha256-hashed at rest. Never short-circuit `verifyBearer`.
4. `update_page` uses CAS on `version`. Conflicts → 409 → client retries.
5. `logs` is append-only. Don't `DELETE` from it; use `prune_logs(days)` for retention.

## Pull requests

- Branch from `main`: `<type>/<short-description>` (e.g. `feat/cross-collection-search`).
- Open the PR with a one-line summary + test plan + any breaking-change notes.
- Wait for CI green before requesting review.

## Reporting bugs

Open an issue with: what you ran, what you expected, what you got, server `/health` response, and (if applicable) a curl reproduction. Logs from `docker compose logs server` help.

## License

By contributing you agree your code ships under [MIT](LICENSE.md).
