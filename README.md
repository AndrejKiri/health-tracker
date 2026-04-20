# Health Tracker

Personal health data pipeline: extract structured data from PDF lab reports using a self-hosted LLM, store in PostgreSQL, visualize in Grafana.

```
PDF Reports → [Ollama LLM Extraction] → [PostgreSQL] → [Grafana Dashboard]
```

## Quick Start — Native macOS (recommended)

Runs everything locally with Apple Silicon Metal GPU acceleration. No Docker required.

### Prerequisites

```bash
brew install ollama poppler postgresql@16 grafana
# tesseract is also required (brew install tesseract if not present)
```

### Setup (one-time)

```bash
# 1. Clone and enter the project
cd health-tracker

# 2. Create inbox directories
mkdir -p data/inbox data/processed data/failed

# 3. Configure credentials
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD and GRAFANA_ADMIN_PASSWORD

# 4. Install Python dependencies
make install-deps

# 5. Start PostgreSQL and initialize the database
make db-start
make db-init        # creates user, database, schema, and seeds reference ranges

# 6. Pull the LLM model
make ollama-start
make pull-model     # downloads ~1 GB (qwen2.5:1.5b default; edit OLLAMA_MODEL in .env)
```

### Daily use

```bash
make start          # starts PostgreSQL + Ollama + Grafana
                    # Grafana → http://localhost:3001

make watch          # start the PDF watcher in a separate terminal
                    # drop PDFs into data/inbox/ to process them

make stop           # shut everything down when done
```

**Verify Metal GPU is active:**
```bash
make status         # PROCESSOR column should show "100% GPU"
```

**On M-series Macs, extraction takes 5–30 seconds per PDF** (vs. minutes on CPU).

Nothing starts at login — `make start` / `make stop` are the on/off switch.

---

## Quick Start — Full Docker (alternative)

Runs all four services in containers. No native tooling required, but inference is CPU-only (no Metal acceleration).

### Prerequisites

- OrbStack or Docker Desktop with Docker Compose v2
- ~6 GB free disk space

```bash
cd health-tracker
mkdir -p data/inbox data/processed data/failed
cp .env.example .env
# Edit .env — remove the "Native macOS settings" block before starting

docker compose up -d

# Pull the LLM model (first time only)
docker compose exec ollama ollama pull llama3.1:8b   # ~4.7 GB

# Open Grafana at http://localhost:3001
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Native macOS (primary)                   │
│                                                       │
│  Ollama (Metal GPU)   Extractor (.venv)               │
│  localhost:11434  ◄───  python -m extractor.cli       │
│                              │                        │
│                    data/inbox/ (PDF drop)             │
│                              │                        │
│                       PostgreSQL                      │
│                       localhost:5432                  │
│                              │                        │
│                          Grafana                      │
│                       localhost:3001                  │
└─────────────────────────────────────────────────────┘
```

---

## Makefile Reference

```
make help           # list all targets

# Services
make start          # start DB + Ollama + Grafana
make stop           # stop all services
make db-start       # start PostgreSQL only
make ollama-start   # start Ollama only
make grafana-start  # start Grafana only (http://localhost:3001)
make status         # show Ollama GPU usage

# Setup
make install-deps   # create .venv and install Python dependencies
make db-init        # create DB user/schema/seed (run once after db-start)
make pull-model     # pull OLLAMA_MODEL from .env into native Ollama
make check-deps     # verify all required system tools are installed

# Extractor
make watch          # start PDF inbox watcher
make extract PDF=path/to/report.pdf   # single extraction, print JSON
make seed           # re-seed reference ranges
make list           # list all processed files
```

---

## CLI Usage

```bash
# Extract a PDF and print JSON (no database write)
make extract PDF=tests/sample_pdfs/complete_blood_count_2024.pdf

# Import directly into the database
.venv/bin/python -m extractor.cli import path/to/report.pdf

# Query lab results for a measurement
.venv/bin/python -m extractor.cli query WBC
.venv/bin/python -m extractor.cli query Hemoglobin --start-date 2024-01-01

# List processed files
make list
```

Add `-v` / `--verbose` to any command for debug logging.

---

## Configuration

