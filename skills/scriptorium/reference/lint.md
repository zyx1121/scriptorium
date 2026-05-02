# `/scriptorium:lint` flow

## Purpose

Find rot in the wiki. The wiki gets sicker over time — lint is the immune system.

## What gets checked (server-side)

| Check | Severity | What it means |
|---|---|---|
| Dead wikilinks | error | `[[foo]]` resolves to nothing |
| Orphan pages | warning | No incoming wikilinks; either link in or delete |
| Missing concepts | warning | Term mentioned in 3+ pages but has no page |
| Stale claims | info | `frontmatter.updated` > 180d AND no recent ingest touched the topic |
| Schema violations | error | Missing required frontmatter, invalid type |
| Frontmatter drift | warning | Type-specific required fields missing |
| Confidence inflation | warning | `high` confidence but only one source cited |

## Steps

### 1. Run

```js
const report = await scriptorium.lint({ collection, scope: "all" });
// report = { errors: [...], warnings: [...], info: [...] }
```

### 2. Triage

- Group by check type.
- Sort by impact (errors > warnings > info, then by # pages affected).
- Show user the top 5 issues with concrete fix suggestions.

### 3. Fix loop

For each issue user approves:
- Dead wikilink → either fix the link target or remove the link (with reason).
- Orphan → propose a page that should link to it; if no good target, suggest archive.
- Missing concept → offer to create a stub page; user provides 2-line definition.
- Stale claim → re-check the source; either bump `updated` (no change needed) or flag for re-ingest.
- Schema violation → fix in place via `scriptorium.update_page()`.

### 4. Save report

```js
scriptorium.save_lint_report({
  collection,
  report,
  fixed: [...],    // paths fixed in this session
  deferred: [...]  // paths deferred for later
});
```

Server stores it in `outputs/reports/lint-<ISO_DATE>.md`.

### 5. Log

```js
scriptorium.append_log({
  collection,
  kind: "lint",
  actor: "claude",
  payload: { errors: N, warnings: N, fixed: N }
});
```

## Anti-patterns

- ❌ Auto-fixing without user approval.
- ❌ Marking stale claims as fresh just to silence the warning.
- ❌ Deleting orphan pages without checking git history — they may be in-progress.
