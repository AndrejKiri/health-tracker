#!/usr/bin/env bash
# Starts native Homebrew Grafana with the project provisioning directory.
# Reads credentials from .env in the project root and passes them as env
# vars so datasource.yml can interpolate ${POSTGRES_HOST} etc.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo "ERROR: .env not found at $PROJECT_DIR/.env — copy .env.example and fill in passwords." >&2
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$PROJECT_DIR/.env"
set +a

export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"

exec grafana server \
    --config /opt/homebrew/etc/grafana/grafana.ini \
    --homepath /opt/homebrew/share/grafana \
    cfg:paths.provisioning="$PROJECT_DIR/grafana/provisioning" \
    cfg:paths.logs=/tmp/grafana-logs \
    cfg:server.http_port=3001
