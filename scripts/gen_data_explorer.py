#!/usr/bin/env python3
"""Generate the Data Explorer Grafana dashboard.

Produces a dashboard focused on understanding raw data structure:
- Summary stats (counts, coverage)
- Collection timeline (samples per month bar chart)
- Category frequencies (how many metrics per category have data)
- Full metrics catalog with reference ranges and data counts
- Per-metric frequency table (measurements, flag counts)
- Raw samples browser (time-filtered, all columns visible)
- Flag analysis (which metrics go out of range, how often)
- Source documents (one row per lab visit PDF)
- Medical events table
- PDF processing log
"""
import json

DS = {"type": "grafana-postgresql-datasource", "uid": "postgres"}


def stat_panel(panel_id, title, sql, x, y, w=4, h=4, color="blue"):
    return {
        "id": panel_id,
        "title": title,
        "type": "stat",
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS,
        "targets": [{
            "datasource": DS,
            "format": "table",
            "rawQuery": True,
            "rawSql": sql,
            "refId": "A",
            "editorMode": "code",
        }],
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": color, "value": None}],
                },
                "unit": "short",
                "mappings": [],
            },
            "overrides": [],
        },
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "auto",
            "textMode": "auto",
            "colorMode": "background",
            "graphMode": "none",
            "justifyMode": "center",
        },
        "pluginVersion": "11.2.0",
    }


def row_panel(panel_id, title, y, collapsed=False):
    return {
        "id": panel_id,
        "title": title,
        "type": "row",
        "collapsed": collapsed,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "panels": [],
    }


def table_panel(panel_id, title, sql, x, y, w=24, h=10,
                overrides=None, description=""):
    return {
        "id": panel_id,
        "title": title,
        "description": description,
        "type": "table",
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS,
        "targets": [{
            "datasource": DS,
            "format": "table",
            "rawQuery": True,
            "rawSql": sql,
            "refId": "A",
            "editorMode": "code",
        }],
        "transformations": [],
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "align": "auto",
                    "cellOptions": {"type": "auto"},
                    "filterable": True,
                    "inspect": False,
                },
            },
            "overrides": overrides or [],
        },
        "options": {
            "showHeader": True,
            "cellHeight": "sm",
            "footer": {"show": False, "reducer": ["sum"], "countRows": False},
            "sortBy": [],
        },
        "pluginVersion": "11.2.0",
    }


def timeseries_bars_panel(panel_id, title, sql, x, y, w=24, h=8):
    return {
        "id": panel_id,
        "title": title,
        "type": "timeseries",
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS,
        "targets": [{
            "datasource": DS,
            "format": "time_series",
            "rawQuery": True,
            "rawSql": sql,
            "refId": "A",
            "editorMode": "code",
        }],
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "drawStyle": "bars",
                    "barMaxWidth": 25,
                    "fillOpacity": 70,
                    "lineWidth": 0,
                    "showPoints": "never",
                    "gradientMode": "none",
                },
                "color": {"mode": "palette-classic"},
            },
            "overrides": [],
        },
        "options": {
            "tooltip": {"mode": "multi", "sort": "none"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        },
        "pluginVersion": "11.2.0",
    }


# ── Reusable override fragments ───────────────────────────────────────────────

def flag_col_override():
    """Red/orange colour-text mapping for a 'Flag' column (values '', 'H', 'L')."""
    return {
        "matcher": {"id": "byName", "options": "Flag"},
        "properties": [
            {"id": "custom.width", "value": 65},
            {"id": "custom.cellOptions", "value": {"type": "color-text"}},
            {
                "id": "mappings",
                "value": [{
                    "type": "value",
                    "options": {
                        "H": {"text": "H ↑", "color": "red",    "index": 0},
                        "L": {"text": "L ↓", "color": "orange", "index": 1},
                        "":  {"text": "—",  "color": "text",   "index": 2},
                    },
                }],
            },
        ],
    }


