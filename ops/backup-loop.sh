#!/usr/bin/env sh
set -eu

backup_dir="${BACKUP_DIR:-/backups}"
retention_days="${RETENTION_DAYS:-30}"
interval_seconds="${BACKUP_INTERVAL_SECONDS:-86400}"
mkdir -p "$backup_dir"

while true; do
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  output="$backup_dir/steel-compass-$timestamp.dump"
  temporary="$output.tmp"

  if pg_dump --format custom --file "$temporary"; then
    mv "$temporary" "$output"
    find "$backup_dir" -type f -name 'steel-compass-*.dump' \
      -mtime "+$retention_days" -delete
    printf '{"event":"database_backup","status":"ok","file":"%s"}\n' "$output"
  else
    rm -f "$temporary"
    printf '{"event":"database_backup","status":"failed"}\n' >&2
  fi

  sleep "$interval_seconds"
done
