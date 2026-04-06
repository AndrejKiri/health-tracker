# Health Tracker

Personal health data pipeline: extract structured data from PDF lab reports using a self-hosted LLM, store in PostgreSQL, visualize in Grafana.

```
PDF Reports → [Ollama LLM Extraction] → [PostgreSQL] → [Grafana Dashboard]
```

## Quick Start

### Prerequisites

- Docker Desktop for Mac (with Docker Compose v2)
- ~6 GB free disk space (for Docker images + Ollama model)

### 1. Start the stack

```bash
cd health-tracker

# Create the inbox directory for PDF uploads
mkdir -p data/inbox data/processed data/failed

# Start all services
docker compose up -d
```

This starts:
- **PostgreSQL** on port 5432 (auto-creates schema + seeds sample data)
- **Ollama** on port 11434 (LLM server)
- **Grafana** on port 3000 (dashboards)
- **Extractor** service (watches `data/inbox/` for new PDFs)

### 2. Pull the LLM model

The first time, you need to pull the model into Ollama:

```bash
docker compose exec ollama ollama pull llama3.1:8b
```

This downloads ~4.7 GB. For a lighter alternative:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
```

Then update `OLLAMA_MODEL` in `docker-compose.yml` to match.

### 3. Open Grafana

Navigate to [http://localhost:3000](http://localhost:3000)

- Username: `admin`
- Password: `health`

The **Health Timeline** dashboard loads automatically with sample data (3,200+ lab results, 300+ medical events from the osteosarc.com dataset).

### 4. Process your own PDFs

Drop a PDF into the inbox:

```bash
cp your-lab-report.pdf data/inbox/
```

The watcher picks it up automatically, sends it through Ollama for extraction, and writes the structured data to PostgreSQL. Processed files move to `data/processed/`, failures to `data/failed/`.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Docker Compose                     │
│                                                       │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐│
│  │  Ollama   │◄───│Extractor │───►│   PostgreSQL     ││
│  │ (LLM)    │    │ (Python) │    │   port 5432      ││
│  │ port 11434│    │          │    │                  ││
│  └──────────┘    └─────▲────┘    └────────┬─────────┘│
│                        │                   │          │
│                  data/inbox/         ┌─────▼────────┐ │
│                  (PDF drop)          │   Grafana    │ │
│                                      │   port 3000  │ │
│                                      └──────────────┘ │
└─────────────────────────────────────────────────────┘
```

## CLI Usage

The extractor service also has a command-line interface for manual operations:

```bash
# Extract a PDF and print JSON (no database write)
docker compose exec extractor python -m extractor.cli extract /data/inbox/report.pdf

# Import a PDF directly into the database
docker compose exec extractor python -m extractor.cli import /data/inbox/report.pdf

# Process all PDFs in a directory
docker compose exec extractor python -m extractor.cli import-dir /data/inbox/

# List all processed files
docker compose exec extractor python -m extractor.cli list

# Query lab results for a specific measurement
docker compose exec extractor python -m extractor.cli query WBC

# Query with date range
docker compose exec extractor python -m extractor.cli query Hemoglobin --start-date 2024-01-01 --end-date 2024-12-31

# Seed reference ranges (already done on init, but can re-run)
docker compose exec extractor python -m extractor.cli seed
```

Add `-v` / `--verbose` to any command for debug logging.

## Data Model

### Lab Results

Each measurement extracted from a PDF:

| Field | Type | Example |
|-------|------|---------|
| date | timestamptz | 2024-06-15 |
| category | text | Complete Blood Count |
| measurement | text | WBC |
| value | double | 7.2 |
| value_text | text | not_detected |
| unit | text | x10E9/L |
| flag | text | H, L, or NULL |

### Reference Ranges

108 pre-seeded measurements across 17 categories:

- Complete Blood Count (WBC, RBC, Hemoglobin, Platelets, ...)
- Metabolic Panel (Glucose, Creatinine, Sodium, Potassium, ...)
- Liver Panel (ALT, AST, Alk Phos, Bilirubin, ...)
- Lipid Panel (Total Cholesterol, HDL, LDL, Triglycerides)
- Thyroid (TSH, Free T4, Free T3)
- Inflammatory Markers (CRP, ESR, IL-6)
- And more: Iron Studies, Vitamins, Coagulation, Blood Gas, Cardiac Markers, Lymphocyte Subsets, Endocrine

### Medical Events

Procedures, imaging, treatments, and other non-lab events:

| Field | Type | Example |
|-------|------|---------|
| date | date | 2024-01-15 |
| end_date | date | (nullable, for ranges) |
| category | text | Imaging |
| subcategory | text | MRI |
| title | text | T-spine |

## Grafana Dashboard

The pre-built dashboard includes:

