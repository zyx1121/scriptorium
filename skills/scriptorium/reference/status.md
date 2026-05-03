# `/scriptorium:status` flow

## Purpose

Give the user a one-screen view of the current connection: where is the wiki, who am I to it, what collections do I see, is everything healthy.

This command is **read-only** and **safe to run any time** — useful as a smoke test after `connect`, after `/reload-plugins`, or when something feels off.

## Steps

### 1. Health

```js
const h = await scriptorium.health();
// { ok: true, db_ok: true, version: "0.2.0" }
```

If this fails (network error, 401), print setup instructions per `reference/connect.md` and stop.

### 2. Identity

```js
const me = await scriptorium.whoami();
// { token_name: "loki-mac", scopes: ["admin"], collections: "*" }
```

### 3. Collections

```js
const cols = await scriptorium.list_collections();
// [{ slug, name, schema_version }, ...]
```

Filter to those `me.collections` actually grants access to (server already does this; double-check for clarity).

### 4. Render

A compact panel like:

```
scriptorium · status
────────────────────────────────────────
✓ server  https://wiki.example.com   v0.2.0   db ok
✓ token   loki-mac                   scopes: rw, admin
✓ access  3 collections

  - propagation-model    schema v2    (32 pages)
  - team-knowledge       schema v1    (5 pages)
  - personal-research    schema v1    (0 pages)
```

Page counts are optional; fetch via `scriptorium.list_pages({ collection })` only if the user is on a fast link or really wants them. For quick status, just slug + schema_version is fine.

### 5. Suggest next step

After the panel, drop a one-line hint:
- If 0 collections → "Try `/scriptorium:init <slug>` to create one."
- If collections exist → "Try `/scriptorium:query <question>` or `/scriptorium:ingest <path>`."

## Anti-patterns

- ❌ Echoing the raw token in chat (it lands in transcripts and exports).
- ❌ Issuing extra MCP calls just to look thorough — three calls is enough.
- ❌ Failing silently when the server is down. Always print the actual error.
