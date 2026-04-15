#!/usr/bin/env bash
# backup.sh — dump the health_tracker PostgreSQL database to a timestamped file.
#
# Usage:
#   ./scripts/backup.sh [output_dir]
#
# If output_dir is omitted, backups are written to ./backups/ relative to the
# project root.  The script must be run from the project root directory where
# docker-compose.yml lives.
#
# The dump is a plain-text pg_dump (--format=plain) so it can be inspected,
# diffed, or restored with a simple `psql … < file.sql`.
#
# Example restore:
#   docker compose exec -T postgres psql \
#       -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
#       < backups/health_tracker_2024-01-15T12-00-00.sql
#
# Dependencies:
#   - Docker Compose v2 (docker compose)
#   - The postgres service must be running

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve project root (directory containing this script's parent)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Load .env for DB credentials (if present)
# ---------------------------------------------------------------------------
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    # Export only the variables we need; avoid clobbering shell environment
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

# Defaults matching .env.example
POSTGRES_USER="${POSTGRES_USER:-health}"
POSTGRES_DB="${POSTGRES_DB:-health_tracker}"

# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
OUTPUT_DIR="${1:-${PROJECT_ROOT}/backups}"
mkdir -p "${OUTPUT_DIR}"

TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M-%S)"
OUTPUT_FILE="${OUTPUT_DIR}/health_tracker_${TIMESTAMP}.sql"

# ---------------------------------------------------------------------------
# Run pg_dump inside the running postgres container
# ---------------------------------------------------------------------------
echo "Backing up database '${POSTGRES_DB}' to '${OUTPUT_FILE}'…"

docker compose -f "${PROJECT_ROOT}/docker-compose.yml" exec -T postgres \
    pg_dump \
        --username="${POSTGRES_USER}" \
        --dbname="${POSTGRES_DB}" \
        --format=plain \
        --no-owner \
        --no-acl \
    > "${OUTPUT_FILE}"

SIZE="$(du -sh "${OUTPUT_FILE}" | cut -f1)"
echo "Backup complete: ${OUTPUT_FILE} (${SIZE})"
