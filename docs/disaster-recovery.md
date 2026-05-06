# Disaster recovery

When something has actually gone wrong. Each scenario below is a runbook you can execute under stress without re-deriving the steps.

If you're reading this for the first time and not because something is currently on fire — good. Skim it now, bookmark it, restore-test the backups (`operations.md`), and come back when you need it.

## Severity guide

| Tag | Examples | Time to act |
|---|---|---|
| **P0** | DB lost, server compromised, admin token leaked | Now |
| **P1** | A member token leaked, a collection has visible bad data | Within hours |
| **P2** | A page is wrong, a backup is missing | Same business day |

## P0 · Database lost

Scenario: the Postgres volume is gone (disk failure, accidental `docker compose down -v`, container snapshot rolled back).

```bash
# 1. Bring up a fresh empty Postgres
docker compose up -d db
sleep 5

# 2. Restore the latest verified backup
LATEST=$(ls -1t /var/backups/scriptorium/scriptorium-*.pgdump | head -1)
docker compose exec -T db pg_restore --clean --create --no-owner -U scriptorium -d postgres < "$LATEST"

# 3. Re-run migrate (idempotent)
docker compose exec -T server bun run migrate

# 4. Smoke test
curl -sS https://wiki.your-team.tld/health | jq

# 5. Tell the team how much data was lost
#    (= time between $LATEST timestamp and now)
```

If the latest backup is more than 24 hours old, the rotation policy or the cron is broken — fix that before the next incident.

If you have **no** usable backup: the wiki is gone. The plugin half is git-tracked; the data half isn't. This is why `operations.md` says restore-test monthly.

## P0 · Server compromise

Scenario: someone got shell on the host, or admin credentials leaked beyond the ops circle.

Immediate (in this order):

1. **Cut external access.** Stop the proxy: `docker stop caddy` / `systemctl stop nginx` / disable the Cloudflare Tunnel route. Site goes 502 — that's correct.

2. **Rotate admin token.**
   ```bash
   docker compose exec -T db psql -U scriptorium -d scriptorium \
     -c "DELETE FROM server_config WHERE key = 'admin_token_hash';"
   NEW_ADMIN=$(openssl rand -hex 32)
   sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$NEW_ADMIN/" /opt/scriptorium/server/.env
   docker compose restart server
   docker compose exec -T server bun run migrate
   ```

3. **Revoke every active token.** Best done in SQL — the CLI does one at a time:
   ```bash
   docker compose exec -T db psql -U scriptorium -d scriptorium \
     -c "UPDATE tokens SET revoked_at = now() WHERE revoked_at IS NULL;"
   ```

4. **Audit the logs table** — what did the attacker do?
   ```bash
   docker compose exec -T db psql -U scriptorium -d scriptorium <<'SQL'
   SELECT ts, kind, actor, payload
   FROM logs
   WHERE ts > now() - interval '7 days'
     AND kind IN ('schema_update','delete_page','init')
   ORDER BY ts DESC LIMIT 100;
   SQL
   ```
   `schema_update` is the highest-leverage write — an attacker could broaden a schema to inject auth-relevant fields. Compare against `git log` of `server/templates/SCHEMA.md.tpl` to see if anything drifted.

5. **Rotate DB password.**
   ```bash
   docker compose exec -T db psql -U postgres \
     -c "ALTER USER scriptorium WITH PASSWORD '$(openssl rand -base64 32)';"
   # then update DATABASE_URL in .env, restart server
   ```

6. **Issue fresh tokens** for real humans, share via password manager. Tell the team to update their `SCRIPTORIUM_TOKEN` env.

7. **Bring the proxy back up.** Verify `/health` still answers, plugin reconnects with the new token.

8. **Post-mortem**. Save it as an `incident` page in the wiki itself. (`type: incident`, `severity: P0`, `detected_at`, `resolved_at`, `root_cause`, `lessons`.)

## P0 · Admin token leaked (but server otherwise clean)

If you only suspect the admin token (e.g. it ended up in a screen recording), this is faster than full compromise:

```bash
# Same as steps 2 + 5 above. Member tokens stay valid.
docker compose exec -T db psql -U scriptorium -d scriptorium \
  -c "DELETE FROM server_config WHERE key = 'admin_token_hash';"
sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$(openssl rand -hex 32)/" /opt/scriptorium/server/.env
docker compose exec -T server bun run migrate
```

## P1 · Member token leaked

