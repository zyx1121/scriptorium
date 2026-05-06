# Security policy

## Reporting a vulnerability

If you find a security issue in scriptorium — auth bypass, token leakage, RCE in the server, prompt-injection holes in the plugin skill, anything that lets a low-scope token escalate or read another collection — please **do not open a public issue**.

Instead, email **loki@winlab.tw** with:

- A short description of the issue
- Steps to reproduce (curl / SQL / code snippet)
- Affected version (`/health` response is fine)
- Impact: who can exploit, what they can read or write

You'll get an acknowledgement within 72 hours. We aim to ship a fix within 14 days for high-severity issues; lower severity may take longer but won't be ignored.

## Threat model

What we **are** trying to defend against:

- A `r`-scope token reading collections it isn't scoped to.
- A `rw`-scope token editing collections it isn't scoped to, deleting pages, or forging audit-log entries (`page_read`, `search`, `init`, `schema_update`, `delete_page`) to cover its tracks or poison stats.
- A leaked dashboard token ending up in browser history, Referer headers, or a reverse-proxy access log on every navigation. (As of 0.5 the token is swapped for an `HttpOnly Secure SameSite=Strict` cookie on first visit; only the initial request is loggable.)
- A leaked `ADMIN_TOKEN` letting anyone with shell access mint admin-scope tokens. (As of 0.5 the env var is hashed at first migrate and verified with `timingSafeEqual`; setting `ADMIN_TOKEN=anything` no longer passes.)
- A leaked or rented Bearer token DoSing the server by spamming session inits. (Throttled separately from per-request bucket; idle sessions sweep every 5 min.)
- A drifting schema producing pages that look authentic but aren't validated. (`scriptorium.update_schema` writes a `schema_update` audit log; reviewers can spot unexpected drift.)

What we are **not** trying to defend against:

- An attacker with root on the host. At that point everything below the proxy is forfeit; rotate every secret per `disaster-recovery.md` and reseed.
- A compromised teammate's laptop. A live `SCRIPTORIUM_TOKEN` on a stolen device is as bad as a leaked password — revoke immediately and rely on `--expires-days N` to bound the blast radius.
- Prompt injection from raw sources Claude ingests. The skill discusses ingest with the user before writing pages; a malicious source can try to coerce Claude, but the human approval gate is the security boundary, not the wiki.
- Brute force against weak admin tokens. Use `openssl rand -hex 32`; we don't add CAPTCHAs.

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
- [ ] Issue per-user tokens with `--scope rw --collection <slug> --expires-days 90`. Reserve `admin` for ops.
- [ ] Terminate TLS at a reverse proxy (Caddy / nginx / Cloudflare Tunnel). The server speaks plain HTTP.
- [ ] Set `X-Forwarded-Proto: https` on the proxy so the dashboard cookie gets `Secure`.
- [ ] Restrict the server's network exposure (firewall to proxy only, VPN, or behind Cloudflare Access).
- [ ] Schedule `pg_dump` backups (`server/scripts/backup.sh`) with **off-host** storage. Restore-test monthly.
- [ ] Run `prune_logs(90)` weekly to bound log table growth.
- [ ] Rotate tokens at expiry, not "when convenient". `bun run cli token list` once a month.
- [ ] Keep `bun`, `postgres`, and image base versions current. (Dependabot handles the npm + Docker side.)

Full deployment + hardening guide: [`docs/deploy.md`](docs/deploy.md).

## Known limitations

- Tokens are **collection-scoped**, not page-scoped. A `rw` token on collection `foo` can edit any page in `foo`. If two pages need different read-sets, put them in different collections.
- No 2FA or session expiry by default. Set `--expires-days N` when issuing tokens, and put SSO at the proxy if you need MFA.
- The dashboard accepts `?token=…` for first-visit browser convenience; the server immediately swaps it for an `HttpOnly` cookie and redirects. The token still appears in the proxy access log for that one request — consider the dashboard a privileged admin tool, not a public link.

## Token rotation

See [`docs/operations.md`](docs/operations.md#rotation) for the full procedure. Headlines:

- **Member tokens**: `cli token revoke --id N` and re-issue. Member updates `SCRIPTORIUM_TOKEN` in shell env. No restart needed.
- **Admin token**: `DELETE FROM server_config WHERE key='admin_token_hash'`, update `.env`, re-run `bun run migrate`. The CLI verifies the env against the new hash on next call.
- **DB password**: `ALTER USER` + update `DATABASE_URL` + restart the server.

After any P0 / P1 incident, write a `type: incident` page in the wiki itself — `disaster-recovery.md` has the template.

## Disclosure

Once a fix is shipped, we'll credit reporters in `CHANGELOG.md` (with permission) and publish a brief advisory in `SECURITY-ADVISORIES.md` if the issue warranted a CVE.
