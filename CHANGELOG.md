# Changelog

All notable changes to **scriptorium** are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.5.0] — 2026-05-06

A security-and-hygiene release. Six items from the 0.4 review's "must-fix" list, eight more from "should-fix", three new operational guides. No new MCP tools, no schema migration that touches user data — just shoring up the foundations before piling on more features.

### Security
- **CLI `ADMIN_TOKEN` is now verified, not assumed.** Migration 005 introduces a `server_config` key/value table; `bun run migrate` hashes `ADMIN_TOKEN` and stores it. Subsequent CLI calls compare with `timingSafeEqual` and refuse if it doesn't match — `ADMIN_TOKEN=anything bun run cli` no longer mints admin tokens. Rotation procedure documented in `docs/operations.md`.
- **`update_schema` now goes through `getCollectionIdBySlug`.** Audit log writes use the resolved `cid` directly instead of a sub-select that could miss on a race and leave NULL ghost rows.
- **`append_log` rejects forged kinds.** Allowed values are the four documented workflow kinds (`ingest`, `recap`, `query`, `lint`) or anything prefixed `client:`. The five system kinds (`page_read`, `search`, `init`, `schema_update`, `delete_page`) are reserved — clients can't poison stats or cover their tracks.
- **Dashboard cookie session.** `?token=<raw>` on first visit is swapped for an `HttpOnly Secure SameSite=Strict` cookie scoped to `/dashboard`, then redirected to a clean URL. Subsequent navigation is cookie-only — no token in browser history, no token in Referer, no token in the proxy access log past the initial redirect. `Secure` flag follows `X-Forwarded-Proto: https`. New `/dashboard/logout` clears the cookie.
- **MCP session-init throttle.** Separate token bucket for new MCP sessions (5 burst, 5/min sustained) on top of the per-token request bucket (120 burst, 2 req/sec). Idle sessions sweep every 5 min, 30 min TTL — a leaked token spamming inits can no longer eat RAM forever.

### Fixed
- `IncidentSchema.detected_at` and `resolved_at` now require ISO 8601 datetimes (matching the per-page schema doc); previously `z.string()` accepted `"yesterday"`.
- `lint` resolves wikilinks against full paths, not just basenames. `[[notes/foo]]` and `[[refs/foo]]` no longer collide; ambiguous basename links now surface as a `warning` instead of silently false-negative orphan checks.
- `backup.sh` writes to a `.partial` tempfile and only renames on `size > 0`. If `pg_dump` and `docker` are both missing, the script fails loudly instead of producing a 0-byte `.pgdump` that gets rotated away in 14 days.
- Rate-limit comment now describes capacity/refill correctly. `60 req/min` was always misleading wording for a token bucket.

### Plugin
- **SKILL.md connection check is now correct.** Five steps: `health` → `whoami` → `list_collections` → resolve active collection → `get_schema(collection)`. Previous flow called `get_schema` without ever resolving the slug.
- **Stop hook removed.** Its stdout was never injected into Claude's context (different lifecycle to `UserPromptSubmit`); the nudge was a no-op. `recap-detector.sh` deleted; `intent-tagger.sh` on `UserPromptSubmit` now handles save-back signals exclusively.
- `intent-tagger.sh` falls back to `jq` if `python3` is missing, with explicit untrusted-input warning at top of file.
- Every reference doc (`init`, `ingest`, `query`, `lint`, `recap`) now has a "Pre-flight" reminder of the SKILL.md connection check, so progressive disclosure of a single ref doesn't bypass it.
- `plugin.json` gets `keywords` for marketplace discovery.
- `frontmatter-schemas.md` slug rule downgraded from "must" to "lint warning" — names with diacritics rarely round-trip kebab-cased.

### Docs
- New `docs/deploy.md` — production hardening: TLS at the edge, reverse proxy configs (Caddy / nginx / Cloudflare Tunnel), per-user token issuance, off-host backups.
- New `docs/operations.md` — daily/weekly/monthly cadence: backup verify + restore-test, log retention, token rotation, admin rotation, server upgrades, monitoring patterns.
- New `docs/disaster-recovery.md` — runbooks by severity: DB lost, server compromise, admin/member token leaked, schema corruption, page rollback. With actual SQL, not philosophy.
- `SECURITY.md` gains a threat model section ("what we're defending against, what we're not"), updated hardening checklist, token rotation pointer.
- `CONTRIBUTING.md` clarifies CLI invocation: same script, two contexts (`bun run cli` for local dev, `docker compose exec -T server bun run cli` for compose).

### CI / tooling
- `.github/dependabot.yml` weekly npm + docker base image scans, monthly GitHub Actions. Grouped PRs to keep noise down.

### Migration notes
- Migration 005 is additive (creates `server_config`). On first apply with a populated `ADMIN_TOKEN` env, the hash is seeded; subsequent migrate runs see "already set" and ignore the env. To rotate the admin token: `DELETE FROM server_config WHERE key='admin_token_hash'`, change the env, re-run migrate. See `docs/operations.md`.
- Plugin clients on 0.4.x keep working — every change is server-internal or additive in the skill.

## [0.4.0] — 2026-05-04

### Added
- **Users abstraction**. Migration 004 introduces a `users` table (id, email, name, role, created_at) with `role IN (admin | member | viewer)`. Each token can now be linked to a user via `tokens.user_id`, so a single human's mac + laptop + phone tokens aggregate to one identity.
- `logs.actor_user_id` column — every state-changing action records both the token name (device label) and the user who owns it.
- CLI: `user create / list / delete` + `token issue --user <email>`. Deleting a user revokes all their active tokens.
- New MCP tool: `team_activity({ collection?, days? })` — per-user breakdown of ingests / searches / reads / last-active. Optionally scoped to a single collection.
- Dashboard: collection view now has a **by user** section; new **team page** at `/dashboard?view=team` with cross-collection user activity, unassigned-token list, and recent-actions feed.
- Auth context (`AuthContext`) carries `userId / userEmail / userName / userRole`, so future tools can do per-role permission checks without a second DB hit.

### Migration notes
- Migration 004 backfills the existing `loki-mac` token and its 13 historical log entries to a seeded `loki@winlab.tw` admin user. Other tokens not matching `loki%` stay unassigned (still functional, listed under "unassigned actors" on the team page).
- Plugin clients on 0.3.0 keep working — `team_activity` is additive and the new dashboard sections are additive HTML.

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

[Unreleased]: https://github.com/zyx1121/scriptorium/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/zyx1121/scriptorium/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/zyx1121/scriptorium/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/zyx1121/scriptorium/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/zyx1121/scriptorium/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/zyx1121/scriptorium/releases/tag/v0.1.0
