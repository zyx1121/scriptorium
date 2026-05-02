# `/scriptorium:connect` flow

## Purpose

Help the user wire a Scriptorium server into this Claude Code session. The plugin's `.mcp.json` reads two environment variables (`SCRIPTORIUM_API_URL`, `SCRIPTORIUM_TOKEN`); this command prints the steps to set them and verifies the result.

This command **does not persist secrets**. The user puts them in their shell profile or project `.env`. Tokens never live in the plugin or this repo.

## Steps

### 1. Try `whoami` first

If env vars are already set, `scriptorium.whoami()` will succeed:

```js
try {
  const me = await scriptorium.whoami();
  // print "✓ Connected as <token_name>, scopes: rw, collections: ..."
  // also call scriptorium.list_collections() and show them
  return;
} catch (e) {
  // not connected; proceed to step 2
}
```

### 2. Print setup instructions

Use the `$ARGUMENTS` URL if provided; otherwise show `https://wiki.your-team.tld` as placeholder.

```
To connect this Claude Code session to <url>:

1. Get a token from the wiki admin (or run this on the server yourself):

     bun run cli token issue \
       --name <your-name> \
       --scope rw \
       --collection <wiki-slug>

   Save the output — the raw token is only shown once.

2. Add these to your shell profile (~/.zshrc or ~/.bashrc):

     export SCRIPTORIUM_API_URL=<url>
     export SCRIPTORIUM_TOKEN=<paste-the-token>

   Or to a project-local `.env` if you use direnv / dotenv.

3. Reload your shell, then re-open Claude Code in this project.

4. Run `/scriptorium:connect` again to verify, or `/scriptorium:init <slug>`
   to create your first collection.
```

### 3. Don't ask the user for the token

Never prompt the user to paste the raw token in chat — that ends up in transcripts and logs. Always tell them to set it via the shell, where it stays in their environment alone.

## Failure modes

- **`whoami` returns 401** → token wrong/expired/revoked. Tell them to re-issue.
- **`whoami` returns 403** → token lacks scope for this wiki. Suggest a higher-scope token from admin.
- **`whoami` connection refused** → server down or wrong URL; suggest checking `SCRIPTORIUM_API_URL` and the server's `/health`.
- **No `scriptorium` MCP tools available at all** → `.mcp.json` env substitution failed (likely `SCRIPTORIUM_API_URL` unset). Show step-2 instructions.
