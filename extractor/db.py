"""
Database operations for the health data extraction service.

Uses psycopg2 with a simple connection pool (psycopg2.pool.ThreadedConnectionPool).
All queries are parameterised to prevent SQL injection.

Public API
----------
get_connection()                        — acquire a connection from the pool
release_connection(conn)                — return a connection to the pool
init_db()                               — create schema from init.sql
insert_lab_results(results, source)     — bulk-insert LabResult rows
insert_events(events, source)           — bulk-insert MedicalEvent rows
log_processing(filename, status, error) — upsert a processing log row
is_processed(filename)                  — check if filename hash already exists
get_lab_results(...)                    — query lab_results with optional filters
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
                    dsn=config.db_dsn,
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
# Lab results
# ---------------------------------------------------------------------------


def insert_lab_results(
    results: list[LabResult],
    source_file: str,
) -> int:
    """
    Bulk-insert LabResult objects into the lab_results table.

    Parameters
    ----------
    results     : Validated LabResult instances.
    source_file : Original PDF filename (stored for traceability).

    Returns
    -------
    int : Number of rows inserted.
    """
    if not results:
        return 0

    rows = [
        (
            r.date,
            r.category,
            r.measurement,
            r.value,
            r.value_text,
            r.unit,
            r.flag,
            source_file,
        )
        for r in results
    ]

    sql = """
        INSERT INTO lab_results
            (date, category, measurement, value, value_text, unit, flag, source_file)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, measurement, source_file) DO NOTHING
    """

    with _conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=200)
            inserted = cur.rowcount

    # rowcount after execute_batch is the count of actually-inserted rows
    # (skipped by ON CONFLICT DO NOTHING are not counted)
    logger.info(
        "Inserted %d/%d lab result(s) from '%s'.", inserted, len(rows), source_file
    )
    return inserted


# ---------------------------------------------------------------------------
# Medical events
# ---------------------------------------------------------------------------


def insert_events(
    events: list[MedicalEvent],
    source_file: str,
) -> int:
    """
    Bulk-insert MedicalEvent objects into the medical_events table.

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
# Processing log
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
# Reference ranges seed
# ---------------------------------------------------------------------------


def seed_reference_ranges(ranges: list[dict]) -> int:
    """
    Insert or update reference range rows from a list of dicts.

    Parameters
    ----------
    ranges : list of dicts matching the reference_ranges.json schema.

    Returns
    -------
    int : Number of rows upserted.
    """
    if not ranges:
        return 0

    sql = """
        INSERT INTO reference_ranges
            (measurement, unit, reference_low, reference_high, scale, category)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (measurement)
        DO UPDATE SET
            unit            = EXCLUDED.unit,
            reference_low   = EXCLUDED.reference_low,
            reference_high  = EXCLUDED.reference_high,
            scale           = EXCLUDED.scale,
            category        = EXCLUDED.category
    """
    rows = [
        (
            r["measurement"],
            r.get("unit", ""),
            r.get("reference_low"),
            r.get("reference_high"),
            r.get("scale", "linear"),
            r.get("category", "Other"),
        )
        for r in ranges
    ]

    with _conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=200)

    logger.info("Seeded %d reference range(s).", len(rows))
    return len(rows)


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
    measurement : str | None — exact measurement name filter.
    category    : str | None — exact category filter.
    start_date  : date | str | None — inclusive lower bound on date.
    end_date    : date | str | None — inclusive upper bound on date.

    Returns
    -------
    list[dict] : Matching rows as plain dicts, newest first.
    """
    conditions: list[str] = []
    params: list = []

    if measurement:
        conditions.append("measurement = %s")
        params.append(measurement)
    if category:
        conditions.append("category = %s")
        params.append(category)
    if start_date:
        conditions.append("date >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("date <= %s")
        params.append(end_date)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT id, date, category, measurement, value, value_text,
               unit, flag, source_file
        FROM lab_results
        {where_clause}
        ORDER BY date DESC, measurement ASC
    """

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# List processed files
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
