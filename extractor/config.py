"""
Configuration module for the health data extraction service.
All settings are driven by environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Immutable application configuration loaded from environment variables."""

    # Ollama LLM settings
    ollama_url: str
    ollama_model: str

    # PostgreSQL database settings
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    # Directory watch/processing settings
    watch_dir: str
    processed_dir: str
    failed_dir: str



def load_config() -> Config:
    """
    Load configuration from environment variables.
    Falls back to sensible defaults for local/Docker Compose development.
    Calls load_dotenv() so a .env file in the working directory is
    respected when running the extractor outside of Docker Compose.
    """
    load_dotenv()  # no-op if .env does not exist
    return Config(
        # Ollama
        ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.1:8b"),
        # Database
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_name=os.environ.get("DB_NAME", "health_tracker"),
        db_user=os.environ.get("DB_USER", "health"),
        db_password=os.environ.get("DB_PASSWORD", "health"),
        # Directories
        watch_dir=os.environ.get("WATCH_DIR", "./data/inbox"),
        processed_dir=os.environ.get("PROCESSED_DIR", "./data/processed"),
        failed_dir=os.environ.get("FAILED_DIR", "./data/failed"),
    )


# Module-level singleton — import this everywhere
config: Config = load_config()
