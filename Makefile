.DEFAULT_GOAL := help
SHELL         := /bin/bash

VENV_DIR    ?= .venv
VENV_PYTHON  = $(VENV_DIR)/bin/python

# Load OLLAMA_MODEL from .env if it exists
-include .env
export

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)

# ── Dependencies ──────────────────────────────────────────────────────────────

.PHONY: check-deps
check-deps: ## Verify required system tools are installed
	@missing=0; \
	for cmd in ollama tesseract pdftoppm psql grafana; do \
	    if ! command -v $$cmd &>/dev/null; then \
	        echo "  MISSING: $$cmd"; missing=1; \
	    fi; \
	done; \
	if [ $$missing -eq 1 ]; then \
	    echo ""; \
	    echo "Install missing tools: brew install ollama tesseract poppler postgresql@16 grafana"; \
	    exit 1; \
	else \
	    echo "All dependencies found."; \
	fi

.PHONY: venv
venv: ## Create Python virtual environment
	@[[ -d $(VENV_DIR) ]] || python3 -m venv $(VENV_DIR)

.PHONY: install-deps
install-deps: venv ## Install Python dependencies into .venv
	$(VENV_DIR)/bin/pip install -q --upgrade pip
	$(VENV_DIR)/bin/pip install -q -r extractor/requirements.txt

# ── Database ──────────────────────────────────────────────────────────────────

.PHONY: db-start
db-start: ## Start PostgreSQL (no auto-login; use 'brew services start' to persist)
	brew services run postgresql@16

.PHONY: db-stop
db-stop: ## Stop PostgreSQL
	brew services stop postgresql@16

.PHONY: db-init
db-init: ## Create DB user, create database, run schema, seed reference ranges
	@if [[ ! -f .env ]]; then echo "ERROR: .env not found — copy .env.example first." && exit 1; fi
	@source .env && \
	    psql -U $$USER -d postgres -c "CREATE USER $$POSTGRES_USER WITH PASSWORD '$$POSTGRES_PASSWORD';" 2>/dev/null || true && \
	    createdb -U $$USER -O $$POSTGRES_USER $$POSTGRES_DB 2>/dev/null || true && \
	    psql -U $$POSTGRES_USER -d $$POSTGRES_DB -f db/init.sql && \
	    echo "Schema applied." && \
	    $(VENV_PYTHON) -m extractor.cli seed && \
	    echo "Reference ranges seeded."

# ── Ollama ────────────────────────────────────────────────────────────────────

.PHONY: ollama-start
ollama-start: ## Start Ollama (no auto-login; Metal GPU detected automatically)
	brew services run ollama

.PHONY: ollama-stop
ollama-stop: ## Stop Ollama
	brew services stop ollama

.PHONY: pull-model
pull-model: ## Pull the configured OLLAMA_MODEL into native Ollama
	@if [[ -z "$(OLLAMA_MODEL)" ]]; then echo "ERROR: OLLAMA_MODEL not set in .env" && exit 1; fi
	ollama pull $(OLLAMA_MODEL)

.PHONY: status
status: ## Show Ollama status and loaded models (PROCESSOR shows GPU usage)
	ollama ps

# ── Grafana ───────────────────────────────────────────────────────────────────

.PHONY: grafana-start
grafana-start: ## Start native Grafana on :3001 (background, logs → /tmp/grafana.log)
	@scripts/run-grafana.sh &>/tmp/grafana.log & disown && \
	    echo "Grafana starting — http://localhost:3001 (logs: /tmp/grafana.log)"

.PHONY: grafana-stop
grafana-stop: ## Stop native Grafana
	@pkill -f "grafana server" && echo "Grafana stopped." || echo "Grafana was not running."

# ── Extractor ─────────────────────────────────────────────────────────────────

.PHONY: watch
watch: ## Start the PDF inbox watcher
	$(VENV_PYTHON) -m extractor.cli watch

.PHONY: extract
extract: ## Extract a single PDF: make extract PDF=path/to/file.pdf
	@if [[ -z "$(PDF)" ]]; then echo "Usage: make extract PDF=path/to/file.pdf" && exit 1; fi
	$(VENV_PYTHON) -m extractor.cli extract $(PDF)

.PHONY: seed
seed: ## Seed reference ranges from reference_ranges.json
	$(VENV_PYTHON) -m extractor.cli seed

.PHONY: list
list: ## List all processed files
	$(VENV_PYTHON) -m extractor.cli list

# ── Lifecycle ─────────────────────────────────────────────────────────────────

.PHONY: start
start: db-start ollama-start grafana-start ## Start all services (DB + Ollama + Grafana)
	@echo ""
	@echo "Services started. Run 'make watch' in a separate terminal to process PDFs."
	@echo "Grafana: http://localhost:3001"

.PHONY: stop
stop: grafana-stop ollama-stop db-stop ## Stop all services
