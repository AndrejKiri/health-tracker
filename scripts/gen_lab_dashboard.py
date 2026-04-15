#!/usr/bin/env python3
"""Generate a compact Grafana dashboard using Table panels with sparkline cells."""
import json

DS = {"type": "grafana-postgresql-datasource", "uid": "postgres"}

# Categories in display order: (measurement, unit, ref_low, ref_high)
CATEGORIES = [
    ("Complete Blood Count", [
        ("WBC", "x10E9/L", 3.4, 10),
        ("RBC", "x10E12/L", 4.5, 5.5),
        ("Hemoglobin", "g/dL", 13.5, 17.7),
        ("Hematocrit", "%", 41, 53),
        ("Platelets", "x10E9/L", 150, 400),
        ("MCV", "fL", 80, 100),
        ("MCH", "pg", 27, 33),
        ("MCHC", "g/dL", 32, 36),
        ("RDW", "%", 11.5, 14.5),
        ("MPV", "fL", 7.5, 12.5),
    ]),
    ("WBC Differential (absolute)", [
        ("Abs Neutrophils", "x10E9/L", 1.5, 7.8),
        ("Abs Lymphocytes", "x10E9/L", 1, 3.4),
        ("Abs Monocytes", "x10E9/L", 0.2, 0.95),
        ("Abs Eosinophils", "x10E9/L", 0.015, 0.5),
        ("Abs Basophils", "x10E9/L", 0, 0.2),
        ("Abs Immature Granulocytes", "x10E9/L", None, None),
    ]),
    ("WBC Differential (%)", [
        ("Neutrophils %", "%", 40, 70),
        ("Lymphocytes %", "%", 20, 40),
        ("Monocytes %", "%", 2, 8),
        ("Eosinophils %", "%", 1, 4),
        ("Basophils %", "%", 0, 1),
        ("Immature Granulocytes %", "%", None, None),
    ]),
    ("Metabolic Panel", [
        ("Glucose", "mg/dL", 70, 100),
        ("BUN", "mg/dL", 7, 25),
        ("Creatinine", "mg/dL", 0.6, 1.29),
        ("eGFR", "", None, None),
        ("Sodium", "mmol/L", 136, 145),
        ("Potassium", "mmol/L", 3.5, 5.1),
        ("Chloride", "mmol/L", 98, 110),
        ("CO2", "mmol/L", 20, 32),
        ("Calcium", "mg/dL", 8.6, 10.3),
        ("Anion Gap", "", 3, 12),
    ]),
    ("Liver Panel", [
        ("ALT", "U/L", 9, 46),
        ("AST", "U/L", 10, 40),
        ("Alk Phos", "U/L", 36, 130),
        ("Total Bilirubin", "mg/dL", 0.1, 1.2),
        ("Direct Bilirubin", "mg/dL", 0, 0.2),
        ("GGT", "U/L", None, None),
        ("Albumin", "g/dL", 3.6, 5.1),
        ("Total Protein", "g/dL", 6, 8.3),
        ("Globulin", "g/dL", 2, 3.5),
        ("A/G Ratio", "", 1, 2.5),
    ]),
    ("Lipid Panel", [
        ("Total Cholesterol", "mg/dL", 0, 200),
        ("HDL Cholesterol", "mg/dL", 40, 60),
        ("LDL Cholesterol", "mg/dL", 0, 100),
        ("Triglycerides", "mg/dL", 0, 150),
        ("Non-HDL Cholesterol", "mg/dL", None, None),
        ("Apolipoprotein B", "mg/dL", None, None),
        ("Cholesterol/HDL Ratio", "", None, None),
    ]),
    ("Thyroid", [
        ("TSH", "mIU/L", 0.4, 4.5),
        ("Free T4", "ng/dL", 0.8, 1.8),
        ("Free T3", "pg/mL", 2.3, 4.2),
        ("T4 Total", "mcg/dL", 4.9, 10.5),
        ("T3 Total", "ng/dL", 87, 167),
    ]),
    ("Cardiac Markers", [
        ("Troponin I", "ug/L", None, None),
        ("CK", "U/L", 44, 196),
        ("CK-MB", "ug/L", None, None),
        ("BNP", "pg/mL", None, None),
    ]),
    ("Iron Studies", [
        ("Ferritin", "ng/mL", 38, 380),
        ("Iron", "mcg/dL", 60, 170),
        ("TIBC", "mcg/dL", 250, 370),
        ("Transferrin Saturation", "%", 20, 50),
    ]),
    ("Coagulation", [
        ("PT", "sec", 11, 14),
        ("PTT", "sec", 25, 35),
        ("INR", "", 0.8, 1.2),
        ("Fibrinogen", "mg/dL", None, None),
    ]),
    ("Inflammatory Markers", [
        ("CRP", "mg/L", 0, 5),
        ("hsCRP", "mg/L", 0, 1),
        ("ESR", "mm/h", 0, 15),
        ("IL-6", "pg/mL", None, None),
    ]),
    ("Endocrine", [
        ("Insulin", "uIU/mL", None, None),
        ("Cortisol", "ug/dL", None, None),
        ("ACTH", "pg/mL", None, None),
    ]),
    ("Vitamins", [
        ("Vitamin D", "ng/mL", 30, 100),
        ("Vitamin B12", "pg/mL", 200, 900),
        ("Folate", "ng/mL", None, None),
    ]),
    ("Other Chemistry", [
        ("Hemoglobin A1c", "%", 4, 5.6),
        ("LDH", "U/L", 120, 246),
        ("Magnesium", "mg/dL", 1.7, 2.2),
        ("Ionized Calcium", "mmol/L", None, None),
        ("Uric Acid", "mg/dL", None, None),
        ("Phosphorus", "mg/dL", None, None),
        ("Lactate", "mmol/L", None, None),
    ]),
    ("Lymphocyte Subsets", [
        ("CD3 T Cells %", "% Lymphs", None, None),
        ("CD3 T Cells Abs", "x10E6/L", None, None),
        ("CD4 T Cells %", "% Lymphs", None, None),
        ("CD4 T Cells Abs", "x10E6/L", None, None),
        ("CD8 T Cells %", "% Lymphs", None, None),
        ("CD8 T Cells Abs", "x10E6/L", None, None),
        ("CD4/CD8 Ratio", "ratio", None, None),
        ("CD19 B Cells %", "% Lymphs", None, None),
        ("CD19 B Cells Abs", "x10E6/L", None, None),
        ("CD16/CD56 NK Cells %", "% Lymphs", None, None),
    ]),
    ("Blood Gas", [
        ("pH", "", None, None),
        ("PCO2", "mm Hg", None, None),
        ("PO2", "mm Hg", None, None),
        ("Oxygen Saturation", "%", None, None),
        ("Base Excess", "mmol/L", None, None),
    ]),
    ("Urinalysis & Other", [
        ("BUN/Creatinine Ratio", "", None, None),
        ("Glucose, Urine", "mg/dL", None, None),
        ("Ketones, Urine", "mg/dL", None, None),
        ("Specific Gravity, Urine", "", None, None),
        ("Urine pH", "", None, None),
        ("Reticulocyte Count", "x10E9/L", None, None),
        ("Nucleated RBC", "/100 WBC", None, None),
        ("Mean Plasma Glucose", "mg/dL", None, None),
    ]),
]


