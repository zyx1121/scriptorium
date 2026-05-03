# Onboarding a teammate

How to add a new member to a Scriptorium wiki you already host.

## You (the operator)

### 1. Mint a token

Pick a scope:

| Scope | Allows | Use for |
|---|---|---|
| `r` | read pages, search, see schema | viewers |
| `rw` | everything `r` plus create/update/delete pages, upload raw, append logs | regular contributors |
| `admin` | everything `rw` plus create collections, update schema, on any collection | ops only |

Restrict by collection (optional but recommended):

```bash
ssh -tt root@<your-pve-host> "ssh user@<your-vm-ip> \
  'cd ~/scriptorium/server && docker compose exec -T server \
   bun src/cli/index.ts token issue \
   --name <teammate-handle> --scope rw --collection <wiki-slug>'"
```

Add `--expires-days 90` if you want auto-rotation.

The CLI prints the **raw token once**. Copy it now or it's gone.

### 2. Share the token securely

- ✅ Private DM in Slack/Signal/iMessage
- ✅ Password manager item shared with the teammate
- ❌ Public Slack channel
- ❌ Email (unencrypted)
- ❌ Git commit, GitHub issue, GitHub gist

### 3. Tell them the API URL

If TLS-fronted: `https://wiki.your-team.tld`.
If still on the bare port-forward: `http://<host>:<port>`.

## They (the teammate)

### 1. Set environment variables

In `~/.zshrc` (or `~/.bashrc` / `~/.config/fish/config.fish`):

```bash
export SCRIPTORIUM_API_URL=https://wiki.your-team.tld
export SCRIPTORIUM_TOKEN=<paste-the-token>
```

Then `source ~/.zshrc` or open a new terminal.

If they prefer per-project secrets, drop the same two lines into a project `.env` and use direnv or dotenv.

### 2. Install the plugin

```
/plugin marketplace add zyx1121/marketplace
/plugin install scriptorium@zyx1121
```

### 3. Verify

```
/scriptorium:status
```

Should print:

```
✓ Connected to https://wiki.your-team.tld
✓ Token: <name>, scopes: [rw], collections: [<slug>]
✓ Server health: ok (db_ok, version 0.2.0)
```

If anything fails, see [`Troubleshooting`](#troubleshooting).

### 4. Try a query

```
/scriptorium:query <some question that should be in the wiki>
```

Or just ask a relevant question without the slash command — the skill description encourages auto-search before training-data fall-through.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Streamable HTTP error: Server not initialized` | Plugin MCP session held a stale id after server restart | `/reload-plugins` |
| `401 unauthorized` on `/whoami` | Token wrong, expired, or revoked | Operator: check `bun run cli token list`. Issue a new token. |
| `403 forbidden` on a tool call | Token lacks scope or collection access | Operator: re-issue with broader `--collection` or `--scope` |
| `Connection refused` | Server down or wrong URL | Operator: `docker compose ps`, check VM port forward |
| Plugin install fails with `Permission denied (publickey)` | Either repo is private, or local SSH key isn't on GitHub | Repos are public — try `/plugin marketplace update zyx1121` and reinstall |

## Revoking access

When someone leaves:

```bash
docker compose exec -T server bun src/cli/index.ts token list
docker compose exec -T server bun src/cli/index.ts token revoke --id <token-id>
```

Revoked tokens fail auth on the next request — no restart needed.
