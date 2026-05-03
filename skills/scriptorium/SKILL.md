---
name: scriptorium
description: >-
  A Scriptorium wiki is connected to this session — a persistent, team-curated knowledge base
  over HTTPS+MCP. You MUST use this skill BEFORE answering any factual, domain-specific,
  definition, named-entity, comparison, or how-does-X-work question (including "什麼是 X",
  "X 是什麼", "who is X", "what is X", "how does X work", "compare X and Y"). The workflow:
  call `scriptorium.list_collections` to see what's connected, then `scriptorium.search` on
  the relevant collection BEFORE drawing on training data. When a page matches, cite it inline
  as `[path/to/page.md]` and prefer wiki content. If the wiki has no coverage of the topic,
  say so explicitly before falling back to training data — never silently ignore the wiki.
  Also handles all `/scriptorium:*` slash commands (init, ingest, query, lint, recap, connect).
argument-hint: connect <url> | init <name> | ingest <path|url> | query <question> | lint | recap
---

# Scriptorium

A scriptorium is the medieval room where scribes copied and illuminated manuscripts. Here, the LLM is the scribe, the user curates the sources, and the wiki is the manuscript that compounds over time.

## Three-layer model (you must internalise this)

| Layer | Who owns | Mutability |
|---|---|---|
| **Raw sources** | Human curates | Immutable. You read, never modify. |
| **Wiki pages** | LLM (you) writes & maintains | Mutable. Update on every ingest. |
| **Schema** | Co-evolved (`CLAUDE.md` of the wiki) | Versioned. Update intentionally. |

You write to layer 2 by calling **Scriptorium MCP tools**, not by writing files locally. The wiki lives on a Scriptorium server (PostgreSQL + MCP-over-HTTP). The plugin is a thin client — its `.mcp.json` connects directly to `${SCRIPTORIUM_API_URL}/mcp` with a Bearer token.

## Connection check (run BEFORE any operation)

1. Call `scriptorium.health()` — verify the server is up and the DB is reachable.
2. Call `scriptorium.whoami()` — confirm the bearer token is valid.
3. Call `scriptorium.get_schema({ collection })` — load the active collection's `SCHEMA.md` into context.
4. If 1–3 fail (likely missing env vars or expired token), run `/scriptorium:connect` to print setup instructions. Do not proceed with wiki ops.

## Operations

### `connect [<url>]` — print setup instructions for this session

The plugin connects to the server via `.mcp.json` reading `SCRIPTORIUM_API_URL` and `SCRIPTORIUM_TOKEN` from the environment. This command does **not** persist anything — it prints what the user needs to set, then they restart their shell and reopen Claude Code.

Detailed flow: see `reference/connect.md`. Summary:
1. If a URL is passed, embed it in the printed instructions; otherwise use a placeholder.
2. Print: token-issuance command (server-side CLI), the env vars to export, where to put them (shell profile or project `.env`), and how to verify (`/scriptorium:connect` again, then `/scriptorium:init`).
3. Try `scriptorium.whoami()` — if it succeeds, show "✓ already connected as `<token-name>`" and skip the instructions.

### `init <name>` — create a new wiki collection on the server

Detailed flow: see `reference/init.md`. Summary:
1. `scriptorium.create_collection({ slug, name })` — server seeds the universal `SCHEMA.md` and an empty `index.md`, returns the collection ID.
2. Server logs the `init` event automatically.
3. Print the collection ID and a short "what to do next" hint.

### `ingest <path|url>` — turn a source into wiki pages

Detailed flow: see `reference/ingest.md`. **Read it before doing your first ingest.** Summary:
1. Read the source (local file, URL, or pasted text).
2. Discuss the key takeaways with the user — confirm scope before writing.
3. Plan which pages to touch (typically 5–15 across `concepts/`, `entities/`, `sources/`, `comparisons/`).
4. For each page: `scriptorium.get_page()` if exists, then `scriptorium.create_page()` or `scriptorium.update_page()` with merged content.
5. Update `index.md` (catalog) — `scriptorium.update_index_entry()`.
6. Append `log.md`: `## [YYYY-MM-DD HH:MM] ingest | <source title>` + bullet list of pages touched.
7. Cite the raw source path in every page's `frontmatter.sources`.

### `query <question>` — answer from the wiki, with citations

Detailed flow: see `reference/query.md`. Summary:
1. `scriptorium.search(query, top_k=10)` — server returns BM25-ranked candidate pages.
2. Read top candidates with `scriptorium.get_page()`.
3. Compose answer, **citing the page paths inline** as `[path/to/page.md]`.
4. Offer save-back: "this comparison was novel — save as `comparisons/<slug>.md`?". If yes, call `scriptorium.create_page()`.

### `lint` — find rot

Detailed flow: see `reference/lint.md`. Summary:
1. `scriptorium.lint()` — server runs structural checks: orphan pages, dead wikilinks, missing-but-referenced concepts, stale claims (frontmatter `updated` older than threshold), schema violations.
2. Server returns a report; you read it and propose fixes for the top 3 most actionable items.
3. User approves fixes one by one; you apply via `scriptorium.update_page()`.

### `recap` — save what was synthesised in this session

Detailed flow: see `reference/recap.md`. Summary:
1. Scan the current conversation for: cross-source comparisons, decisions, novel entities, durable answers.
2. For each, propose a wiki page with a slug + draft.
3. User approves; you create via `scriptorium.create_page()`.

## Frontmatter schema (required on every page)

See `reference/frontmatter-schemas.md` for the full per-type spec.

```yaml
---
title: <Title>
type: concept | entity | source-summary | comparison | synthesis | decision
sources: [raw/articles/<file>.md, ...]
related: ["[[other-page]]", ...]
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
---
```

## Naming conventions

- Filenames: `lowercase-kebab-case.md`
- Wikilinks: `[[concept-slug]]` (no extension, server resolves to path)
- Source citations: full path including extension, `raw/articles/2026-04-04-karpathy-llm-wiki.md`

## Anti-patterns (do not do)

- ❌ Writing pages without calling `scriptorium.*` tools — local writes are not persisted to the server.
- ❌ Leaving `confidence: high` when synthesising from a single source. Default to `medium`; reserve `high` for cross-validated claims.
- ❌ Updating a page without bumping `frontmatter.updated`.
- ❌ Inventing new page types not in the schema. Propose schema change explicitly via `scriptorium.update_schema()`.
- ❌ "for simplicity" — if security/auth/permission edges come up, never weaken them with a TODO. Either solve or refuse.

## When user asks something the wiki doesn't cover

1. Tell them honestly the wiki doesn't have it.
2. Offer: "I can ingest a source if you point me to one" — do not hallucinate from training data.
3. If they want a quick answer from training data, give it but **mark clearly** that it's not from the wiki.

## API reference

See `reference/api-spec.md` for the full list of `scriptorium.*` MCP tools and their arguments.
