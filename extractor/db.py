"""
Database operations for the health data extraction service.

Uses psycopg2 with a simple connection pool (psycopg2.pool.ThreadedConnectionPool).
All queries are parameterised to prevent SQL injection.

Schema (Prometheus-inspired)
----------------------------
documents        — source lab reports (one row per PDF)
metrics          — measurement definitions (name, category, unit, scale)
reference_ranges — multi-dimensional thresholds (standard/optimal/critical × sex × age)
samples          — time-series lab result data

Public API
----------
get_connection()                        — acquire a connection from the pool
release_connection(conn)                — return a connection to the pool
init_db()                               — create schema from init.sql
insert_lab_results(results, source)     — bulk-insert into documents + samples
insert_events(events, source)           — bulk-insert MedicalEvent rows
log_processing(filename, status, error) — upsert a processing log row
is_processed(filename)                  — check if filename hash already exists
get_lab_results(...)                    — query samples with optional filters
seed_reference_ranges(ranges)           — upsert metrics + reference_ranges
check_flags_against_references(results) — cross-check LLM flags vs stored ranges
list_processed_files()                  — list processing log entries
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

import psycopg2  # type: ignore[import]
import psycopg2.extras  # type: ignore[import]
import psycopg2.pool  # type: ignore[import]

from .config import config
from .schema import LabResult, MedicalEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool (initialised lazily)
# ---------------------------------------------------------------------------

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # seconds


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return (or create) the module-level connection pool."""
    global _pool  # noqa: PLW0603
    if _pool is None or _pool.closed:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    host=config.db_host,
                    port=config.db_port,
                    dbname=config.db_name,
                    user=config.db_user,
                    password=config.db_password,
                )
                logger.info("Database connection pool established.")
                break
            except psycopg2.OperationalError as exc:
                logger.warning(
                    "DB connection failed (attempt %d/%d): %s",
                    attempt, _MAX_RETRIES, exc,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF * attempt)
                else:
                    raise
    return _pool  # type: ignore[return-value]


def get_connection() -> psycopg2.extensions.connection:
    """Acquire a connection from the pool."""
    return _get_pool().getconn()


def release_connection(conn: psycopg2.extensions.connection) -> None:
    """Return a connection to the pool."""
    _get_pool().putconn(conn)


# ---------------------------------------------------------------------------
# Context manager helper
# ---------------------------------------------------------------------------


class _ManagedConn:
    """Context manager that acquires/releases a pooled connection."""

    def __init__(self) -> None:
        self._conn: Optional[psycopg2.extensions.connection] = None

    def __enter__(self) -> psycopg2.extensions.connection:
        self._conn = get_connection()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        if self._conn:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
            release_connection(self._conn)
            self._conn = None


def _conn() -> _ManagedConn:
    return _ManagedConn()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_INIT_SQL_PATH = Path("/app/db/init.sql")


def init_db() -> None:
    """
    Execute the SQL initialisation script to create all tables.

    The script path is ``/app/db/init.sql`` (matches the Dockerfile COPY).
    Idempotent — uses IF NOT EXISTS internally.
    """
    if not _INIT_SQL_PATH.exists():
        logger.warning(
            "init.sql not found at '%s' — skipping schema init.",
            _INIT_SQL_PATH,
        )
        return

    sql = _INIT_SQL_PATH.read_text(encoding="utf-8")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("Database schema initialised from '%s'.", _INIT_SQL_PATH)


# ---------------------------------------------------------------------------
# Documents (find or create)
# ---------------------------------------------------------------------------


