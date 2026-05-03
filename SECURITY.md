# Security policy

## Reporting a vulnerability

If you find a security issue in scriptorium — auth bypass, token leakage, RCE in the server, prompt-injection holes in the plugin skill, anything that lets a low-scope token escalate or read another collection — please **do not open a public issue**.

Instead, email **loki@winlab.tw** with:

- A short description of the issue
- Steps to reproduce (curl / SQL / code snippet)
- Affected version (`/health` response is fine)
- Impact: who can exploit, what they can read or write

You'll get an acknowledgement within 72 hours. We aim to ship a fix within 14 days for high-severity issues; lower severity may take longer but won't be ignored.

## Scope

In scope:
- The plugin (`.claude-plugin/`, `skills/`, `commands/`, `hooks/`, `.mcp.json`)
- The server (`server/`)
- Authentication, authorization, token handling
- Schema validation bypass
- SQL injection in any MCP tool or HTTP handler
- Prompt-injection vectors in skill instructions or hook output

Out of scope:
- Third-party dependencies (file upstream)
- Misconfigured deployments (e.g. running without TLS, leaking `.env`)
- Brute-force attacks against weak admin tokens (use `openssl rand -hex 32`)

## Hardening checklist (operators)

When you self-host scriptorium for a team:

- [ ] Generate `ADMIN_TOKEN` with `openssl rand -hex 32`. Never reuse.
- [ ] Issue per-user tokens with `--scope rw --collection <slug>`. Reserve `admin` for ops.
- [ ] Terminate TLS at a reverse proxy (Caddy / nginx). The server speaks plain HTTP.
- [ ] Restrict the server's network exposure (PVE port forward, VPN, or behind Cloudflare Access).
- [ ] Schedule `pg_dump` backups (`server/scripts/backup.sh`) with off-host storage.
- [ ] Run `prune_logs(90)` periodically to bound log table growth.
- [ ] Keep `bun`, `postgres`, and image base versions current.

## Known limitations

- Tokens are **collection-scoped**, not page-scoped. A `rw` token on collection `foo` can edit any page in `foo`.
- No 2FA or session expiry by default. Set `--expires-days N` when issuing tokens.
- The dashboard accepts `?token=…` for browser convenience. This puts the token in browser history and may leak via Referer. Prefer `Authorization: Bearer …` for automation.

## Disclosure

Once a fix is shipped, we'll credit reporters in `CHANGELOG.md` (with permission) and publish a brief advisory in `SECURITY-ADVISORIES.md` if the issue warranted a CVE.