- **Overview stats** — total lab results, events, flagged values
- **Medical Events Timeline** — state timeline visualization of all events
- **Complete Blood Count** — WBC, Hemoglobin, Platelets, RBC with reference range bands
- **Metabolic Panel** — Glucose, Creatinine, Sodium, Potassium
- **Liver Panel** — ALT, AST, Alk Phos, Total Bilirubin
- **Lipid Panel** — Total Cholesterol, HDL, LDL, Triglycerides
- **Inflammatory Markers** — CRP (log scale), ESR
- **Thyroid** — TSH (log scale), Free T4, Free T3
- **Dynamic View** — select any measurement from dropdowns
- **Flagged Results** — table of all out-of-range values
- **Full Data Table** — all lab results with reference ranges

Each time series panel shows green reference range bands so you can immediately see when values are outside normal.

## Configuration

All settings are environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| OLLAMA_URL | http://ollama:11434 | Ollama API endpoint |
| OLLAMA_MODEL | llama3.1:8b | Model for extraction |
| DB_HOST | postgres | PostgreSQL host |
| DB_PORT | 5432 | PostgreSQL port |
| DB_NAME | health_tracker | Database name |
| DB_USER | health | Database user |
| DB_PASSWORD | health | Database password |
| WATCH_DIR | /data/inbox | Directory to watch for PDFs |
| PROCESSED_DIR | /data/processed | Where processed PDFs go |
| FAILED_DIR | /data/failed | Where failed PDFs go |

## Using a Different LLM

To use a different model:

```bash
# Pull a different model
docker compose exec ollama ollama pull mistral

# Update docker-compose.yml
# Change OLLAMA_MODEL: mistral
docker compose restart extractor
```

Tested models: `llama3.1:8b`, `qwen2.5:7b`, `mistral`. Larger models (13B+) give better extraction quality but need more RAM.

## Adding Custom Reference Ranges

Edit `reference_ranges.json` and re-seed:

```bash
docker compose exec extractor python -m extractor.cli seed
```

Or insert directly via SQL:

```sql
INSERT INTO reference_ranges (measurement, category, unit, reference_low, reference_high, scale)
VALUES ('My Custom Test', 'Custom', 'units', 10, 50, 'linear')
ON CONFLICT (measurement) DO UPDATE SET
  reference_low = EXCLUDED.reference_low,
  reference_high = EXCLUDED.reference_high;
```

## Sample Data

The stack comes pre-seeded with data from the [osteosarc.com](https://osteosarc.com/timeline/) project:

- 3,257 lab results across 170 measurements
- 311 medical events (imaging, procedures, treatments)
- 36 MRD (minimal residual disease) measurements

This gives you a fully populated dashboard to explore immediately.

Three sample PDFs in `tests/sample_pdfs/` can be used to test the extraction pipeline:
- `complete_blood_count_2024.pdf` — CBC panel
- `metabolic_panel_2024.pdf` — Comprehensive metabolic panel (includes a flagged glucose)
- `thyroid_lipid_2024.pdf` — Thyroid + lipid + vitamins

## Stopping and Cleanup

```bash
# Stop all services (data persists)
docker compose down

# Stop and remove all data (fresh start)
docker compose down -v
```

## Project Structure

```
health-tracker/
├── docker-compose.yml          # Full stack: Postgres + Ollama + Grafana + Extractor
├── README.md
├── reference_ranges.json       # 108 measurement reference ranges
├── db/
│   ├── init.sql                # Schema + reference range seeds
│   └── seed_sample_data.sql    # 3,600+ sample records
├── extractor/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── __init__.py
│   ├── config.py               # Environment-based configuration
│   ├── schema.py               # Pydantic v2 data models
│   ├── pdf_parser.py           # PDF text extraction (pymupdf + OCR fallback)
│   ├── prompts.py              # LLM prompt templates with measurement catalog
│   ├── llm_client.py           # Async Ollama client with retry logic
│   ├── db.py                   # PostgreSQL operations
│   ├── cli.py                  # Command-line interface
│   └── watcher.py              # Filesystem watcher for auto-processing
├── grafana/
│   ├── dashboards/
│   │   └── health-timeline.json  # Pre-built dashboard (40 panels)
│   └── provisioning/
│       ├── dashboards/
│       │   └── dashboard.yml
│       └── datasources/
│           └── datasource.yml
├── tests/
│   ├── generate_sample_pdfs.py
│   └── sample_pdfs/
│       ├── complete_blood_count_2024.pdf
│       ├── metabolic_panel_2024.pdf
│       └── thyroid_lipid_2024.pdf
└── data/                       # Created at runtime
    ├── inbox/                  # Drop PDFs here
    ├── processed/              # Successfully processed
    └── failed/                 # Failed extractions
```