def _find_or_create_document(
    cur: psycopg2.extensions.cursor,
    filename: str,
    date,
) -> int:
    """
    Return the document ID for *filename*, creating a row if needed.

    Must be called inside an open transaction (cursor from a managed conn).
    """
    # Try INSERT first (common path for new files)
    cur.execute(
        """
        INSERT INTO documents (date, filename)
        VALUES (%s, %s)
        ON CONFLICT (filename) DO NOTHING
        RETURNING id
        """,
        (date, filename),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    # Already existed — fetch its id
    cur.execute(
        "SELECT id FROM documents WHERE filename = %s",
        (filename,),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Lab results → documents + metrics + samples
# ---------------------------------------------------------------------------


def insert_lab_results(
    results: list[LabResult],
    source_file: str,
) -> int:
    """
    Bulk-insert LabResult objects into documents + samples.

    Parameters
    ----------
    results     : Validated LabResult instances.
    source_file : Original PDF filename (stored for traceability).

    Returns
    -------
    int : Number of sample rows attempted (duplicates silently skipped).
    """
    if not results:
        return 0

    with _conn() as conn:
        with conn.cursor() as cur:
            # 1. Find or create the document
            earliest_date = min(r.date for r in results)
            doc_id = _find_or_create_document(cur, source_file, earliest_date)

            # 2. Ensure all metrics exist (upsert unknown measurements)
            unique_metrics = {
                (r.measurement, r.category, r.unit) for r in results
            }
            metric_rows = [
                (name, name, category, unit)
                for name, category, unit in unique_metrics
            ]
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO metrics (name, display_name, category, unit)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                metric_rows,
                page_size=200,
            )

            # 3. Insert samples
            sample_rows = [
                (
                    r.date,
                    r.measurement,
                    r.value,
                    r.value_text,
                    r.flag,
                    doc_id,
                )
                for r in results
            ]
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO samples (time, metric, value, value_text, flag, document_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (time, metric, document_id) DO NOTHING
                """,
                sample_rows,
                page_size=200,
            )

    logger.info(
        "Attempted %d sample insert(s) from '%s' (duplicates silently skipped).",
        len(results), source_file,
    )
    return len(results)


# ---------------------------------------------------------------------------
# Medical events (unchanged — same table)
# ---------------------------------------------------------------------------


def insert_events(
    events: list[MedicalEvent],
    source_file: str,
) -> int:
    """
    Bulk-insert MedicalEvent objects into the events table.

    Parameters
    ----------
    events      : Validated MedicalEvent instances.
    source_file : Original PDF filename.

    Returns
    -------
    int : Number of rows inserted.
    """
    if not events:
        return 0

    rows = [
        (
            e.date,
            e.end_date,
            e.category,
            e.subcategory,
            e.title,
            e.description,
            source_file,
        )
        for e in events
    ]

    sql = """
        INSERT INTO events
            (date, end_date, category, subcategory, title, description, source_file)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s)
    """

    with _conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=200)

    logger.info(
        "Inserted %d event(s) from '%s'.", len(events), source_file
    )
    return len(events)


# ---------------------------------------------------------------------------
# Processing log (unchanged — same table)
# ---------------------------------------------------------------------------


def _filename_hash(filename: str) -> str:
    """Return a stable SHA-256 hex digest of the bare filename."""
    return hashlib.sha256(filename.encode()).hexdigest()


def log_processing(
    filename: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    """
    Upsert a row in the processing_log table.

    Parameters
    ----------
    filename : str   — original PDF filename (path basename).
    status   : str   — "success", "failed", "skipped", etc.
    error    : str | None — error message if status is "failed".
    """
    file_hash = _filename_hash(filename)
    sql = """
        INSERT INTO pdf_processing_log (filename, file_hash, status, error_message)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (filename)
        DO UPDATE SET
            status        = EXCLUDED.status,
            error_message = EXCLUDED.error_message,
            processed_at  = NOW()
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (filename, file_hash, status, error))
    logger.debug("Processing log updated: %s → %s", filename, status)


