# Operating scriptorium

Day-to-day runbook for a deployed Scriptorium server. If you're setting up for the first time, see [`deploy.md`](deploy.md) first.

## Cadence at a glance

| Frequency | Task | Section |
|---|---|---|
| Daily   | Confirm last night's backup completed | [Backups](#backups) |
| Weekly  | Run `prune_logs(90)` | [Log retention](#log-retention) |
| Monthly | Review active tokens; revoke stale ones | [Tokens](#tokens) |
| Monthly | Restore-test latest backup | [Backups](#backups) |
| As needed | Server upgrade | [Upgrades](#upgrades) |
| As needed | Token / admin rotation | [Rotation](#rotation) |

## Backups

The backup script (`server/scripts/backup.sh`) writes `pg_dump -F c` archives to `${BACKUP_DIR:-/backups}` and rotates anything older than `${RETENTION_DAYS:-14}` days.

### Verify backups exist

```bash
ls -lh /var/backups/scriptorium/scriptorium-*.pgdump | tail -5
# expect: ~daily files, sizes within 10–20% of each other
```

If a file is missing for yesterday, **don't wait** — the script `exit 1`s on failure and writes nothing, so a missing date means the dump never ran. Check the cron log.

### Restore-test (do this monthly, not when production breaks)

```bash
# In an isolated container, NOT prod
docker run --rm -d --name pg-restore -e POSTGRES_PASSWORD=test -p 15432:5432 postgres:16
sleep 5
pg_restore --clean --no-owner -U postgres -d postgres -h localhost -p 15432 \
  < /var/backups/scriptorium/scriptorium-2026-05-04T04-17-00Z.pgdump
psql -U postgres -h localhost -p 15432 -c 'SELECT count(*) FROM pages;'
docker rm -f pg-restore
```

If `pg_restore` errors out you've been collecting useless files. Fix the dump command in `backup.sh` before relying on it again.

## Log retention

The `logs` table grows continuously. `prune_logs(retention_days)` deletes only `page_read` and `search` rows older than the threshold; `ingest`, `init`, `delete_page`, `schema_update` and other audit-bearing kinds are kept forever.

```bash
docker compose exec -T db psql -U scriptorium -d scriptorium \
  -c "SELECT prune_logs(90);"
```

Cron entry:

```cron
0 5 * * 0   docker compose exec -T db psql -U scriptorium -d scriptorium -c "SELECT prune_logs(90);" >> /var/log/scriptorium-prune.log 2>&1
```

Tune the retention if you have heavy `page_read` traffic — the log table is the dominant disk-grower in a busy wiki.

## Tokens

### List and revoke

```bash
docker compose exec -T server bun run cli token list
docker compose exec -T server bun run cli token revoke --id 7
```

A monthly review:

- Anyone who left the team → revoke their tokens.
- Devices nobody uses anymore (`alice-old-laptop`) → revoke.
- `expires_at` in the past but `revoked_at` null → already inactive but gunks up `token list`; revoke for cleanliness.

### Rotate a member token

```bash
# 1. Issue the new one and share via password manager
docker compose exec -T server bun run cli token issue \
  --name alice-mac-2 --user alice@your-team.tld \
  --scope rw --collection main-wiki --expires-days 90

# 2. Once Alice has updated her shell env and confirmed it works:
docker compose exec -T server bun run cli token revoke --id <old-id>
```

## Rotation

### Admin token

The CLI verifies `ADMIN_TOKEN` against a hash stored at first migrate. To rotate:

```bash
# 1. Pick a new token
NEW_ADMIN_TOKEN=$(openssl rand -hex 32)

# 2. Drop the old hash row
docker compose exec -T db psql -U scriptorium -d scriptorium \
  -c "DELETE FROM server_config WHERE key = 'admin_token_hash';"

# 3. Update .env
sed -i.bak "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$NEW_ADMIN_TOKEN/" /opt/scriptorium/server/.env
rm /opt/scriptorium/server/.env.bak

# 4. Re-seed the hash
docker compose exec -T server bun run migrate

# 5. Verify the CLI still works
docker compose exec -T server bun run cli token list
```

Stash the new value in your password manager before step 2 — losing it after step 2 means you have to drop the hash row by hand again, which works but is awkward if your DB is ever locked down.

### Token DB password

If `DATABASE_URL` was leaked: change the Postgres password (`ALTER USER scriptorium WITH PASSWORD '...'`), update `.env`, restart. No data loss; the server reconnects on next request.

## Upgrades

Scriptorium follows SemVer. Minor version bumps add migrations and may add MCP tools; major bumps may break wire compatibility.

```bash
cd /opt/scriptorium
git fetch --tags
git checkout v0.5.0     # or `main` if you live dangerously
docker compose up -d --build
docker compose exec -T server bun run migrate
```

Migrations are append-only and idempotent — running `migrate` is always safe. If a migration fails, the script `ROLLBACK`s the transaction and exits non-zero; the previous version of the server still works.

After upgrade, smoke-test:

```bash
curl -sS https://wiki.your-team.tld/health | jq
docker compose exec -T server bun run cli token list  # should still work
```

## Monitoring

Useful log lines and what they mean:

| Pattern | Severity | Action |
|---|---|---|
| `[scriptorium] received SIGTERM` | info | normal restart; check it came back |
| `[stats] page_read log failed` | warn | DB blip; if persistent, investigate `db_ok` |
| `verifyBearer` returns null repeatedly for the same hash | suspect | someone trying revoked / expired token; consider firewalling the source |
| `429` on `/mcp` | info | rate limit kicked; if from a known token, the user is hammering us |

Tail with `docker compose logs -f --tail=50 server`. Pipe to journald or Loki if you want long retention.

## Things that look like incidents but aren't

- **`429 rate limited` from a busy ingest** — token bucket caps `mcp:<token>` at 120 burst / 2 req/sec. Slow the ingest down or sharded across tokens; not a server problem.
- **Dashboard shows 0 reads/searches for the last 90 days** — `prune_logs` ran with a low retention. By design.
- **`migrations: skip 005 (already applied)`** — normal. Migrations are append-only and tracked in `migrations` table.
- **`admin_token_hash already set; ignoring ADMIN_TOKEN env`** — also normal after first migrate. To rotate, see [Rotation](#rotation).

For real incidents (token leak, DB lost, server compromise), see [`disaster-recovery.md`](disaster-recovery.md).
