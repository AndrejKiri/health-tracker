# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Component showcase dashboard with reusable `make_timeseries_panel()` and `make_showcase_dashboard()` generators — currently demoing Lipid Panel data (sparkline table + timeseries)

### In Progress / Planned
- Expanding the component showcase to additional categories beyond Lipid Panel
- The README still references Grafana on port 3000, but it was remapped to 3001 — needs updating
- The README project structure section is outdated (missing `scripts/`, `db/migrations/`, new dashboards)

## [0.1.3] - 2026-04-15

Database schema evolution and new Grafana lab dashboards.

### Added
- Prometheus-inspired 4-table data model (`documents`, `metrics`, `reference_ranges`, `samples`) replacing the flat `lab_results` table
- `description` column on `metrics` table with clinical explanations for all 108 metrics (migration `003_metric_descriptions.sql`)
- Lab results overview dashboard with SQL-based sparkline arrays (per-category tables, 106 metrics across 17 categories)
- Lab metric detail dashboard with full timeseries, reference range lines (orange dashed=low, red dashed=high), and metric description
- Status column (H/L/OK) with colour coding (red/orange/green) computed from last value vs reference range
- Last Tested date column in overview table
- Clickable metric names linking to the detail dashboard
- 1-year fixed sparkline window independent of dashboard time picker
- Truncated description preview column replacing numeric Ref Low/High
- `gen_lab_dashboard.py` — Python-based dashboard JSON generator
- `convert_seed_data.py` — legacy seed data converter for the new schema
- Debug sparkline dashboard for testing rendering approaches

### Fixed
- Two broken template variables: metric variable used Prometheus-style nested object instead of plain SQL; category/measurement variables queried old table instead of `metrics`
- `timeSeriesTable` transformation does not work with PostgreSQL data in Grafana 11.2.0 — replaced with SQL `array_agg()` sparkline approach
- Grafana remapped to port 3001 to avoid local conflicts
- `backup.sh` — replaced `mapfile` (bash 4+) with POSIX-compatible read loop for macOS compatibility

## [0.1.2] - 2026-04-15

Second hardening pass. Delivered via PRs #14–#15.

### Added
- Backup script (`scripts/backup.sh`) with `--keep N` rotation flag (default: 7)
- Migration conventions documentation (`db/migrations/README.md`)

### Fixed
- `str.format()` on untrusted PDF text replaced to prevent injection
- Grafana datasource fully parameterised (`POSTGRES_DB` variable)
- Extractor memory cap added
- CK added to sex-specific reference ranges documentation
- LLM prompt example 3 fixed to include Glucose (Urine) — was teaching the model to skip qualitative results

## [0.1.1] - 2026-04-15

First hardening pass across security, infrastructure, and data quality. Delivered via PRs #1–#13.

### Added
- Backup script (`scripts/backup.sh`) with `--keep N` rotation flag (default: 7)
- Migration conventions documentation (`db/migrations/README.md`)
- Cross-check of LLM-extracted flags against stored reference ranges
- Documentation of sex-specific reference ranges and eGFR limitations
- `MedicalEvent.category` enforced as a `Literal` enum in Pydantic schema

### Changed
- Ollama memory limit raised to 6 GB for `llama3.1:8b`
- Extractor container runs as non-root user
- Watcher uses bounded `ThreadPoolExecutor` instead of unbounded thread-per-file
- All credentials moved to `.env` (no more hardcoded secrets in compose/config)
- Grafana datasource fully parameterised (`POSTGRES_DB` variable)
- Container memory caps added for all services including extractor
- Healthcheck hardened across all services
- Ollama healthcheck added; extractor waits for it before starting

### Fixed
- Grafana datasource type aligned with Grafana 11+ plugin ID
- `reference_ranges.json` not accessible inside container
- Grafana and Ollama images pinned to specific versions
- `datetime.utcnow()` replaced with timezone-aware call (deprecated in Python 3.12+)
- Unique constraint added on `lab_results` with correct `ON CONFLICT` target
- DATE columns cast to `timestamptz` in Grafana annotation query
- Unused `argparse` removed from `requirements.txt`
- Dead `__inputs` block and wrong `__requires` plugin ID removed from dashboard JSON
- OCR page mapping corrected for non-contiguous image-only pages
- `load_dotenv()` actually called so `.env` is loaded
- `execute_batch` rowcount limitation documented
- `str.format()` on untrusted PDF text replaced to prevent injection
- CK added to sex-specific reference ranges documentation
- LLM prompt example 3 fixed to include Glucose (Urine) — was teaching the model to skip qualitative results

### Security
- Docker network isolation between services
- Database password removed from exception messages
- `.dockerignore` added to extractor
- Host port exposure removed for internal-only services

## [0.1.0] - 2026-04-06

Initial release.

### Added
- Docker Compose stack: PostgreSQL, Ollama, Grafana, Extractor
- PDF text extraction via PyMuPDF with OCR fallback (pdf2image + Tesseract)
- LLM-based structured data extraction using Ollama (llama3.1:8b / qwen2.5:7b)
- Pydantic v2 schema for lab results and medical events
- PostgreSQL schema with lab_results and medical_events tables
- 108 pre-seeded reference ranges across 17 categories
- Filesystem watcher for automatic PDF processing (inbox/processed/failed)
- CLI for manual extraction, import, query, and seeding
- Health Timeline Grafana dashboard (40 panels) with reference range bands
- Sample test PDFs (CBC, metabolic panel, thyroid/lipid)

## Top 5 Suggested Additions

1. **Automated test suite** — no unit or integration tests exist yet; the extraction pipeline, DB operations, and reference range cross-checks are all untested beyond manual verification
2. **Multi-user / sex-aware reference ranges** — the schema supports it (`reference_ranges` has `sex` and `age_min`/`age_max`), but the extractor and dashboards ignore sex-specific ranges, leading to silent misflags for female patients
3. **Alerting rules** — Grafana alert rules for newly flagged values (e.g., notify when a freshly extracted result is out of range)
4. **Trend analysis / rate-of-change tracking** — detect not just out-of-range values but concerning trends (e.g., steadily rising creatinine even if still within range)
5. **PDF report provenance and audit trail** — link each sample back to its source document with extraction confidence scores, so you can trace and re-verify any suspicious value
