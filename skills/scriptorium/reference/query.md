# `/scriptorium:query <question>` flow

## Purpose

Answer a question using the wiki, with citations. Optionally save the synthesised answer back as a new wiki page.

## Steps

### 1. Search

```js
const results = await scriptorium.search({
  collection,
  query: question,
  top_k: 10,
  filter: { type: ["concept", "synthesis", "comparison"] }  // optional
});
```

Server uses PostgreSQL `ts_rank` (BM25-style) over `search_vector`. Returns `{path, title, snippet, score}[]`.

### 2. Read

- Pick top 3–5 candidates by score.
- `scriptorium.get_page({ collection, path })` for each.
- If no candidates above a relevance threshold, tell the user honestly: "wiki doesn't cover this yet — want me to ingest a source?"

### 3. Synthesise

- Compose a focused answer (2–6 paragraphs).
- **Cite inline**: every claim that comes from a wiki page gets `[path/to/page.md]` after it.
- If you bring in training-data knowledge, mark it clearly: `(not from the wiki)`.

### 4. Save-back offer

If the answer:
- Is a non-trivial synthesis across 2+ pages, OR
- Resolves a conflict between sources, OR
- Defines a new comparison the wiki doesn't yet have

→ propose: "This is a useful synthesis. Save as `synthesis/<slug>.md`? (y/N)"

If yes:
```js
await scriptorium.create_page({
  collection,
  path: `synthesis/${slug}.md`,
  content: answerBody,
  frontmatter: {
    title,
    type: "synthesis",
    sources: dedup(citedPaths.map(p => p.replace(/\.md$/, '').split('/').pop())),
    related: linkedPages,
    created: today,
    updated: today,
    confidence: "medium"
  }
});
```

### 5. Log

```js
scriptorium.append_log({
  collection,
  kind: "query",
  actor: "claude",
  payload: { question, pages_read: [...], saved_back: boolean }
});
```

## Failure modes

- Empty result set → don't fabricate. Tell the user.
- Conflicting pages → surface both, let the user decide which to trust.
- Stale info → if a page's `frontmatter.updated` is >180 days old, flag it in the answer.
