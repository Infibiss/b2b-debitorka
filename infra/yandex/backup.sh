#!/usr/bin/env bash
# A private consistent pg_dump; safe to invoke manually or by the daily timer.
set -euo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
compose=(docker compose --env-file /etc/agentpay/production.env -p agentpay -f compose.production.yml)
folder=/var/backups/agentpay
mkdir -p "$folder"
chmod 700 "$folder"
exec 9>"$folder/.backup.lock"
flock -w 30 9
stamp=$(date -u +%Y%m%dT%H%M%SZ)
partial="$folder/.agentpay-$stamp-$$.partial"
archive="$folder/agentpay-$stamp-$$.dump"
trap 'rm -f "$partial"' EXIT
"${compose[@]}" exec -T app-db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$partial"
test -s "$partial"
"${compose[@]}" exec -T app-db pg_restore --list < "$partial" >/dev/null
mv "$partial" "$archive"
# Only this application's dated local dumps are rotated, after a verified new one.
find "$folder" -maxdepth 1 -type f -name 'agentpay-*.dump' -mtime +14 -delete
echo 'Private PostgreSQL archive created and its table of contents verified.'
