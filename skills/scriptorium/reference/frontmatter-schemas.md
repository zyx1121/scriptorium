# Frontmatter schemas (per page type)

Every wiki page has YAML frontmatter. Type determines the required fields. The server validates on `create_page` / `update_page` — bad frontmatter is a hard reject.

## Common (all types)

```yaml
title: <Title Case Human Readable>
type: <one of: concept | entity | source-summary | comparison | synthesis | decision>
sources: [raw/articles/<file>.md, ...]   # at least 1
related: ["[[other-page]]", ...]         # may be empty
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
```

## `concept`

Abstract idea, framework, or pattern.

```yaml
type: concept
domain: <area, e.g. "machine-learning" | "auth" | "operations">
```

## `entity`

A specific person, organisation, project, paper, model, tool.

```yaml
type: entity
entity_kind: person | org | project | paper | model | tool
canonical_url: <optional homepage / arxiv / github>
```

## `source-summary`

A 1:1 distillation of one raw source. Auto-generated on `ingest`.

```yaml
type: source-summary
sources: [raw/articles/<exact-one-file>.md]   # exactly 1
length_tokens: <int, approx>
```

## `comparison`

A side-by-side of 2+ items.

```yaml
type: comparison
items: ["[[item-a]]", "[[item-b]]", ...]      # at least 2
```

## `synthesis`

Cross-source conclusion that didn't exist in any single source.

```yaml
type: synthesis
sources: [...]                                # >= 2 distinct sources required
```

## `decision`

A judgement call made (often during a session) with reasoning.

```yaml
type: decision
status: active | superseded | reversed
alternatives_considered: ["...", "..."]
superseded_by: <path-to-newer-decision>       # only if status != active
```

## Validation rules (server-enforced)

- `created` ≤ `updated`.
- All paths in `sources` must exist in `raw_sources` table.
- All `[[wikilinks]]` in `related` must resolve OR be marked `<missing>` (lint warning).
- `confidence: high` requires `len(sources) >= 2` (or override flag).
- Filename slug must equal `frontmatter.title` after kebab-casing.

## Adding a new type

Don't invent silently. Propose via `scriptorium.update_schema({ collection, addition: ... })` — the server logs schema changes as audited events.
