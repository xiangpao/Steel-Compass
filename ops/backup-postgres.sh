#!/usr/bin/env sh
set -eu

backup_dir="${1:-./backups}"
mkdir -p "$backup_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="$backup_dir/steel-compass-$timestamp.dump"

docker compose exec -T postgres pg_dump \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --format custom > "$output"

find "$backup_dir" -type f -name 'steel-compass-*.dump' -mtime +30 -delete
printf '%s\n' "$output"

