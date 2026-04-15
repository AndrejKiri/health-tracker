#!/usr/bin/env python3
"""Convert seed_sample_data.sql from old lab_results format to new samples format.

Reads the existing INSERT statements and emits:
  1. INSERT into documents (one row per distinct source_file)
  2. INSERT into samples (referencing document_id via subquery)
"""
import re
import sys
from pathlib import Path
from collections import defaultdict

SEED_PATH = Path(__file__).resolve().parent.parent / "db" / "seed_sample_data.sql"
OUT_PATH = SEED_PATH  # overwrite in place

# Pattern for old-format INSERT values:
# ('2022-11-10T00:00:00+00:00', 'Complete Blood Count', 'WBC', 11.6, 'x10E9/L', 'H', 'osteosarc_sample_data')
# ('2022-11-10T00:00:00+00:00', 'Complete Blood Count', 'WBC', 11.6, 'x10E9/L', NULL, 'osteosarc_sample_data')
ROW_RE = re.compile(
    r"\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*([\d.]+|NULL)\s*,\s*'([^']*)'\s*,\s*('H'|'L'|NULL)\s*,\s*'([^']+)'\s*\)"
)


def parse_seed(path: Path) -> list[dict]:
    """Parse existing INSERT statements into dicts."""
    text = path.read_text()
    rows = []
    for m in ROW_RE.finditer(text):
        date, category, measurement, value, unit, flag, source_file = m.groups()
        rows.append({
            "date": date,
            "category": category,
            "measurement": measurement,
            "value": value,
            "unit": unit,
            "flag": flag,  # already quoted or NULL
            "source_file": source_file,
        })
    return rows


def emit_new_sql(rows: list[dict]) -> str:
    """Generate new-format SQL for documents + samples."""
    lines = []
    lines.append("-- Seed sample data for health tracker (new schema)")
    lines.append(f"-- Converted from {len(rows)} lab_results rows\n")

    # Collect distinct source files with their earliest date
    sources: dict[str, str] = {}
    for r in rows:
        sf = r["source_file"]
        if sf not in sources or r["date"] < sources[sf]:
            sources[sf] = r["date"]

    # 1. Documents
    lines.append("-- ============================================================")
    lines.append(f"-- Documents ({len(sources)} source files)")
    lines.append("-- ============================================================\n")
    for sf, earliest in sorted(sources.items()):
        date_only = earliest.split("T")[0]
        lines.append(
            f"INSERT INTO documents (date, filename) "
            f"VALUES ('{date_only}', '{sf}') "
            f"ON CONFLICT (filename) DO NOTHING;"
        )

    # 2. Ensure metrics exist for all measurements in seed data
    metrics_seen: dict[str, tuple[str, str]] = {}
    for r in rows:
        if r["measurement"] not in metrics_seen:
            metrics_seen[r["measurement"]] = (r["category"], r["unit"])

    lines.append("\n-- ============================================================")
    lines.append(f"-- Ensure metrics exist ({len(metrics_seen)} measurements)")
    lines.append("-- ============================================================\n")
    for meas, (cat, unit) in sorted(metrics_seen.items()):
        lines.append(
            f"INSERT INTO metrics (name, display_name, category, unit) "
            f"VALUES ('{meas}', '{meas}', '{cat}', '{unit}') "
            f"ON CONFLICT (name) DO NOTHING;"
        )

    # 3. Samples (batch by source file for readability)
    lines.append("\n-- ============================================================")
    lines.append(f"-- Samples ({len(rows)} records)")
    lines.append("-- ============================================================\n")

    by_source = defaultdict(list)
    for r in rows:
        by_source[r["source_file"]].append(r)

    for sf, sf_rows in sorted(by_source.items()):
        lines.append(f"-- Source: {sf} ({len(sf_rows)} samples)")
        lines.append(
            f"INSERT INTO samples (time, metric, value, value_text, flag, document_id)"
        )

        # Build VALUES with subquery for document_id
        val_lines = []
        for r in sf_rows:
            val = r["value"] if r["value"] != "NULL" else "NULL"
            flag = r["flag"]  # 'H', 'L', or NULL (already formatted)
            val_lines.append(
                f"  ('{r['date']}', '{r['measurement']}', {val}, NULL, {flag}, "
                f"(SELECT id FROM documents WHERE filename = '{sf}'))"
            )

        # Join with commas, last line gets semicolon
        for i, vl in enumerate(val_lines):
            sep = "," if i < len(val_lines) - 1 else ""
            if i == 0:
                lines.append(f"VALUES\n{vl}{sep}")
            else:
                lines.append(f"{vl}{sep}")
        lines.append("ON CONFLICT (time, metric, document_id) DO NOTHING;\n")

    return "\n".join(lines)


def main():
    if not SEED_PATH.exists():
        print(f"Seed file not found: {SEED_PATH}", file=sys.stderr)
        sys.exit(1)

    rows = parse_seed(SEED_PATH)
    if not rows:
        print("No rows parsed from seed file!", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(rows)} rows from {SEED_PATH}")

    new_sql = emit_new_sql(rows)
    OUT_PATH.write_text(new_sql)
    print(f"Wrote {OUT_PATH} ({len(new_sql)} bytes)")


if __name__ == "__main__":
    main()
