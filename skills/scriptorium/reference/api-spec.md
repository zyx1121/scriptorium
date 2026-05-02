# Scriptorium MCP tools (reference)

The plugin exposes these via `.mcp.json` SSE connection. Server-side they're typed; below is the contract.

## Connection / health

| Tool | Args | Returns |
|---|---|---|
| `scriptorium.health` | — | `{ ok, version, db_ok }` |
| `scriptorium.whoami` | — | `{ token_name, scopes, collections: [...] }` |
| `scriptorium.list_collections` | — | `[{ slug, name, schema_version }]` |

## Schema

| Tool | Args | Returns |
|---|---|---|
| `scriptorium.get_schema` | `{ collection }` | full `CLAUDE.md` content of that collection |
| `scriptorium.update_schema` | `{ collection, schema }` | `{ schema_version }` (audited) |
| `scriptorium.create_collection` | `{ slug, name }` | `{ collection_id }` |

## Pages

| Tool | Args | Returns |
|---|---|---|
| `scriptorium.get_page` | `{ collection, path }` | `{ path, content, frontmatter, version }` |
| `scriptorium.list_pages` | `{ collection, filter? }` | `[{ path, title, type, updated }]` |
| `scriptorium.create_page` | `{ collection, path, content, frontmatter }` | `{ path, version }` |
| `scriptorium.update_page` | `{ collection, path, content, frontmatter, base_version }` | `{ version }` (CAS check) |
| `scriptorium.delete_page` | `{ collection, path, reason }` | `{ ok }` (soft delete; appears in audit) |

## Index / log

| Tool | Args | Returns |
|---|---|---|
| `scriptorium.get_index` | `{ collection }` | `index.md` rendered |
| `scriptorium.update_index_entry` | `{ collection, path, summary, type }` | `{ ok }` |
| `scriptorium.get_recent` | `{ collection, n }` | last N log entries |
| `scriptorium.append_log` | `{ collection, kind, actor, payload }` | `{ ok }` |

## Search

| Tool | Args | Returns |
|---|---|---|
| `scriptorium.search` | `{ collection, query, top_k, filter? }` | `[{ path, title, snippet, score }]` |

## Raw sources

| Tool | Args | Returns |
|---|---|---|
| `scriptorium.upload_raw` | `{ collection, slug, content, kind }` | `{ raw_id, sha }` |
| `scriptorium.get_raw` | `{ collection, slug }` | `{ slug, content, kind, ingested_at }` |
| `scriptorium.list_raw` | `{ collection }` | `[{ slug, kind, ingested_at }]` |

## Lint

| Tool | Args | Returns |
|---|---|---|
| `scriptorium.lint` | `{ collection, scope: "all" \| "touched_pages", paths? }` | `{ errors, warnings, info }` |
| `scriptorium.save_lint_report` | `{ collection, report, fixed, deferred }` | `{ report_path }` |

## Concurrency

`update_page` requires `base_version` — server does CAS. If conflict, returns `409 conflict` with the current version; you must `get_page` again, merge, retry.

## Error codes

- `400` — bad input (e.g. invalid frontmatter)
- `401` — token invalid/expired
- `403` — token lacks scope for this collection
- `404` — path not found
- `409` — version conflict (CAS)
- `422` — schema validation failed (returns details)
- `5xx` — server error; retry with backoff is OK for idempotent ops only
