#!/usr/bin/env bash
# server/scripts/backup.sh
# Daily pg_dump → ${BACKUP_DIR:-/backups}, with 14-day rotation.
# Usage:
#   docker compose exec -T server bash /app/scripts/backup.sh
# Or run from host (will exec into the `db` service if local pg_dump is missing):
#   bash server/scripts/backup.sh
# Cron-friendly (set BACKUP_DIR + cd into compose project, or wrap in a
# systemd timer / cron entry on the host).

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_USER="${POSTGRES_USER:-scriptorium}"
DB_NAME="${POSTGRES_DB:-scriptorium}"
DATE="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
OUT="$BACKUP_DIR/scriptorium-$DATE.pgdump"
TMP="$OUT.partial"

mkdir -p "$BACKUP_DIR"

cleanup() { rm -f "$TMP"; }
trap cleanup EXIT

# Pick the dump strategy explicitly. If neither pg_dump nor docker is
# available, fail loudly — never silently leave a 0-byte file behind for
# rotation to delete in 14 days.
if command -v pg_dump >/dev/null 2>&1; then
  pg_dump -U "$DB_USER" -F c -d "$DB_NAME" > "$TMP"
elif command -v docker >/dev/null 2>&1; then
  docker compose exec -T db pg_dump -U "$DB_USER" -F c "$DB_NAME" > "$TMP"
else
  echo "[backup] error: neither pg_dump nor docker is available on this host" >&2
  exit 1
fi

if [ ! -s "$TMP" ]; then
  echo "[backup] error: dump produced an empty file — aborting (no rotation)" >&2
  exit 1
fi

mv "$TMP" "$OUT"
echo "[backup] wrote $OUT ($(du -h "$OUT" | awk '{print $1}'))"

# Rotate: drop dumps older than $RETENTION_DAYS days. Only `.pgdump`, never
# `.partial` — those are aborted runs and get cleaned up on EXIT.
find "$BACKUP_DIR" -maxdepth 1 -name 'scriptorium-*.pgdump' -mtime "+$RETENTION_DAYS" -print -delete | sed 's/^/[backup] removed /'

echo "[backup] done. $(ls -1 "$BACKUP_DIR"/scriptorium-*.pgdump 2>/dev/null | wc -l | xargs) backups retained."