def is_processed(filename: str) -> bool:
    """
    Return True if this filename has already been successfully processed.

    Checks by SHA-256 hash of the filename to handle path variations.
    """
    file_hash = _filename_hash(filename)
    sql = """
        SELECT 1
        FROM pdf_processing_log
        WHERE file_hash = %s AND status = 'success'
        LIMIT 1
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (file_hash,))
            return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Reference ranges seed → metrics + reference_ranges
# ---------------------------------------------------------------------------


def seed_reference_ranges(ranges: list[dict]) -> int:
    """
    Insert or update metric definitions and reference ranges.

    Parameters
    ----------
    ranges : list of dicts matching the reference_ranges.json schema.
             Expected keys: measurement, unit, reference_low, reference_high,
             scale, category.

    Returns
    -------
    int : Number of rows upserted.
    """
    if not ranges:
        return 0

    # 1. Upsert metrics
    metric_rows = [
        (
            r["measurement"],
            r["measurement"],
            r.get("category", "Other"),
            r.get("unit", ""),
            r.get("scale", "linear"),
        )
        for r in ranges
    ]
    metrics_sql = """
        INSERT INTO metrics (name, display_name, category, unit, scale)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (name)
        DO UPDATE SET
            unit     = EXCLUDED.unit,
            scale    = EXCLUDED.scale,
            category = EXCLUDED.category
    """

    # 2. Upsert reference ranges (standard, sex-unspecified)
    ref_rows = [
        (
            r["measurement"],
            "standard",
            r.get("reference_low"),
            r.get("reference_high"),
        )
        for r in ranges
        if r.get("reference_low") is not None or r.get("reference_high") is not None
    ]
    ref_sql = """
        INSERT INTO reference_ranges (metric, range_type, ref_low, ref_high)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (metric, range_type, COALESCE(sex, ''), COALESCE(age_min, -1), COALESCE(age_max, -1))
        DO UPDATE SET
            ref_low  = EXCLUDED.ref_low,
            ref_high = EXCLUDED.ref_high
    """

    with _conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, metrics_sql, metric_rows, page_size=200)
            psycopg2.extras.execute_batch(cur, ref_sql, ref_rows, page_size=200)

    logger.info(
        "Seeded %d metric(s) and %d reference range(s).",
        len(metric_rows), len(ref_rows),
    )
    return len(metric_rows)


# ---------------------------------------------------------------------------
# Query helper
# ---------------------------------------------------------------------------


def get_lab_results(
    measurement: Optional[str] = None,
    category: Optional[str] = None,
    start_date=None,
    end_date=None,
) -> list[dict]:
    """
    Query lab results with optional filters.

    All parameters are optional and ANDed together when provided.

    Parameters
    ----------
    measurement : str | None — exact metric name filter.
    category    : str | None — exact category filter.
    start_date  : date | str | None — inclusive lower bound.
    end_date    : date | str | None — inclusive upper bound.

    Returns
    -------
    list[dict] : Matching rows as plain dicts, newest first.
    """
    conditions: list[str] = []
    params: list = []

    if measurement:
        conditions.append("s.metric = %s")
        params.append(measurement)
    if category:
        conditions.append("m.category = %s")
        params.append(category)
    if start_date:
        conditions.append("s.time >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("s.time <= %s")
        params.append(end_date)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT d.id, s.time AS date, m.category, s.metric AS measurement,
               s.value, s.value_text, m.unit, s.flag,
               d.filename AS source_file
        FROM samples s
        JOIN metrics m ON s.metric = m.name
        JOIN documents d ON s.document_id = d.id
        {where_clause}
        ORDER BY s.time DESC, s.metric ASC
    """

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# List processed files (unchanged — same table)
# ---------------------------------------------------------------------------


def list_processed_files() -> list[dict]:
    """Return all rows from processing_log, newest first."""
    sql = """
        SELECT filename, status, error_message, processed_at
        FROM pdf_processing_log
        ORDER BY processed_at DESC
    """
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Flag cross-check
# ---------------------------------------------------------------------------


def check_flags_against_references(results: list) -> None:
    """
    Compare the LLM-extracted flag on each LabResult against the stored
    reference range and emit a WARNING for any disagreement.

    This does NOT modify or reject the results — they are stored as-is
    since the lab's own flag is authoritative. The warning exists to
    surface cases where the LLM misread a flag or OCR introduced noise.

    Parameters
    ----------
    results : list[LabResult]
        Validated LabResult objects, typically right before DB insertion.
    """
    if not results:
        return

    measurements = list({r.measurement for r in results})
    placeholders = ", ".join(["%s"] * len(measurements))
    sql = f"""
        SELECT metric AS measurement, ref_low AS reference_low, ref_high AS reference_high
        FROM reference_ranges
        WHERE metric IN ({placeholders})
          AND ref_low IS NOT NULL
          AND ref_high IS NOT NULL
          AND range_type = 'standard'
    """

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, measurements)
            ref_map: dict = {row["measurement"]: row for row in cur.fetchall()}

    # Surface measurements that have no stored reference range at all — helpful
    # when new tests appear in a report that haven't been seeded yet.
    no_ref = [m for m in measurements if m not in ref_map]
    if no_ref:
        logger.debug(
            "No reference range found for %d measurement(s); flag cross-check "
            "skipped for: %s",
            len(no_ref),
            ", ".join(sorted(no_ref)),
        )

    for r in results:
        if r.value is None:
            continue
        ref = ref_map.get(r.measurement)
        if ref is None:
            continue

        if r.value > ref["reference_high"]:
            expected = "H"
        elif r.value < ref["reference_low"]:
            expected = "L"
        else:
            expected = None

        if expected != r.flag:
            logger.warning(
                "Flag mismatch for %s (value=%.3g %s): "
                "LLM extracted flag=%r, reference range [%.3g–%.3g] suggests %r. "
                "Storing LLM flag as-is.",
                r.measurement,
                r.value,
                getattr(r, "unit", ""),
                r.flag,
                ref["reference_low"],
                ref["reference_high"],
                expected,
            )
