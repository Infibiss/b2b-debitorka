#!/usr/bin/env bash
# Installed timer invokes the current reviewed release. No domain is required.
set -euo pipefail
cd /opt/agentpay/current
compose=(docker compose --env-file /etc/agentpay/production.env -p agentpay -f compose.production.yml)
"${compose[@]}" run --rm --no-deps certbot renew --quiet
"${compose[@]}" exec -T proxy nginx -t
"${compose[@]}" exec -T proxy nginx -s reload
