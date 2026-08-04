#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  printf 'Usage: %s <backup.dump>\n' "$0" >&2
  exit 2
fi

backup_file="$1"
if [ ! -f "$backup_file" ]; then
  printf 'Backup not found: %s\n' "$backup_file" >&2
  exit 2
fi

printf 'Restore overwrites data in database %s. Type RESTORE to continue: ' "$POSTGRES_DB"
read -r confirmation
if [ "$confirmation" != "RESTORE" ]; then
  printf 'Cancelled.\n'
  exit 1
fi

docker compose exec -T postgres dropdb \
  --username "$POSTGRES_USER" \
  --if-exists "$POSTGRES_DB"
docker compose exec -T postgres createdb \
  --username "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T postgres pg_restore \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --clean \
  --if-exists < "$backup_file"

