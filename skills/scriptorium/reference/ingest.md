# `/scriptorium:ingest <path|url>` flow

> **Pre-flight**: SKILL.md's connection check (`health` → `whoami` → `list_collections` → resolve active collection → `get_schema`) must run before any page is created or updated. The schema is what makes `create_page` not 422 on the first attempt.

## Purpose

Turn one source into many wiki pages. **A single ingest typically touches 5–15 pages.** Read this whole document before your first ingest of a session.

## Steps

### 1. Acquire raw

- Local path: read with the Read tool.
- URL: WebFetch (or ask user to drop into `raw/`).
- Pasted text: write to `raw/articles/<date>-<slug>.md` first, then proceed.
- Compute a stable raw slug: `<YYYY-MM-DD>-<title-slug>.md`.

### 2. Upload to server

- `scriptorium.upload_raw({ slug, content, kind: "article" | "paper" | "url" })`
- Server stores immutable copy in `raw_sources` table + records SHA.

### 3. Discuss with user (mandatory)

Before writing any wiki page, summarise the source in 5–10 bullets and ask:
- "Which entities/concepts here are worth their own page?"
- "Are any of these in conflict with existing pages? (I'll check)"

Get explicit OK before proceeding. **Do not skip this** — silent ingests cause schema drift and content rot.

### 4. Plan touches

For each candidate page:
- `scriptorium.search(slug)` to check existence.
- Decide: create / update / skip.
- Write a one-line plan to chat: `"Will create concepts/llm-wiki.md, update entities/karpathy.md, create comparisons/wiki-vs-rag.md"`.

### 5. Write pages

For each page in the plan:

```js
// existing page
const page = await scriptorium.get_page({ collection, path });
const merged = mergeContent(page.content, newSection);
await scriptorium.update_page({
  collection,
  path,
  content: merged,
  frontmatter: { ...page.frontmatter, updated: today, sources: dedup([...page.frontmatter.sources, raw_slug]) }
});

// new page
await scriptorium.create_page({
  collection,
  path: "concepts/llm-wiki.md",
  content: pageBody,
  frontmatter: {
    title: "LLM Wiki",
    type: "concept",
    sources: [raw_slug],
    related: ["[[karpathy]]", "[[rag]]", "[[memex]]"],
    created: today,
    updated: today,
    confidence: "medium"
  }
});
```

### 6. Update index

- `scriptorium.update_index_entry({ collection, path, summary, type })`

### 7. Append log

```js
scriptorium.append_log({
  collection,
  kind: "ingest",
  actor: "claude",
  payload: {
    source: raw_slug,
    pages_created: [...],
    pages_updated: [...]
  }
});
```

### 8. Lint pass (optional, fast)

- `scriptorium.lint({ collection, scope: "touched_pages", paths: [...] })`
- Surface any issues immediately — don't wait for the next full lint.

## Conflict handling

If a new claim contradicts an existing page:
1. Don't overwrite silently.
2. Add a `### Conflicting evidence` section in the existing page citing both sources.
3. Bump `frontmatter.confidence` down one notch (`high → medium`, `medium → low`).
4. Mention the conflict in the user-facing summary.

## Anti-patterns

- ❌ Skipping step 3 (discuss with user). The wiki is your team's brain — don't overwrite it autonomously.
- ❌ Creating pages with one-source `confidence: high`.
- ❌ Forgetting to update `index.md` and `log.md` (these are the navigation/audit surfaces).
- ❌ Inventing new entity types. Stick to schema or propose a change.
