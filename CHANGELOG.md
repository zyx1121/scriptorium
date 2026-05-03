# Changelog

All notable changes to **scriptorium** are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.3.0] — 2026-05-03

### Added
- CI workflow (`.github/workflows/ci.yml`) — typecheck + docker build smoke on every push / PR.
- `CONTRIBUTING.md`, `SECURITY.md`, `docs/onboarding-teammate.md`.
- Migration 003: `prune_logs(retention_days)` PG function — drops old `page_read` / `search` rows, keeps high-value events forever.
- Per-token rate limit on `/mcp` (60 req/min) and per-IP rate limit on `/dashboard` (20 req/min). In-memory token bucket, no external dep.
- `/scriptorium:status` slash command — endpoint / token / scopes / collections / server health on one screen.
- Dashboard **page detail view** at `/dashboard?collection=…&path=…` — frontmatter, content, recent reads. All paths in the dashboard tables are now clickable links.
- `server/scripts/backup.sh` — `pg_dump` with 14-day rotation, runnable inside the container or from the host via `docker compose exec`.

### Changed
- **Dashboard redesigned** to a monochrome bash aesthetic — pure black/white, monospace, no rounded corners, no shadows, no gradients, full-bleed (no max-width, breathing-room padding only).
- Versions across plugin / server pkg / `VERSION` const aligned at `0.3.0`.

## [0.2.0] — 2026-05-03

### Added
- Observability dashboard: `stats` MCP tool + server-rendered `/dashboard` HTML.
- `get_page` and `search` now write fire-and-forget log entries (`page_read`, `search`).
- Migration 002: GIN + path indexes on `logs.payload` for fast aggregations.
- Banner image (`assets/banner.jpg`) on README — medieval scribe with a laptop.

### Changed
- **Schema unification**: merged `default` / `research` / `team-knowledge` templates into one universal `SCHEMA.md.tpl`. Eleven page types (`concept`, `entity`, `source-summary`, `comparison`, `synthesis`, `decision`, `paper`, `experiment`, `hypothesis`, `playbook`, `incident`) are available in every collection.
- `entity.entity_kind` expanded with `code-symbol`, `library`, `dataset`, `endpoint`, `concept-ref` so codebase ingest is a first-class case.
- `create_collection` no longer takes a `schema_template` parameter.
- Plugin skill description rewritten in imperative voice — "MUST use this skill BEFORE answering any factual / definition / entity question" — to encourage auto-trigger over training-data fall-through.

### Migration notes
- Existing collections seeded with the old default template can `update_schema` to the new `SCHEMA.md.tpl`. The `propagation-model` collection was migrated in this release.

## [0.1.0] — 2026-05-02

### Added
- Initial plugin: `.claude-plugin/plugin.json` + `marketplace.json`, `.mcp.json` (HTTP transport pointed at the server's `/mcp`).
- Skill `scriptorium` + reference docs (`connect`, `init`, `ingest`, `query`, `lint`, `recap`, `frontmatter-schemas`, `api-spec`).
- Six slash commands: `/scriptorium:connect | init | ingest | query | lint | recap`.
- Hooks: `UserPromptSubmit` (intent tagger) + `Stop` (recap detector).
- Server: TypeScript on Bun, raw `node:http`, `@modelcontextprotocol/sdk` streamable-HTTP transport, PostgreSQL 16 with `tsvector` FTS.
- 18 MCP tools: `health`, `whoami`, `list_collections`, `create_collection`, `get_schema`, `update_schema`, `get_page`, `list_pages`, `create_page`, `update_page` (CAS), `delete_page`, `search`, `append_log`, `get_recent`, `upload_raw`, `get_raw`, `list_raw`, `lint`.
- Bearer-token auth (sha256-hashed at rest), collection-scoped, admin CLI for token issuance.
- Three SCHEMA templates (default / research / team-knowledge) + index.md.
- Dockerfile + `docker-compose.yml` + `.env.example`.

[Unreleased]: https://github.com/zyx1121/scriptorium/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/zyx1121/scriptorium/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/zyx1121/scriptorium/releases/tag/v0.1.0
