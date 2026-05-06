# `/scriptorium:recap` flow

> **Pre-flight**: SKILL.md's connection check (`health` → `whoami` → `list_collections` → resolve active collection → `get_schema`) must run before saving any page.

## Purpose

Save the durable insights from this session to the wiki before the conversation evaporates. Recap is the explicit save-back primitive.

## When recap is right

- After a long debugging / research / planning session that produced a non-trivial conclusion.
- When the user said "actually save this" or "let's not lose this".
- When the `UserPromptSubmit` intent-tagger hook (`hooks/intent-tagger.sh`) injects a save-back hint into your context.

## Steps

### 1. Scan the conversation

Look for:
- **Decisions** — "we'll go with X because Y" → likely a `decision` page.
- **Comparisons** — "X vs Y" with verdict → `comparison` page.
- **Novel entities** — names/orgs that don't yet have a page → `entity` page.
- **Synthesis** — multi-source conclusions the wiki doesn't have → `synthesis` page.
- **Anti-patterns / lessons** — "we tried X and it failed because Z" → `decision` page with "alternatives considered".

### 2. Propose

Show the user a numbered list:
```
Recap candidates from this session:

1. [comparison] wiki-vs-rag
   "RAG re-derives knowledge per query; wiki compounds. Wiki wins ≤100K tokens."
2. [decision] postgres-not-markdown-storage
   "Chose PG over markdown+git for multi-user concurrent writes."
3. [entity] mimir-norse-mythology
   "Considered for naming; rejected due to AI-tool collision."

Save which? (1,2,3 / all / none)
```

### 3. Draft each approved page

For each, draft body + frontmatter. Show before saving:
```
=== synthesis/wiki-vs-rag.md ===
---
title: Wiki vs RAG
type: comparison
sources: [raw/articles/2026-04-04-karpathy-llm-wiki.md]
related: ["[[llm-wiki]]", "[[rag]]"]
created: 2026-05-02
updated: 2026-05-02
confidence: medium
---

# Wiki vs RAG

[body]

OK to save? (y/N)
```

### 4. Save

```js
scriptorium.create_page({ collection, path, content, frontmatter });
scriptorium.update_index_entry({ ... });
scriptorium.append_log({ kind: "recap", payload: { saved: paths } });
```

### 5. Optional follow-ups

Suggest:
- "Want me to lint the touched area?" → `/scriptorium:lint`
- "Want me to ingest the actual source for these claims?" → `/scriptorium:ingest`

## Anti-patterns

- ❌ Saving every back-and-forth — only durable insights.
- ❌ Save-back without the user seeing the draft first.
- ❌ Inventing a `confidence: high` recap from a single conversation. Default `medium`.
