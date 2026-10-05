#!/usr/bin/env sh
# Dump the Kontor database to a compressed file: scripts/backup.sh [target-dir]
# Needs pg_dump (postgresql-client) and KONTOR_DATABASE_URL, taken from the environment or .env.
# Restore: gunzip -c kontor-YYYYMMDD-HHMMSS.sql.gz | psql "<url without +psycopg>"
set -eu
url="${KONTOR_DATABASE_URL:-$(grep '^KONTOR_DATABASE_URL=' .env | cut -d= -f2-)}"
# pg_dump wants a plain libpq URL; and from the Docker host the Postgres is just localhost.
url=$(printf '%s' "$url" | sed -e 's/+psycopg//' -e 's/host.docker.internal/localhost/')
dir="${1:-./backups}"
mkdir -p "$dir"
file="$dir/kontor-$(date +%Y%m%d-%H%M%S).sql.gz"
pg_dump --clean --if-exists "$url" | gzip > "$file"
echo "Wrote $file"