def flag_pct_override(col="Flag %", width=70):
    """Green→yellow→orange→red threshold colouring for a flag-percentage column."""
    return {
        "matcher": {"id": "byName", "options": col},
        "properties": [
            {"id": "custom.width", "value": width},
            {"id": "custom.cellOptions", "value": {"type": "color-text"}},
            {
                "id": "thresholds",
                "value": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green",  "value": None},
                        {"color": "yellow", "value": 10},
                        {"color": "orange", "value": 25},
                        {"color": "red",    "value": 50},
                    ],
                },
            },
            {"id": "color", "value": {"mode": "thresholds"}},
        ],
    }


def count_col_override(col, color, width=80, threshold=1):
    """Colour a count column when it exceeds threshold."""
    return {
        "matcher": {"id": "byName", "options": col},
        "properties": [
            {"id": "custom.width", "value": width},
            {"id": "custom.cellOptions", "value": {"type": "color-text"}},
            {
                "id": "thresholds",
                "value": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "text",  "value": None},
                        {"color": color,   "value": threshold},
                    ],
                },
            },
            {"id": "color", "value": {"mode": "thresholds"}},
        ],
    }


def detail_link_override(col, width=200):
    """Clickable link from a metric name column to the detail dashboard."""
    return {
        "matcher": {"id": "byName", "options": col},
        "properties": [
            {"id": "custom.width", "value": width},
            {
                "id": "links",
                "value": [{
                    "title": "Open detail: ${__data.fields." + col + "}",
                    "url": "/d/lab-metric-detail?var-metric=${__data.fields." + col + "}&${__url_time_range}",
                    "targetBlank": False,
                }],
            },
        ],
    }


def w(col, width):
    return {"matcher": {"id": "byName", "options": col},
            "properties": [{"id": "custom.width", "value": width}]}


# ── Dashboard builder ─────────────────────────────────────────────────────────

