#!/usr/bin/env bash
# server/scripts/backup.sh
# Daily pg_dump → ${BACKUP_DIR:-/backups}, with 14-day rotation.
# Usage:
#   docker compose exec -T server bash /app/scripts/backup.sh
# Or run from host with docker compose exec mapped:
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

mkdir -p "$BACKUP_DIR"

# If invoked outside a container, exec into the db service.
if command -v pg_dump >/dev/null 2>&1; then
  pg_dump -U "$DB_USER" -F c -d "$DB_NAME" > "$OUT"
else
  docker compose exec -T db pg_dump -U "$DB_USER" -F c "$DB_NAME" > "$OUT"
fi

echo "[backup] wrote $OUT ($(du -h "$OUT" | awk '{print $1}'))"

# Rotate: drop dumps older than $RETENTION_DAYS days.
find "$BACKUP_DIR" -maxdepth 1 -name 'scriptorium-*.pgdump' -mtime "+$RETENTION_DAYS" -print -delete | sed 's/^/[backup] removed /'

echo "[backup] done. $(ls -1 "$BACKUP_DIR"/scriptorium-*.pgdump 2>/dev/null | wc -l | xargs) backups retained."
