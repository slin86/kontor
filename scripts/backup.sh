#!/usr/bin/env sh
# Dump the Kontor database to a compressed file: scripts/backup.sh [target-dir]
# Restore: gunzip -c kontor-YYYYMMDD-HHMMSS.sql.gz | docker compose exec -T db psql -U kontor kontor
set -eu
dir="${1:-./backups}"
mkdir -p "$dir"
file="$dir/kontor-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U kontor --clean --if-exists kontor | gzip > "$file"
echo "Wrote $file"
