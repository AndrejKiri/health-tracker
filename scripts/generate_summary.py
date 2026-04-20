#!/usr/bin/env python3
"""
Generate data/summaries/metrics_summary.json.

Contains only metric names, categories, and entry counts — no actual health values.
Run via: make summary
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname": os.getenv("POSTGRES_DB", "health_tracker"),
    "user": os.getenv("POSTGRES_USER", "health"),
    "password": os.getenv("POSTGRES_PASSWORD", "health"),
}

QUERY = """
SELECT
    m.name,
    m.display_name,
    m.category,
    COUNT(s.value)          AS entry_count,
    MIN(s.time)::date       AS first_date,
    MAX(s.time)::date       AS latest_date
FROM metrics m
LEFT JOIN samples s ON s.metric = m.name
GROUP BY m.name, m.display_name, m.category
ORDER BY m.category, m.name;
"""

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "summaries" / "metrics_summary.json"


def main() -> None:
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to database — {e}", file=sys.stderr)
        sys.exit(1)

    with conn:
        with conn.cursor() as cur:
            cur.execute(QUERY)
            rows = cur.fetchall()

    conn.close()

    metrics = []
    total_entries = 0
    metrics_with_data = 0

    for name, display_name, category, entry_count, first_date, latest_date in rows:
        count = int(entry_count or 0)
        total_entries += count
        if count > 0:
            metrics_with_data += 1
        metrics.append({
            "name": name,
            "display_name": display_name,
            "category": category,
            "entry_count": count,
            "first_date": str(first_date) if first_date else None,
            "latest_date": str(latest_date) if latest_date else None,
        })

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": total_entries,
        "total_metrics_with_data": metrics_with_data,
        "metrics": metrics,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Written: {OUTPUT_PATH}")
    print(f"  {metrics_with_data} metrics with data, {total_entries} total entries")


if __name__ == "__main__":
    main()
