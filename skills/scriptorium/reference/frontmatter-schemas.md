# Frontmatter schemas (per page type)

Every wiki page has YAML frontmatter. `type` determines the required fields. The server validates on `create_page` / `update_page` — bad frontmatter is a hard reject.

All 11 types below are **always available**. Pick the one that fits the topic. Unused types just stay unused.

## Common (all types)

```yaml
title: <Title Case Human Readable>
type: concept | entity | source-summary | comparison | synthesis | decision | paper | experiment | hypothesis | playbook | incident
sources: [raw/articles/<file>.md, ...]   # may be empty unless the type requires
related: ["[[other-page]]", ...]         # may be empty
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
```

## `concept`

Abstract idea, framework, pattern, algorithm.

```yaml
type: concept
domain: <area, e.g. "machine-learning" | "auth" | "operations">   # optional
```

## `entity`

A specific named thing.

```yaml
type: entity
entity_kind: person | org | project | paper | model | tool
            | code-symbol | library | dataset | endpoint | concept-ref
canonical_url: <optional homepage / arxiv / github>
```

Use `code-symbol` for functions/classes/modules, `library` for npm/pypi packages, `dataset` for data, `endpoint` for an API URL, `concept-ref` to link to an external concept that lives in another wiki.

## `source-summary`

A 1:1 distillation of one raw source. Auto-generated on `ingest`.

```yaml
type: source-summary
sources: [raw/articles/<exact-one-file>.md]   # exactly 1
length_tokens: <int, approx>                  # optional
```

## `comparison`

A side-by-side of 2+ items, with a verdict in the body.

```yaml
type: comparison
items: ["[[item-a]]", "[[item-b]]", ...]      # at least 2 wikilinks
```

## `synthesis`

Cross-source conclusion that didn't exist in any single source.

```yaml
type: synthesis
sources: [...]                                # >= 2 distinct sources required
```

## `decision`

A judgement call with reasoning and alternatives.

```yaml
type: decision
status: active | superseded | reversed
alternatives_considered: ["...", "..."]
superseded_by: <path-to-newer-decision>       # only if status != active
```

## `paper`

Structured summary of one academic paper you've actually read.

```yaml
type: paper
authors: [...]
year: <int>
venue: <optional>
arxiv_id: <optional>
doi: <optional>
abstract_summary: <2-4 sentence distillation>
key_claims: ["...", ...]
limitations: ["...", ...]
```

## `experiment`

A run with hypothesis, setup, result, takeaway.

```yaml
type: experiment
hypothesis_ref: "[[hypothesis-slug]]"   # optional wikilink to the hypothesis page
setup: <what was run>
result: <what came out>
takeaway: <what we learned>
ran_at: YYYY-MM-DD
```

## `hypothesis`

A claim under investigation.

```yaml
type: hypothesis
status: open | supported | refuted | inconclusive
evidence_for: ["[[paper-x]]", "[[experiment-y]]", ...]
evidence_against: [...]
last_evaluated: YYYY-MM-DD                # optional
```

## `playbook`

Step-by-step procedure for a recurring task / runbook / SOP.

```yaml
type: playbook
trigger: <when to run this>
prerequisites: [...]
steps: [...]                              # at least 1
last_verified: YYYY-MM-DD                 # optional
```

## `incident`

Post-mortem of an outage / bug / mistake.

```yaml
type: incident
status: open | resolved
severity: P0 | P1 | P2 | P3
detected_at: <ISO datetime>
resolved_at: <ISO datetime>               # optional
timeline: [...]
root_cause: <string>                      # optional
lessons: ["...", ...]
related_decisions: ["[[decision-slug]]", ...]
```

## Validation rules (server-enforced)

- `created` ≤ `updated`.
- `confidence: high` requires `sources.length >= 2`.
- `incident.detected_at` and `resolved_at` must be ISO 8601 datetimes (e.g. `2026-05-04T14:32:00Z`); other date fields are `YYYY-MM-DD`.
- All paths in `sources` should exist in `raw_sources` (warning if missing).
- All `[[wikilinks]]` in `related` should resolve (lint **error** if dead, lint **warning** if `[[name]]` matches multiple pages by basename — disambiguate with the full path `[[folder/name]]`).
- Filename slug should broadly match `frontmatter.title` kebab-cased (lint **warning**, not a hard reject — names with diacritics or punctuation rarely round-trip cleanly).

## Adding / changing a type

Don't invent silently. Edit the collection's `SCHEMA.md` via `scriptorium.update_schema({ collection, schema_md })` — the server logs schema changes as audited events.
