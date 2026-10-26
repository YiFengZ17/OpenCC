#!/usr/bin/env bash
# Dump the OpenCC PostgreSQL database to ./backups and keep the last N days.
# Cron example (03:17 daily):
#   17 3 * * * cd /opt/opencc-web/app/deploy && ./opencc-backup.sh >> backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p backups
chmod 700 backups
out="backups/opencc-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose --env-file .env.opencc -f compose.opencc.yml exec -T postgres \
  pg_dump -U opencc -d opencc --no-owner --clean --if-exists | gzip > "$out.tmp"
mv "$out.tmp" "$out"
chmod 600 "$out"
find backups -name 'opencc-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: $out ($(du -h "$out" | cut -f1))"