def build_dashboard():
    panels = []
    pid = 1
    y = 0

    # ── Section 1: Summary stats ──────────────────────────────────────────
    panels.append(row_panel(pid, "Summary", y))
    pid += 1
    y += 1

    stat_defs = [
        ("Total Samples",
         'SELECT COUNT(*) AS "Total Samples" FROM samples',
         "blue"),
        ("Metrics Measured",
         'SELECT COUNT(DISTINCT metric) AS "Measured" FROM samples',
         "purple"),
        ("Source Documents",
         'SELECT COUNT(*) AS "Documents" FROM documents',
         "dark-blue"),
        ("Medical Events",
         'SELECT COUNT(*) AS "Events" FROM events',
         "dark-green"),
        ("Flagged Samples",
         'SELECT COUNT(*) AS "Flagged" FROM samples WHERE flag IS NOT NULL',
         "orange"),
        ("Catalog Coverage %",
         ('SELECT ROUND(100.0 * COUNT(DISTINCT metric)'
          ' / NULLIF((SELECT COUNT(*) FROM metrics), 0), 0)'
          ' AS "Coverage %" FROM samples'),
         "green"),
    ]
    for i, (title, sql, color) in enumerate(stat_defs):
        panels.append(stat_panel(pid, title, sql, x=i * 4, y=y, color=color))
        pid += 1
    y += 4

    # ── Section 2: Collection timeline ───────────────────────────────────
    panels.append(row_panel(pid, "Collection Timeline", y))
    pid += 1
    y += 1

    timeline_sql = (
        "SELECT\n"
        "  date_trunc('month', time)::timestamptz AS time,\n"
        "  COUNT(*) AS \"Samples\",\n"
        "  COUNT(DISTINCT metric) AS \"Distinct Metrics\"\n"
        "FROM samples\n"
        "GROUP BY 1\n"
        "ORDER BY 1"
    )
    panels.append(timeseries_bars_panel(
        pid, "Samples Collected per Month", timeline_sql, 0, y, h=8,
    ))
    pid += 1
    y += 8

    # ── Section 3: Category frequencies ──────────────────────────────────
    panels.append(row_panel(pid, "Category Frequencies", y))
    pid += 1
    y += 1

    cat_sql = (
        "SELECT\n"
        "  m.category                                     AS \"Category\",\n"
        "  COUNT(DISTINCT m.name)                         AS \"Defined\",\n"
        "  COUNT(DISTINCT s.metric)                       AS \"With Data\",\n"
        "  ROUND(100.0 * COUNT(DISTINCT s.metric)\n"
        "        / COUNT(DISTINCT m.name), 0)             AS \"Coverage %\",\n"
        "  COALESCE(COUNT(s.value), 0)                    AS \"Total Samples\",\n"
        "  COUNT(s.value) FILTER (WHERE s.flag = 'H')     AS \"High (H)\",\n"
        "  COUNT(s.value) FILTER (WHERE s.flag = 'L')     AS \"Low (L)\",\n"
        "  COUNT(s.value) FILTER (WHERE s.flag IS NOT NULL) AS \"Flagged\",\n"
        "  CASE WHEN COUNT(s.value) > 0\n"
        "    THEN ROUND(100.0\n"
        "               * COUNT(s.value) FILTER (WHERE s.flag IS NOT NULL)\n"
        "               / COUNT(s.value), 1)\n"
        "    ELSE 0\n"
        "  END                                            AS \"Flag %\"\n"
        "FROM metrics m\n"
        "LEFT JOIN samples s ON s.metric = m.name\n"
        "GROUP BY m.category\n"
        "ORDER BY COUNT(s.value) DESC NULLS LAST"
    )
    cat_overrides = [
        w("Category", 210),
        w("Defined", 70),
        w("With Data", 80),
        {
            "matcher": {"id": "byName", "options": "Coverage %"},
            "properties": [
                {"id": "custom.width", "value": 95},
                {"id": "custom.cellOptions", "value": {"type": "color-background"}},
                {"id": "color", "value": {"mode": "thresholds"}},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "red",    "value": None},
                    {"color": "orange", "value": 25},
                    {"color": "yellow", "value": 50},
                    {"color": "green",  "value": 100},
                ]}},
            ],
        },
        w("Total Samples", 110),
        count_col_override("High (H)", "red",    width=80),
        count_col_override("Low (L)",  "orange", width=70),
        w("Flagged", 75),
        flag_pct_override(),
    ]
    panels.append(table_panel(
        pid, "Category Frequencies", cat_sql, 0, y, h=10,
        overrides=cat_overrides,
        description=(
            "One row per metric category. "
            "Coverage % = metrics with at least one measurement / total metrics defined. "
            "Flag % = flagged samples / total samples."
        ),
    ))
    pid += 1
    y += 10

    # ── Section 4: Metrics catalog ────────────────────────────────────────
    panels.append(row_panel(pid, "Metrics Catalog — all 108 metrics + reference ranges", y))
    pid += 1
    y += 1

    catalog_sql = (
        "SELECT\n"
        "  m.category                                     AS \"Category\",\n"
        "  m.display_name                                 AS \"Metric\",\n"
        "  COALESCE(m.unit, '')                           AS \"Unit\",\n"
        "  COALESCE(m.scale, 'linear')                    AS \"Scale\",\n"
        "  rr.range_type                                  AS \"Range Type\",\n"
        "  rr.ref_low                                     AS \"Ref Low\",\n"
        "  rr.ref_high                                    AS \"Ref High\",\n"
        "  COALESCE(rr.sex, 'any')                        AS \"Sex\",\n"
        "  CASE\n"
        "    WHEN rr.age_min IS NOT NULL AND rr.age_max IS NOT NULL\n"
        "      THEN rr.age_min::text || '–' || rr.age_max::text\n"
        "    WHEN rr.age_min IS NOT NULL THEN '>=' || rr.age_min::text\n"
        "    WHEN rr.age_max IS NOT NULL THEN '<'  || rr.age_max::text\n"
        "    ELSE 'any'\n"
        "  END                                            AS \"Age\",\n"
        "  COALESCE(stats.n, 0)                           AS \"# Samples\",\n"
        "  stats.first_date                               AS \"First Seen\",\n"
        "  stats.last_date                                AS \"Last Seen\",\n"
        "  CASE WHEN stats.n > 0\n"
        "    THEN ROUND(100.0 * stats.n_flagged / stats.n, 1)\n"
        "  END                                            AS \"Flag %\",\n"
        "  LEFT(COALESCE(m.description, ''), 200)         AS \"Description\"\n"
        "FROM metrics m\n"
        "LEFT JOIN reference_ranges rr\n"
        "  ON rr.metric = m.name\n"
        "LEFT JOIN (\n"
        "  SELECT metric,\n"
        "    COUNT(*)                                  AS n,\n"
        "    COUNT(*) FILTER (WHERE flag IS NOT NULL)  AS n_flagged,\n"
        "    MIN(time::date)                           AS first_date,\n"
        "    MAX(time::date)                           AS last_date\n"
        "  FROM samples\n"
        "  GROUP BY metric\n"
        ") stats ON stats.metric = m.name\n"
        "ORDER BY m.category, m.sort_order, m.display_name,\n"
        "         rr.range_type NULLS LAST, rr.sex NULLS FIRST"
    )
    catalog_overrides = [
        w("Category",   180),
        detail_link_override("Metric", width=200),
        w("Unit",       80),
        w("Scale",      75),
        w("Range Type", 90),
        w("Ref Low",    70),
        w("Ref High",   70),
        w("Sex",        50),
        w("Age",        70),
        w("# Samples",  85),
        w("First Seen", 90),
        w("Last Seen",  90),
        flag_pct_override(),
        {
            "matcher": {"id": "byName", "options": "Description"},
            "properties": [
                {"id": "custom.width",   "value": 260},
                {"id": "custom.inspect", "value": True},
            ],
        },
    ]
    panels.append(table_panel(
        pid,
        "Metrics Catalog — all metrics with reference ranges and data counts",
        catalog_sql, 0, y, h=18,
        overrides=catalog_overrides,
        description=(
            "Every metric in the catalog joined to its reference range(s). "
            "Metrics with multiple ranges (e.g. sex-specific) appear on separate rows. "
            "# Samples, First/Last Seen, and Flag % come from actual data. "
            "Click a metric name to open its detail dashboard."
        ),
    ))
    pid += 1
    y += 18

    # ── Section 5: Per-metric frequencies ────────────────────────────────
    panels.append(row_panel(pid, "Per-Metric Frequencies (measured metrics only)", y))
    pid += 1
    y += 1

    freq_sql = (
        "SELECT\n"
        "  m.category                                              AS \"Category\",\n"
        "  m.display_name                                         AS \"Metric\",\n"
        "  COALESCE(m.unit, '')                                   AS \"Unit\",\n"
        "  COUNT(*)                                               AS \"# Measurements\",\n"
        "  MIN(s.time::date)                                      AS \"First\",\n"
        "  MAX(s.time::date)                                      AS \"Latest\",\n"
        "  (MAX(s.time::date) - MIN(s.time::date))                AS \"Days Tracked\",\n"
        "  COUNT(*) FILTER (WHERE s.flag = 'H')                   AS \"High (H)\",\n"
        "  COUNT(*) FILTER (WHERE s.flag = 'L')                   AS \"Low (L)\",\n"
        "  COUNT(*) FILTER (WHERE s.flag IS NULL)                 AS \"Normal\",\n"
        "  ROUND(\n"
        "    100.0 * COUNT(*) FILTER (WHERE s.flag IS NOT NULL)\n"
        "    / COUNT(*), 1\n"
        "  )                                                      AS \"Flag %\"\n"
        "FROM samples s\n"
        "JOIN metrics m ON m.name = s.metric\n"
        "GROUP BY m.name, m.display_name, m.category, m.unit\n"
        "ORDER BY COUNT(*) DESC, m.category, m.display_name"
    )
    freq_overrides = [
        w("Category", 180),
        detail_link_override("Metric", width=200),
        w("Unit",            80),
        w("# Measurements", 130),
        w("First",           90),
        w("Latest",          90),
        {
            "matcher": {"id": "byName", "options": "Days Tracked"},
            "properties": [
                {"id": "custom.width", "value": 105},
                {"id": "unit", "value": "d"},
            ],
        },
        count_col_override("High (H)", "red",    width=80),
        count_col_override("Low (L)",  "orange", width=75),
        w("Normal", 75),
        flag_pct_override(),
    ]
    panels.append(table_panel(
        pid, "Per-Metric Frequencies", freq_sql, 0, y, h=14,
        overrides=freq_overrides,
        description=(
            "Only metrics that appear in the samples table. "
            "Sorted by measurement count descending — the most-tracked metrics first. "
            "High/Low counts match the 'H'/'L' flags recorded by the lab."
        ),
    ))
    pid += 1
    y += 14

    # ── Section 6: Raw samples browser ───────────────────────────────────
    panels.append(row_panel(pid, "Raw Samples Browser", y))
    pid += 1
    y += 1

    raw_sql = (
        "SELECT\n"
        "  s.time::date                           AS \"Date\",\n"
        "  m.category                             AS \"Category\",\n"
        "  m.display_name                         AS \"Metric\",\n"
        "  s.value                                AS \"Value\",\n"
        "  COALESCE(s.value_text, '')             AS \"Value Text\",\n"
        "  COALESCE(m.unit, '')                   AS \"Unit\",\n"
        "  COALESCE(s.flag, '')                   AS \"Flag\",\n"
        "  rr.ref_low                             AS \"Ref Low\",\n"
        "  rr.ref_high                            AS \"Ref High\",\n"
        "  COALESCE(d.lab_name, '—')         AS \"Lab\",\n"
        "  d.filename                             AS \"Source File\"\n"
        "FROM samples s\n"
        "JOIN  metrics   m ON m.name         = s.metric\n"
        "JOIN  documents d ON d.id           = s.document_id\n"
        "LEFT JOIN reference_ranges rr\n"
        "  ON  rr.metric     = s.metric\n"
        "  AND rr.range_type = 'standard'\n"
        "  AND rr.sex        IS NULL\n"
        "  AND rr.age_min    IS NULL\n"
        "WHERE $__timeFilter(s.time)\n"
        "ORDER BY s.time DESC\n"
        "LIMIT 2000"
    )
    raw_overrides = [
        w("Date",         90),
        w("Category",    180),
        detail_link_override("Metric", width=200),
        {"matcher": {"id": "byName", "options": "Value"},
         "properties": [{"id": "custom.width", "value": 80},
                        {"id": "custom.align",  "value": "right"}]},
        w("Value Text",  110),
        w("Unit",         80),
        flag_col_override(),
        w("Ref Low",      70),
        w("Ref High",     70),
        w("Lab",         120),
        w("Source File", 260),
    ]
    panels.append(table_panel(
        pid,
        "Raw Samples — every individual measurement (most recent 2 000, time-range filtered)",
        raw_sql, 0, y, h=16,
        overrides=raw_overrides,
        description=(
            "One row per sample point. All columns are shown: value, unit, flag, "
            "reference range from the catalog, lab name, and source PDF filename. "
            "Use the dashboard time-range picker to focus on a period. "
            "Results are capped at 2 000 rows (most recent first)."
        ),
    ))
    pid += 1
    y += 16

    # ── Section 7: Flag analysis ──────────────────────────────────────────
    panels.append(row_panel(pid, "Flag Analysis — out-of-range breakdown per metric", y))
    pid += 1
    y += 1

    flag_sql = (
        "SELECT\n"
        "  m.display_name                                          AS \"Metric\",\n"
        "  m.category                                             AS \"Category\",\n"
        "  COALESCE(m.unit, '')                                   AS \"Unit\",\n"
        "  COUNT(*)                                               AS \"Total\",\n"
        "  COUNT(*) FILTER (WHERE s.flag = 'H')                   AS \"High (H)\",\n"
        "  COUNT(*) FILTER (WHERE s.flag = 'L')                   AS \"Low (L)\",\n"
        "  COUNT(*) FILTER (WHERE s.flag IS NULL)                 AS \"Normal\",\n"
        "  ROUND(\n"
        "    100.0 * COUNT(*) FILTER (WHERE s.flag IS NOT NULL)\n"
        "    / COUNT(*), 1\n"
        "  )                                                      AS \"Flag %\"\n"
        "FROM samples s\n"
        "JOIN metrics m ON m.name = s.metric\n"
        "GROUP BY m.name, m.display_name, m.category, m.unit\n"
        "HAVING COUNT(*) FILTER (WHERE s.flag IS NOT NULL) > 0\n"
        "ORDER BY COUNT(*) FILTER (WHERE s.flag IS NOT NULL) DESC,\n"
        "         \"Flag %\" DESC"
    )
    flag_overrides = [
        detail_link_override("Metric", width=200),
        w("Category", 180),
        w("Unit",      80),
        w("Total",     65),
        count_col_override("High (H)", "red",    width=80),
        count_col_override("Low (L)",  "orange", width=75),
        w("Normal", 75),
        flag_pct_override(),
    ]
    panels.append(table_panel(
        pid,
        "Flag Analysis — metrics with at least one out-of-range result",
        flag_sql, 0, y, h=10,
        overrides=flag_overrides,
        description=(
            "Only metrics where at least one result carried an H or L flag. "
            "Sorted by absolute flagged count descending. "
            "Flag % = (H + L) / Total × 100."
        ),
    ))
    pid += 1
    y += 10

    # ── Section 8: Source documents ───────────────────────────────────────
    panels.append(row_panel(pid, "Source Documents (lab visits)", y))
    pid += 1
    y += 1

    docs_sql = (
        "SELECT\n"
        "  d.date                                              AS \"Date\",\n"
        "  COALESCE(d.lab_name, '—')                     AS \"Lab\",\n"
        "  COUNT(DISTINCT s.metric)                           AS \"Unique Metrics\",\n"
        "  COUNT(s.value)                                     AS \"Samples\",\n"
        "  COUNT(s.value) FILTER (WHERE s.flag IS NOT NULL)   AS \"Flagged\",\n"
        "  d.filename                                         AS \"Filename\",\n"
        "  d.processed_at::date                               AS \"Processed\"\n"
        "FROM documents d\n"
        "LEFT JOIN samples s ON s.document_id = d.id\n"
        "GROUP BY d.id, d.date, d.lab_name, d.filename, d.processed_at\n"
        "ORDER BY d.date DESC"
    )
    docs_overrides = [
        w("Date",           90),
        w("Lab",           160),
        w("Unique Metrics", 120),
        w("Samples",         80),
        count_col_override("Flagged", "orange", width=75),
        w("Filename",       300),
        w("Processed",       90),
    ]
    panels.append(table_panel(
        pid, "Source Documents", docs_sql, 0, y, h=8,
        overrides=docs_overrides,
        description=(
            "One row per processed PDF (lab visit). "
            "Shows how many distinct metrics and total samples were extracted "
            "from each document, and how many were flagged."
        ),
    ))
    pid += 1
    y += 8

    # ── Section 9: Medical events ─────────────────────────────────────────
    panels.append(row_panel(pid, "Medical Events", y))
    pid += 1
    y += 1

    events_sql = (
        "SELECT\n"
        "  e.date                                AS \"Date\",\n"
        "  COALESCE(e.end_date::text, '—')  AS \"End Date\",\n"
        "  e.category                            AS \"Category\",\n"
        "  COALESCE(e.subcategory, '—')     AS \"Subcategory\",\n"
        "  e.title                               AS \"Title\",\n"
        "  COALESCE(e.description, '')           AS \"Description\"\n"
        "FROM events e\n"
        "ORDER BY e.date DESC"
    )
    events_overrides = [
        w("Date",        90),
        w("End Date",    90),
        w("Category",   110),
        w("Subcategory",130),
        w("Title",      240),
        {"matcher": {"id": "byName", "options": "Description"},
         "properties": [{"id": "custom.inspect", "value": True}]},
    ]
    panels.append(table_panel(
        pid, "Medical Events", events_sql, 0, y, h=8,
        overrides=events_overrides,
        description=(
            "All medical events extracted from source documents "
            "(imaging, procedures, diagnoses, medications, vaccinations, visits). "
            "Long descriptions can be read in full via the cell inspect drawer."
        ),
    ))
    pid += 1
    y += 8

    # ── Section 10: PDF processing log ───────────────────────────────────
    panels.append(row_panel(pid, "PDF Processing Log", y))
    pid += 1
    y += 1

    log_sql = (
        "SELECT\n"
        "  p.processed_at                          AS \"Processed At\",\n"
        "  p.status                                AS \"Status\",\n"
        "  COALESCE(p.records_extracted, 0)        AS \"Records\",\n"
        "  p.filename                              AS \"Filename\",\n"
        "  COALESCE(p.error_message, '')           AS \"Error\"\n"
        "FROM pdf_processing_log p\n"
        "ORDER BY p.processed_at DESC"
    )
    log_overrides = [
        w("Processed At", 160),
        {
            "matcher": {"id": "byName", "options": "Status"},
            "properties": [
                {"id": "custom.width", "value": 110},
                {"id": "custom.cellOptions", "value": {"type": "color-text"}},
                {
                    "id": "mappings",
                    "value": [{
                        "type": "value",
                        "options": {
                            "success":   {"color": "green",  "text": "✓ success",   "index": 0},
                            "failed":    {"color": "red",    "text": "✗ failed",    "index": 1},
                            "duplicate": {"color": "orange", "text": "⊖ duplicate", "index": 2},
                        },
                    }],
                },
            ],
        },
        w("Records",   70),
        w("Filename", 310),
        {"matcher": {"id": "byName", "options": "Error"},
         "properties": [{"id": "custom.inspect", "value": True}]},
    ]
    panels.append(table_panel(
        pid, "PDF Processing Log", log_sql, 0, y, h=8,
        overrides=log_overrides,
        description=(
            "Pipeline audit trail — every PDF the extractor has seen, "
            "its outcome (success / failed / duplicate), "
            "number of records extracted, and any error message."
        ),
    ))

    return {
        "annotations": {"list": []},
        "description": (
            "Raw data explorer — understand exactly what data exists, "
            "when it was collected, which metrics are covered, how values compare "
            "to reference ranges, and where the data came from. "
            "Nothing is pre-aggregated or hidden."
        ),
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": [
            {
                "icon": "dashboard",
                "title": "← Lab Results Overview",
                "type": "link",
                "url": "/d/lab-results-overview",
                "tooltip": "",
            },
            {
                "icon": "dashboard",
                "title": "Health Timeline",
                "type": "link",
                "url": "/d/health-timeline",
                "tooltip": "",
            },
        ],
        "panels": panels,
        "schemaVersion": 39,
        "tags": ["health", "explorer", "data"],
        "templating": {"list": []},
        "time": {"from": "now-10y", "to": "now"},
        "timepicker": {"refresh_intervals": ["5m", "15m", "1h"]},
        "timezone": "browser",
        "title": "Data Explorer",
        "uid": "data-explorer",
        "version": 1,
    }


if __name__ == "__main__":
    import pathlib
    dashboards = (
        pathlib.Path(__file__).resolve().parent.parent
        / "grafana" / "dashboards"
    )
    out = dashboards / "data-explorer.json"
    with open(out, "w") as f:
        json.dump(build_dashboard(), f, indent=2)
    dashboard = build_dashboard()
    panel_count = len(dashboard["panels"])
    print(f"Generated {out}  ({panel_count} panels)")
