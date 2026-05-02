# {{name}} — Wiki Schema

This file is the contract between humans and the LLM scribes maintaining this wiki. Edit it intentionally — schema changes are audited and bump the collection's `schema_version`.

## Three layers

| Layer | Owns | Mutability |
|---|---|---|
| **Raw sources** | Humans curate | Immutable. The LLM reads, never modifies. |
| **Wiki pages** | LLM scribes write & maintain | Mutable. Updated on every ingest. |
| **Schema** (this file) | Co-evolved | Versioned via `schema_version`. |

## Page types

Every page declares one of these `type`s in its frontmatter. Adding a new type requires updating this schema.

| Type | When to use |
|---|---|
| `concept` | An abstract idea, framework, or pattern. |
| `entity` | A specific person, organisation, project, paper, model, or tool. |
| `source-summary` | A 1:1 distillation of one raw source. Auto-generated on ingest. |
| `comparison` | A side-by-side of 2+ items with a verdict. |
| `synthesis` | A cross-source conclusion that didn't exist in any single source. |
| `decision` | A judgement call with reasoning and alternatives considered. |

## Frontmatter (required on every page)

```yaml
---
title: <Title Case Human Readable>
type: concept | entity | source-summary | comparison | synthesis | decision
sources: [<raw-slug-1>, <raw-slug-2>]
related: ["[[other-page]]", ...]
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
---
```

### Type-specific fields

- **concept**: `domain` (optional)
- **entity**: `entity_kind: person | org | project | paper | model | tool`, `canonical_url` (optional)
- **source-summary**: `sources` must have exactly 1 item
- **comparison**: `items: [[...wikilinks, >=2]]`
- **synthesis**: `sources` must have >= 2 distinct items
- **decision**: `status: active | superseded | reversed`, `alternatives_considered: [...]`, `superseded_by` (only if not active)

## Validation rules (server-enforced)

- `created` ≤ `updated`.
- `confidence: high` requires `sources.length >= 2`.
- All paths in `sources` should exist in `raw_sources` (warning if missing).
- Wikilinks in `related` and body should resolve (lint error if dead).
- Filename slug must match `frontmatter.title` after kebab-casing.

## Naming conventions

- Filenames: `lowercase-kebab-case.md`
- Wikilinks: `[[concept-slug]]` — no `.md` extension, server resolves to path
- Source citations: full path including extension, e.g. `raw/articles/2026-04-04-karpathy-llm-wiki.md`

## Directory layout

```
{{slug}}/
├── concepts/        # type: concept
├── entities/        # type: entity
├── sources/         # type: source-summary
├── comparisons/     # type: comparison
├── synthesis/       # type: synthesis
└── decisions/       # type: decision
```

`index.md` lives at the root and is the catalog. `log.md` is server-managed (append-only audit).

## Operation rules

### Ingest

A single ingest typically touches **5–15 pages**. Always discuss with the human before writing.

1. `upload_raw` the source.
2. Discuss key takeaways with the human; get OK on which entities/concepts deserve pages.
3. For each touched page: `get_page` (if exists), then `create_page` or `update_page` with merged content.
4. Update `index.md` for every new page.
5. `append_log` with `kind: ingest`.

### Query

1. `search` for relevant pages.
2. Read top candidates with `get_page`.
3. Compose answer with **inline citations** `[path/to/page.md]`.
4. If the synthesis is novel, offer to save it back as `synthesis/<slug>.md`.
5. `append_log` with `kind: query`.

### Lint

Run periodically. Surface top issues, propose fixes, get human approval per fix.

Checks: dead wikilinks, orphan pages, stale claims (>180d), schema violations, confidence inflation.

## Anti-patterns

- ❌ Silent ingests. Always discuss before writing.
- ❌ `confidence: high` from a single source.
- ❌ Updating a page without bumping `frontmatter.updated`.
- ❌ Inventing new page types without updating this schema.
- ❌ "for simplicity" shortcuts in security/auth/permission.

## Schema version

This is `schema_version` 1. Every `update_schema` call bumps it.
