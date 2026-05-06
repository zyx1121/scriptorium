# Deploying scriptorium

This is the production-hardening guide for running a Scriptorium server for a real team. The `Quick start` in `README.md` gets you a `localhost:8787` toy; this gets you `https://wiki.your-team.tld` with real tokens, real backups, and real boundaries.

If any step here feels optional, re-read it. Each one prevents an incident the project has already imagined.

## Threat model in one paragraph

Scriptorium stores a team's compiled brain in plaintext markdown plus YAML frontmatter, behind a bearer-token MCP server. The threats we care about: (a) someone reads a collection they shouldn't (token leak / scope bypass), (b) someone writes pages that look authentic but aren't (token theft / kind-forgery in audit logs), (c) the server is exposed to the open internet without TLS so tokens leak in transit, (d) backups don't actually exist when you need them. We are **not** trying to defend against a determined attacker who has root on your server — at that point, rotate everything and reseed.

## Pre-deploy checklist

- [ ] You own a TLS-capable hostname (`wiki.your-team.tld`).
- [ ] You have a place to run the server with persistent storage and an outbound network — one of: a small VM, a PVE container, Fly Machine, Render, etc.
- [ ] You can put a reverse proxy in front of it (Caddy / nginx / Cloudflare Tunnel). The Bun server speaks plain HTTP; **TLS terminates at the proxy**.
- [ ] You have a backup destination off the same host (S3 / B2 / another VM / a teammate's NAS).
- [ ] You generated `ADMIN_TOKEN` with `openssl rand -hex 32` and stored it somewhere only the ops account can read.

## Step 1 — provision the host

Anything Linux that can run Docker. Open ports `80` / `443` to the proxy, `22` to ops only, **everything else closed**. Do not expose port `8787` to the public internet — let the proxy reach it on `127.0.0.1` or a private bridge network.

## Step 2 — clone & configure

```bash
gh repo create your-team/your-wiki --template zyx1121/scriptorium --public --clone
cd your-wiki/server
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=postgres://scriptorium:<long-random-password>@db:5432/scriptorium
PORT=8787
PUBLIC_URL=https://wiki.your-team.tld
ADMIN_TOKEN=<openssl rand -hex 32>
LOG_LEVEL=info
```

Stash the `ADMIN_TOKEN` value out-of-band (1Password / Vault / encrypted file). After step 4 it's hashed in the DB and you'll never see it printed by the server again.

## Step 3 — bring up Postgres + server

```bash
docker compose up -d --build
docker compose exec -T server bun run migrate
```

The migrate script does two things on first run:
1. Apply every `NNN_*.sql` file in `server/src/db/migrations/`.
2. Hash `ADMIN_TOKEN` and store it in `server_config.admin_token_hash`. **From this point on the CLI verifies the env var against this hash** — `ADMIN_TOKEN=anything bun run cli` no longer works.

If the migrate output says `seeded admin_token_hash from ADMIN_TOKEN env`, you're good. If it says `admin_token_hash already set; ignoring ADMIN_TOKEN env`, something already seeded it — look at the OPERATIONS.md rotation flow.

## Step 4 — reverse proxy + TLS

### Caddy (recommended for one-host deployments)

```caddy
wiki.your-team.tld {
  encode zstd gzip
  reverse_proxy server:8787 {
    header_up X-Forwarded-Proto https
    header_up X-Forwarded-For {remote_host}
  }
}
```

`X-Forwarded-Proto: https` is **required** — without it the dashboard won't set `Secure` on the session cookie. Caddy adds it by default; make sure custom configs preserve it.

### nginx

```nginx
server {
  listen 443 ssl http2;
  server_name wiki.your-team.tld;
  ssl_certificate     /etc/letsencrypt/live/wiki.your-team.tld/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/wiki.your-team.tld/privkey.pem;

  location / {
    proxy_pass http://127.0.0.1:8787;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;

    # MCP streamable-HTTP needs long-lived connections
    proxy_buffering    off;
    proxy_read_timeout 300s;
  }
}
```

### Cloudflare Tunnel (no public IP needed)

```bash
cloudflared tunnel create scriptorium
cloudflared tunnel route dns scriptorium wiki.your-team.tld
# Then point the tunnel ingress at http://server:8787
```

In `~/.cloudflared/config.yml`:

```yaml
ingress:
  - hostname: wiki.your-team.tld
    service: http://server:8787
    originRequest:
      noTLSVerify: false
      httpHostHeader: wiki.your-team.tld
  - service: http_status:404
```

Cloudflare adds `X-Forwarded-Proto: https` automatically; optional **Cloudflare Access** policy in front gives you SSO before the server even sees the request.

## Step 5 — smoke test

From your laptop, not the server:

```bash
curl -sS https://wiki.your-team.tld/health | jq
# { "ok": true, "db_ok": true, "version": "0.5.0" }
```

If `db_ok: false`, the server can't reach Postgres — check the docker network and `DATABASE_URL`.

## Step 6 — issue tokens for real humans

```bash
docker compose exec -T server bun run cli user create \
  --email alice@your-team.tld --name "Alice" --role member

docker compose exec -T server bun run cli token issue \
  --name alice-mac --user alice@your-team.tld \
  --scope rw --collection main-wiki --expires-days 90
```

Save the printed raw token to your team's password manager and share via 1Password / Bitwarden share — **never paste in Slack or commit to a repo**.

Reserve `--scope admin` for the ops user. Members get `rw` on the collections they need; visiting researchers get `r` only.

## Step 7 — back-up automation

Pick a backup destination:

```bash
# Cron entry on the host (every day at 04:17 UTC):
17 4 * * * cd /opt/scriptorium && BACKUP_DIR=/var/backups/scriptorium docker compose exec -T server bash /app/scripts/backup.sh && rsync -a /var/backups/scriptorium/ ops@nas:/backups/scriptorium/
```

The backup script writes to a tempfile, verifies size > 0, then `mv`s to the final name. If the dump fails, no `.pgdump` appears — your alerting on missing files works.

## Hardening checklist

- [ ] TLS at the edge. `https://`, not `http://`.
- [ ] `ADMIN_TOKEN` generated with `openssl rand -hex 32`, stored only in the password manager and `.env` on the host.
- [ ] `.env` not committed (`.gitignore` already has it; double-check).
- [ ] Public exposure restricted to `:443` via the proxy. Not `:8787` directly.
- [ ] Per-user tokens with `--expires-days N` (90 is a reasonable default).
- [ ] Backups go off-host. A backup that lives on the same server is a disk failure away from being useless.
- [ ] `docker compose logs -f server` reviewed after first deploy to confirm no error spam.
- [ ] `prune_logs(90)` scheduled weekly (see OPERATIONS.md).

## What's intentionally not here

- **2FA**. Bearer tokens with a 90-day TTL hit the same access pattern; if your team needs MFA, put SSO at the proxy (Cloudflare Access, Tailscale serve, or oauth2-proxy) and treat scriptorium tokens as a second factor.
- **Per-page ACL**. Tokens are collection-scoped, full stop. If two pages need different read sets, put them in different collections.
- **High availability**. Single server + Postgres. If your team needs HA, the migration story is `pg_dump + restore on a hot standby`; we'll formalise it when someone actually needs it.

## Getting help

- Server won't start → `docker compose logs server` (most issues are `DATABASE_URL` typos or the migrate step skipped).
- Plugin can't reach the server → check `SCRIPTORIUM_API_URL` is `https://wiki.your-team.tld` (no trailing slash, no `/mcp` suffix — `.mcp.json` adds it).
- Token rejected → `bun run cli token list` to see if it's revoked / expired.
- Anything else → `loki@winlab.tw` (security: see SECURITY.md).
