---
description: "Print setup instructions to connect this Claude Code session to a Scriptorium server. Shows token-issuance command + env vars to export."
argument-hint: "[<https://wiki.example.com>]"
---

Load the `scriptorium` skill and follow the **connect** flow in `reference/connect.md`. Optional URL: `$ARGUMENTS`

First try `scriptorium.whoami()` — if it succeeds, just confirm "already connected" and list accessible collections. Otherwise print the setup instructions for the provided URL (or a placeholder if none).

**Never ask the user to paste a token in chat.** Always direct them to set `SCRIPTORIUM_TOKEN` in their shell environment.