```bash
docker compose exec -T server bun run cli token list
# find the leaked token's id by name (e.g. alice-mac, id=12)
docker compose exec -T server bun run cli token revoke --id 12
docker compose exec -T server bun run cli token issue \
  --name alice-mac-rotated --user alice@your-team.tld \
  --scope rw --collection main-wiki --expires-days 90
```

Audit what that token did:

```sql
SELECT ts, kind, payload
FROM logs
WHERE actor = 'alice-mac' AND ts > now() - interval '7 days'
ORDER BY ts DESC LIMIT 50;
```

If `kind` includes `delete_page` or `schema_update` you didn't expect, treat as P0 of section above (the leaker was active, not just possessing the token).

## P1 · Collection has visible bad data (vandalism, bad ingest)

Pages are versioned. To roll a single page back:

```sql
-- Find the prior version
SELECT version, created_at, author
FROM page_versions
WHERE page_id = (SELECT id FROM pages WHERE collection_id =
                 (SELECT id FROM collections WHERE slug = 'main-wiki')
                 AND path = 'concepts/foo.md')
ORDER BY version DESC LIMIT 5;

-- Restore version N (replace 7 with the chosen version)
WITH v AS (
  SELECT content, frontmatter
  FROM page_versions
  WHERE page_id = (SELECT id FROM pages WHERE collection_id =
                   (SELECT id FROM collections WHERE slug = 'main-wiki')
                   AND path = 'concepts/foo.md')
    AND version = 7
)
UPDATE pages
   SET content = v.content,
       frontmatter = v.frontmatter,
       version = version + 1,
       updated_at = now()
  FROM v
 WHERE pages.path = 'concepts/foo.md'
   AND pages.collection_id = (SELECT id FROM collections WHERE slug = 'main-wiki');
```

Bumping `version` is important — it keeps CAS clients on the right path. Don't `UPDATE pages SET version = 7`; the new write _is_ a new version, just one whose content matches an old one.

For a whole collection rollback, restore from `pg_dump` filtered to that collection — too risky to script generically; pair with a teammate.

## P1 · Schema corruption

Someone ran `update_schema` and broke it:

```bash
# Look at the audit log — what changed and when
docker compose exec -T db psql -U scriptorium -d scriptorium <<'SQL'
SELECT ts, actor, payload
FROM logs
WHERE collection_id = (SELECT id FROM collections WHERE slug = 'main-wiki')
  AND kind = 'schema_update'
ORDER BY ts DESC LIMIT 10;
SQL
```

If you have the previous `schema_md` text (in your terminal scrollback, in a `git log` of templates, in a backup), `scriptorium.update_schema({collection, schema_md: <previous>})` rolls forward — it bumps the version, doesn't decrement.

If you don't, restore the `collections` table from backup:

```sql
-- only the schema_md column for one collection
WITH old AS (
  -- hand-paste the dump's value
  SELECT '<previous SCHEMA.md content>'::text AS schema_md
)
UPDATE collections
   SET schema_md = old.schema_md,
       schema_version = schema_version + 1,
       updated_at = now()
  FROM old
 WHERE slug = 'main-wiki';
```

## P2 · Wrong page content

Use `update_page` via the plugin — it's CAS-safe and your normal workflow.

```
/scriptorium:query "what's the current state of <topic>"   # find it
# Read, edit, then via Claude:
# scriptorium.update_page({collection, path, content, frontmatter, base_version})
```

If you want history, Postgres has it:

```sql
SELECT version, created_at, author FROM page_versions
WHERE page_id = (SELECT id FROM pages WHERE path = '...');
```

## P2 · Backup missing

Cron probably didn't run, or `backup.sh` exited non-zero (missing `pg_dump`, no docker, disk full). Check:

```bash
tail -50 /var/log/scriptorium-backup.log    # whatever your cron redirects to
df -h /var/backups                          # disk full?
```

Fix the cause, then run a one-off backup:

```bash
docker compose exec -T server bash /app/scripts/backup.sh
```

## After any P0 / P1

Write an `incident` page in the wiki itself:

```yaml
type: incident
status: resolved
severity: P0
detected_at: 2026-05-06T03:14:00Z
resolved_at: 2026-05-06T05:42:00Z
timeline:
  - "03:14 — observed X"
  - "03:30 — root caused Y"
  - "05:42 — verified recovery"
root_cause: "..."
lessons:
  - "..."
related_decisions: ["[[decisions/rotate-admin-token-monthly]]"]
```

The wiki is supposed to compound. Incidents are the cheapest learning material it'll ever get; don't waste them.