def make_table_panel(panel_id, category, measurements, x, y):
    """Create a Table panel with sparkline cells for one category."""
    # Pivot to wide format via FILTER (WHERE): one column per metric.
    # Grafana treats each column as a named time series.
    filter_cols = ",\n    ".join(
        f"MAX(s.value) FILTER (WHERE s.metric = '{m[0]}') AS \"{m[0]}\""
        for m in measurements
    )
    meas_list = ", ".join(f"'{m[0]}'" for m in measurements)
    sql = (
        f"SELECT s.time,\n"
        f"    {filter_cols}\n"
        f"FROM samples s\n"
        f"WHERE s.metric IN ({meas_list})\n"
        f"  AND $__timeFilter(s.time)\n"
        f"  AND s.value IS NOT NULL\n"
        f"GROUP BY s.time\n"
        f"ORDER BY s.time"
    )

    n = len(measurements)
    h = max(n * 2 + 3, 6)

    # After timeSeriesTable transform on wide-format time series,
    # columns should be: "Name" (measurement) + "Trend" (sparkline) + aggregates.
    overrides = [
        # All Trend columns: render as sparkline
        {
            "matcher": {"id": "byRegexp", "options": "/Trend|#/"},
            "properties": [
                {
                    "id": "custom.cellOptions",
                    "value": {
                        "type": "sparkline",
                        "drawStyle": "line",
                        "lineWidth": 1,
                        "fillOpacity": 15,
                        "pointSize": 3,
                        "showPoints": "always",
                    },
                },
            ],
        },
        # Name column: fixed narrow width
        {
            "matcher": {"id": "byName", "options": "Name"},
            "properties": [
                {"id": "custom.width", "value": 200},
            ],
        },
    ]

    # Hide common aggregate columns the transform might produce
    for col in ("Last", "Min", "Max", "Mean", "Count", "Total", "First"):
        overrides.append({
            "matcher": {"id": "byName", "options": col},
            "properties": [{"id": "custom.hidden", "value": True}],
        })

    return {
        "id": panel_id,
        "title": f"{category} ({n})",
        "type": "table",
        "gridPos": {"x": x, "y": y, "w": 24, "h": h},
        "datasource": DS,
        "targets": [
            {
                "datasource": DS,
                "format": "time_series",
                "rawQuery": True,
                "rawSql": sql,
                "refId": "A",
                "editorMode": "code",
                "sql": {
                    "columns": [{"parameters": [], "type": "function"}],
                    "groupBy": [{"property": {"type": "string"}, "type": "groupBy"}],
                    "limit": 50,
                },
            }
        ],
        "transformations": [
            {
                "id": "timeSeriesTable",
                "options": {},
            }
        ],
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "cellOptions": {"type": "auto"},
                    "filterable": False,
                    "inspect": False,
                    "align": "auto",
                },
                "color": {
                    "mode": "palette-classic",
                },
            },
            "overrides": overrides,
        },
        "options": {
            "showHeader": True,
            "cellHeight": "sm",
            "footer": {"show": False, "reducer": ["sum"], "countRows": False},
            "sortBy": [],
        },
        "pluginVersion": "11.2.0",
    }


