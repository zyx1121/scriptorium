# {{name}} — Wiki Schema

This file is the contract between humans and the LLM scribes maintaining this wiki. Edit it intentionally — schema changes are audited and bump the collection's `schema_version`.

## Three layers

| Layer | Owns | Mutability |
|---|---|---|
| **Raw sources** | Humans curate | Immutable. The LLM reads, never modifies. |
| **Wiki pages** | LLM scribes write & maintain | Mutable. Updated on every ingest. |
| **Schema** (this file) | Co-evolved | Versioned via `schema_version`. |

## Page types (universal)

Every page declares one `type` in its frontmatter. **All types are available in every collection** — pick what fits the topic. Want a new type? `update_schema` to register it.

| Type | When to use |
|---|---|
| `concept` | Abstract idea, framework, pattern, algorithm |
| `entity` | Specific thing: person, org, project, paper, model, tool, code-symbol, library, dataset, API endpoint, etc. |
| `source-summary` | 1:1 distillation of one raw source (auto-generated on ingest) |
| `comparison` | Side-by-side of 2+ items with a verdict |
| `synthesis` | Cross-source conclusion that didn't exist in any single source |
| `decision` | A judgement call with reasoning and alternatives |
| `paper` | Structured summary of one academic paper you've read |
| `experiment` | A run with hypothesis, setup, result, takeaway |
| `hypothesis` | A claim under investigation, with evidence-for / evidence-against |
| `playbook` | Step-by-step procedure for a recurring task / runbook / SOP |
| `incident` | Post-mortem of an outage / bug / mistake |

## Frontmatter (required on every page)

```yaml
---
title: <Title Case Human Readable>
type: <one of the types above>
sources: [<raw-slug-1>, <raw-slug-2>]
related: ["[[other-page]]", ...]
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
---
```

### Type-specific fields

- **concept**: `domain` (optional)
- **entity**: `entity_kind: person | org | project | paper | model | tool | code-symbol | library | dataset | endpoint | concept-ref`, `canonical_url` (optional)
- **source-summary**: `sources` must have exactly 1 item; optional `length_tokens`
- **comparison**: `items: [[...wikilinks, >=2]]`
- **synthesis**: `sources` must have >= 2 distinct items
- **decision**: `status: active | superseded | reversed`, `alternatives_considered: [...]`, `superseded_by` (only if not active)
- **paper**: `authors`, `year`, `venue`, `arxiv_id` / `doi`, `abstract_summary`, `key_claims`, `limitations`
- **experiment**: `hypothesis_ref`, `setup`, `result`, `takeaway`, `ran_at: YYYY-MM-DD`
- **hypothesis**: `status: open | supported | refuted | inconclusive`, `evidence_for: [[...]]`, `evidence_against: [[...]]`, `last_evaluated`
- **playbook**: `trigger`, `prerequisites`, `steps: [...]`, `last_verified`
- **incident**: `status: open | resolved`, `severity: P0 | P1 | P2 | P3`, `detected_at`, `resolved_at`, `timeline`, `root_cause`, `lessons`, `related_decisions: [[...]]`

## Validation rules (server-enforced)

- `created` ≤ `updated`.
- `confidence: high` requires `sources.length >= 2`.
- All paths in `sources` should exist in `raw_sources` (warning if missing).
- Wikilinks in `related` and body should resolve (lint error if dead).
- Filename slug should match `frontmatter.title` after kebab-casing.

## Naming conventions

- Filenames: `lowercase-kebab-case.md`
- Wikilinks: `[[concept-slug]]` — no `.md` extension, server resolves to path
- Source citations: full path including extension, e.g. `raw/articles/2026-04-04-karpathy-llm-wiki.md`

## Suggested directory layout

Use type-keyed directories, but it's not mandatory — server only cares about the `path` (unique per collection).

```
{{slug}}/
├── concepts/
├── entities/
├── sources/
├── comparisons/
├── synthesis/
├── decisions/
├── papers/
├── experiments/
├── hypotheses/
├── playbooks/
└── incidents/
```

`index.md` is the catalog. The collection `log` is server-managed (append-only audit).

## Operation rules

### Ingest

A single ingest typically touches **5–15 pages**. Always discuss with the human before writing.

1. `upload_raw` the source.
2. Discuss key takeaways; get OK on which entities/concepts deserve pages.
3. For each touched page: `get_page` (if exists), then `create_page` or `update_page` with merged content.
4. Update `index.md` for every new page.
5. `append_log` with `kind: ingest`.

### Query

1. `search` for relevant pages.
2. Read top candidates with `get_page`.
3. Compose answer with **inline citations** `[path/to/page.md]`.
4. If the synthesis is novel, offer to save back as `synthesis/<slug>.md`.
5. `append_log` with `kind: query`.

### Lint

Run periodically. Surface top issues, propose fixes, get human approval per fix. Checks: dead wikilinks, orphan pages, stale claims (>180d), schema violations, confidence inflation.

## Anti-patterns

- ❌ Silent ingests. Always discuss before writing.
- ❌ `confidence: high` from a single source.
- ❌ Updating a page without bumping `frontmatter.updated`.
- ❌ Inventing new page types without `update_schema`.
- ❌ "for simplicity" shortcuts in security/auth/permission.

## Schema version

This collection starts at `schema_version` 1. Every `update_schema` call bumps it.
