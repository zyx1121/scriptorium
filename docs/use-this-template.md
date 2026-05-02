# Use this template

This repo is a GitHub Template. One template → many wiki instances. Each wiki = one fresh repo + one server + one set of bearer tokens for the team.

## 1. Create your wiki repo

On GitHub, click **Use this template** → **Create a new repository**. Pick a name like `<your-team>-wiki` or `<topic>-wiki`. Private or public — your call.

```bash
gh repo clone <you>/<your-wiki>
cd <your-wiki>
```

## 2. (Optional) Rebrand the plugin

If you want the plugin's slash commands to be `/your-wiki:ingest` instead of `/scriptorium:ingest`:

1. Edit `.claude-plugin/plugin.json` → set `"name": "your-wiki"`.
2. Edit `.claude-plugin/marketplace.json` → set `"name": "your-wiki"` and the inner plugin `"name"`.
3. (Optional) Rename the skill folder `skills/scriptorium/` → `skills/your-wiki/`.

If you keep the default `scriptorium` name, slash commands stay `/scriptorium:*`. Either is fine.

## 3. Deploy the server

```bash
cd server
cp .env.example .env
# edit .env:
#   ADMIN_TOKEN: openssl rand -base64 32
#   PUBLIC_URL:  https://wiki.your-team.tld
docker compose up -d --build
```

Migrations run automatically on container start. Check:

```bash
curl http://localhost:8787/health
# {"ok":true,"db_ok":true,"version":"0.1.0"}
```

### Put it on the public internet

Pick one:

- **Caddy** (recommended for self-host): `wiki.your-team.tld { reverse_proxy localhost:8787 }` — auto TLS via Let's Encrypt.
- **Cloudflare Tunnel**: zero-config public hostname, no port-forwarding required. Works great on a PVE LXC.
- **fly.io / Railway**: tweak the Dockerfile or use the docker-compose service directly.

The server itself speaks plain HTTP. TLS terminates at your reverse proxy.

## 4. Create a collection

```bash
# inside the server container
docker compose exec server bun src/cli/index.ts token issue \
  --name admin --scope admin

# copy the printed token, then export it locally:
export SCRIPTORIUM_API_URL=https://wiki.your-team.tld
export SCRIPTORIUM_TOKEN=<paste>

# in any Claude Code session (after installing the plugin):
/scriptorium:init my-research
```

`init` calls `create_collection` server-side, which seeds `index.md` and the schema doc.

## 5. Onboard a teammate

Mint them a token:

```bash
docker compose exec server bun src/cli/index.ts token issue \
  --name <their-name> --scope rw --collection my-research
```

Send them:
- The wiki URL (`SCRIPTORIUM_API_URL`)
- Their token (one-time view; don't paste in Slack)
- The plugin install command:

```bash
# (they run this)
claude plugin install <you>/<your-wiki>
# then add to their shell profile:
export SCRIPTORIUM_API_URL=https://wiki.your-team.tld
export SCRIPTORIUM_TOKEN=<their-token>
# verify:
/scriptorium:connect
```

## 6. Day-to-day

```bash
/scriptorium:ingest ~/papers/karpathy-llm-wiki.md
/scriptorium:query "what's the difference between LLM Wiki and RAG?"
/scriptorium:lint
/scriptorium:recap
```

## Multiple wikis from the same Claude Code

Each wiki has its own template-fork repo, plugin name, and `SCRIPTORIUM_API_URL`. Because plugin slash commands are namespaced (`/your-wiki:*` vs `/scriptorium:*`), multiple wiki plugins can coexist. Just set the appropriate env vars per project (use direnv / dotenv) and they won't clash.

## Updating from upstream

This repo is a Template, not a fork — there's no upstream tracking by default. To pull improvements from `zyx1121/scriptorium`:

```bash
git remote add upstream https://github.com/zyx1121/scriptorium.git
git fetch upstream
git merge upstream/main   # resolve conflicts in your local customisations
```

Take what's useful, ignore what isn't.

## Backups

The source of truth is the **database**, not git. Schedule `pg_dump`:

```bash
docker compose exec db pg_dump -U scriptorium -F c scriptorium > backup-$(date +%F).pgdump
```

Restore with `pg_restore`. Tokens are sha256-hashed; if you lose the DB, you re-issue.
