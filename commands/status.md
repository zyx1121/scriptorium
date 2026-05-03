---
description: "Show current Scriptorium connection: server URL, token identity, accessible collections, and health. Use when the user asks 'am I connected?', 'which wiki?', 'check status'."
---

Load the `scriptorium` skill and follow the **status** flow in `reference/status.md`.

Step through these MCP calls in order and print a one-screen summary:
1. `scriptorium.health()` — server up + db reachable + version
2. `scriptorium.whoami()` — token name, scopes, collections this token can see
3. `scriptorium.list_collections()` — slugs + names + schema versions

Format the output as a short status panel (✓ / ✗ per check). Mention `SCRIPTORIUM_API_URL` if useful, but never echo the raw token.
