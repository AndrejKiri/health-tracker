#!/usr/bin/env bash
# backup.sh — dump the health_tracker PostgreSQL database to a timestamped file.
#
# Usage:
#   ./scripts/backup.sh [--keep N] [output_dir]
#
#   --keep N      Keep the N most-recent backups in output_dir and delete the
#                 rest.  Defaults to 7.  Pass 0 to disable rotation entirely.
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
# Example cron entry (daily at 02:00, keep 14 backups):
#   0 2 * * * /path/to/health-tracker/scripts/backup.sh --keep 14 >> /var/log/health-backup.log 2>&1
#
# Dependencies:
#   - Docker Compose v2 (docker compose)
#   - The postgres service must be running

set -euo pipefail

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
KEEP=7          # number of recent backups to retain (0 = no rotation)
OUTPUT_DIR=""   # set below after argument parsing

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep)
            KEEP="$2"
            shift 2
            ;;
        --keep=*)
            KEEP="${1#--keep=}"
            shift
            ;;
        -*)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
        *)
            OUTPUT_DIR="$1"
            shift
            ;;
    esac
done

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
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/backups}"
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

# ---------------------------------------------------------------------------
# Rotate old backups
# ---------------------------------------------------------------------------
if [[ "${KEEP}" -gt 0 ]]; then
    # List backups matching our naming pattern, oldest first
    mapfile -t ALL_BACKUPS < <(
        ls -1t "${OUTPUT_DIR}"/health_tracker_*.sql 2>/dev/null || true
    )
    TOTAL="${#ALL_BACKUPS[@]}"
    if [[ "${TOTAL}" -gt "${KEEP}" ]]; then
        DELETE_COUNT=$(( TOTAL - KEEP ))
        # The oldest files are at the end of the ls -1t (newest-first) list
        for (( i=KEEP; i<TOTAL; i++ )); do
            echo "Removing old backup: ${ALL_BACKUPS[$i]}"
            rm -f "${ALL_BACKUPS[$i]}"
        done
        echo "Removed ${DELETE_COUNT} old backup(s); kept ${KEEP}."
    fi
fi