def make_row_panel(panel_id, title, y, collapsed=False):
    return {
        "id": panel_id,
        "title": title,
        "type": "row",
        "collapsed": collapsed,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "panels": [],
    }


def build_dashboard():
    panels = []
    panel_id = 1
    y = 0

    for cat_idx, (category, measurements) in enumerate(CATEGORIES):
        collapsed = cat_idx >= 5

        row = make_row_panel(panel_id, category, y, collapsed)
        panels.append(row)
        panel_id += 1
        y += 1

        table = make_table_panel(panel_id, category, measurements, 0, y)
        panels.append(table)
        panel_id += 1
        y += table["gridPos"]["h"]

    total = sum(len(m) for _, m in CATEGORIES)

    return {
        "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "11.0.0"},
            {"type": "datasource", "id": "grafana-postgresql-datasource", "name": "PostgreSQL", "version": "1.0.0"},
            {"type": "panel", "id": "table", "name": "Table", "version": ""},
        ],
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "hide": True,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations & Alerts",
                    "type": "dashboard",
                },
                {
                    "datasource": DS,
                    "enable": True,
                    "hide": False,
                    "iconColor": "#5794F2",
                    "name": "Medical Events",
                    "rawQuery": (
                        "SELECT date::timestamptz as time, end_date::timestamptz as timeend, "
                        "title as text, category || ' \u2014 ' || COALESCE(subcategory, '') || ': ' "
                        "|| COALESCE(description,'') as tags FROM events "
                        "WHERE $__timeFilter(date::timestamptz) ORDER BY date"
                    ),
                    "showIn": 0,
                    "step": "60s",
                    "type": "tags",
                },
            ]
        },
        "description": f"Compact lab results overview \u2014 {total} biomarkers with inline sparkline trends.",
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [
            {
                "icon": "dashboard",
                "title": "Health Timeline (detailed)",
                "type": "link",
                "url": "/d/health-timeline",
                "tooltip": "Open the full health timeline dashboard",
            }
        ],
        "panels": panels,
        "schemaVersion": 39,
        "tags": ["health", "lab-results"],
        "templating": {"list": []},
        "time": {"from": "now-5y", "to": "now"},
        "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "Lab Results Overview",
        "uid": "lab-results-overview",
        "version": 2,
    }


if __name__ == "__main__":
    import pathlib
    out = pathlib.Path(__file__).resolve().parent.parent / "grafana" / "dashboards" / "lab-results-overview.json"
    with open(out, "w") as f:
        json.dump(build_dashboard(), f, indent=2)
    total = sum(len(m) for _, m in CATEGORIES)
    print(f"Generated {out} with {total} measurements across {len(CATEGORIES)} categories")