All settings are environment variables. Copy `.env.example` to `.env` and edit.

| Variable | Native default | Docker default | Description |
|----------|---------------|----------------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | `http://ollama:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | `llama3.1:8b` | Model for extraction |
| `POSTGRES_HOST` | `localhost` | `postgres` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `health_tracker` | same | Database name |
| `POSTGRES_USER` | `health` | same | Database user |
| `POSTGRES_PASSWORD` | — | — | Database password (required) |
| `DB_INIT_SQL_PATH` | `./db/init.sql` | `/app/db/init.sql` | Schema init script path |
| `WATCH_DIR` | `./data/inbox` | `/data/inbox` | PDF inbox directory |
| `PROCESSED_DIR` | `./data/processed` | `/data/processed` | Successful extractions |
| `FAILED_DIR` | `./data/failed` | `/data/failed` | Failed extractions |

---

## Using a Different LLM

Edit `OLLAMA_MODEL` in `.env`, then:

```bash
make pull-model
```

Tested models: `qwen2.5:1.5b` (fast, default), `llama3.1:8b`, `qwen2.5:7b`, `mistral`. Larger models give better extraction quality but need more unified memory.

---

## Data Model

### Lab Results

| Field | Type | Example |
|-------|------|---------|
| date | timestamptz | 2024-06-15 |
| category | text | Complete Blood Count |
| measurement | text | WBC |
| value | double | 7.2 |
| unit | text | x10E9/L |
| flag | text | H, L, or NULL |

### Reference Ranges

108 pre-seeded measurements across 17 categories: Complete Blood Count, Metabolic Panel, Liver Panel, Lipid Panel, Thyroid, Inflammatory Markers, Iron Studies, Vitamins, Coagulation, Blood Gas, Cardiac Markers, Lymphocyte Subsets, Endocrine.

### Medical Events

Procedures, imaging, treatments, and other non-lab events (date, category, subcategory, title).

---

## Grafana Dashboard

Pre-built dashboard at http://localhost:3001 includes:

- **Overview stats** — total lab results, events, flagged values
- **Medical Events Timeline** — state timeline of all events
- **CBC, Metabolic, Liver, Lipid, Thyroid, Inflammatory Markers** panels
- **Dynamic View** — select any measurement from dropdowns
- **Flagged Results** and **Full Data Table**

Each time series panel shows green reference range bands.

---

## Adding Custom Reference Ranges

Edit `reference_ranges.json` and re-seed:

```bash
make seed
```

---

## Sample Data

Three sample PDFs in `tests/sample_pdfs/` for testing the extraction pipeline:
- `complete_blood_count_2024.pdf`
- `metabolic_panel_2024.pdf`
- `thyroid_lipid_2024.pdf`

The repository does not include personal lab data. The database starts empty aside from schema and reference range seeding.

---

## Project Structure

```
health-tracker/
├── Makefile                    # Native macOS workflow targets
├── docker-compose.yml          # Full Docker alternative (all 4 services)
├── .env.example                # Configuration template
├── reference_ranges.json       # 108 measurement reference ranges
├── db/
│   ├── init.sql                # Schema + reference range seeds
│   └── migrations/             # Schema migrations
├── extractor/
│   ├── Dockerfile              # For optional full-Docker deployment
│   ├── requirements.txt
│   ├── config.py               # Environment-based configuration
│   ├── schema.py               # Pydantic v2 data models
│   ├── pdf_parser.py           # PDF text extraction (pymupdf + OCR fallback)
│   ├── prompts.py              # LLM prompt templates
│   ├── llm_client.py           # Async Ollama client with retry logic
│   ├── db.py                   # PostgreSQL operations
│   ├── cli.py                  # Command-line interface
│   └── watcher.py              # Filesystem watcher
├── grafana/
│   ├── dashboards/
│   │   └── health-timeline.json
│   └── provisioning/
│       ├── dashboards/dashboard.yml
│       └── datasources/datasource.yml
├── scripts/
│   └── run-grafana.sh          # Native Grafana launcher
├── tests/
│   └── sample_pdfs/
└── data/                       # Created at runtime
    ├── inbox/
    ├── processed/
    └── failed/
```
