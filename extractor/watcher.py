"""
File watcher for the health data extraction service.

Monitors WATCH_DIR for newly-created or moved-in PDF files and automatically
processes them through the extraction pipeline.

Behaviour
---------
- Uses watchdog's ``Observer`` to monitor the inbox directory.
- On a new .pdf file event: waits 2 seconds (in case the file is still being
  copied), then submits the file to a bounded thread-pool executor.
- At most MAX_WORKERS extractions run concurrently; additional files queue up
  rather than spawning unbounded threads that would overwhelm Ollama.
- Successfully processed files are moved to PROCESSED_DIR.
- Files that fail extraction are moved to FAILED_DIR.
- Handles SIGTERM and SIGINT for graceful shutdown.
- Skips files that have already been processed (by filename hash).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler  # type: ignore[import]
from watchdog.observers import Observer  # type: ignore[import]

from .config import config

logger = logging.getLogger(__name__)

# Delay after a file-creation event before processing starts (seconds).
# Gives in-progress copy operations time to finish.
_COPY_SETTLE_SECONDS = 2.0

# Maximum number of PDFs processed concurrently. Ollama is single-threaded;
# more than a handful of concurrent requests just queue up inside Ollama and
# risk hitting the 120s per-request timeout.
_MAX_WORKERS = 3

# Module-level executor shared across all watchdog events and the pre-scan.
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="extractor")


# ---------------------------------------------------------------------------
# Helper: ensure output directories exist
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
    for d in (config.watch_dir, config.processed_dir, config.failed_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
        logger.debug("Ensured directory exists: '%s'", d)


# ---------------------------------------------------------------------------
# Processing logic (runs inside the thread pool)
# ---------------------------------------------------------------------------


def _process_file(pdf_path: str) -> None:
    """
    Run the full extraction pipeline on a single PDF file.

    On success: move to PROCESSED_DIR.
    On failure: move to FAILED_DIR and log the error.
    """
    # Lazy imports to avoid circular dependency at module level
    from .db import check_flags_against_references, insert_events, insert_lab_results, is_processed, log_processing
    from .llm_client import extract_from_text
    from .pdf_parser import extract_text
    from .schema import LabResult, MedicalEvent

    filename = Path(pdf_path).name

    # Skip already-processed files
    if is_processed(filename):
        logger.info("'%s' already processed — skipping.", filename)
        return

    logger.info("Processing '%s'…", pdf_path)

    try:
        # --- Extract text ---------------------------------------------------
        text = extract_text(pdf_path)
        if not text.strip():
            logger.warning("No text extracted from '%s'.", pdf_path)

        # --- LLM extraction (sync wrapper around async) --------------------
        result = asyncio.run(extract_from_text(text))

        # --- Validate and insert -------------------------------------------
        lab_results = [LabResult.model_validate(r) for r in result["lab_results"]]
        events = [MedicalEvent.model_validate(e) for e in result["events"]]

        check_flags_against_references(lab_results)
        insert_lab_results(lab_results, filename)
        insert_events(events, filename)
        log_processing(filename, "success")

        logger.info(
            "Processed '%s': %d lab result(s), %d event(s).",
            filename, len(lab_results), len(events),
        )

        # --- Move to processed --------------------------------------------
        dest = Path(config.processed_dir) / filename
        shutil.move(pdf_path, str(dest))
        logger.info("Moved '%s' → '%s'.", pdf_path, dest)

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process '%s': %s", pdf_path, exc, exc_info=True)
        log_processing(filename, "failed", str(exc))

        # Move to failed dir
        try:
            dest = Path(config.failed_dir) / filename
            shutil.move(pdf_path, str(dest))
            logger.info("Moved failed file '%s' → '%s'.", pdf_path, dest)
        except Exception as move_exc:  # noqa: BLE001
            logger.error(
                "Could not move failed file '%s': %s", pdf_path, move_exc
            )


# ---------------------------------------------------------------------------
# Watchdog event handler
# ---------------------------------------------------------------------------


class _PDFEventHandler(FileSystemEventHandler):
    """React to new PDF files appearing in the watched directory."""

    def __init__(self, stop_event: Event) -> None:
        super().__init__()
        self._stop_event = stop_event

    def _is_pdf(self, path: str) -> bool:
        return path.lower().endswith(".pdf")

    def _handle(self, path: str) -> None:
        """Submit PDF processing to the bounded thread pool."""
        if not self._is_pdf(path):
            return

        logger.info("New PDF detected: '%s'", path)

        def _delayed_process() -> None:
            # Wait for the copy to settle
            time.sleep(_COPY_SETTLE_SECONDS)

            # Confirm the file still exists after the delay
            if not Path(path).exists():
                logger.warning(
                    "File disappeared before processing: '%s'", path
                )
                return

            _process_file(path)

        _executor.submit(_delayed_process)

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(event.dest_path)


# ---------------------------------------------------------------------------
# Scan existing files on startup
# ---------------------------------------------------------------------------


def _scan_existing(stop_event: Event) -> None:
    """Submit any PDFs already present in WATCH_DIR to the thread pool."""
    inbox = Path(config.watch_dir)
    pdfs = list(inbox.glob("*.pdf")) + list(inbox.glob("*.PDF"))
    if pdfs:
        logger.info(
            "Found %d existing PDF(s) in '%s' — submitting to processor…",
            len(pdfs), inbox,
        )
        for pdf in pdfs:
            if stop_event.is_set():
                break
            _executor.submit(_process_file, str(pdf))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def start_watcher() -> None:
    """
    Start the file watcher and block until a shutdown signal is received.

    Handles SIGTERM and SIGINT gracefully:
    - Stops the watchdog Observer.
    - Shuts down the thread pool executor (waits for in-flight extractions
      to finish before exiting).
    """
    _ensure_dirs()

    stop_event = Event()

    def _shutdown(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.info(
            "Received signal %d — shutting down watcher…", signum
        )
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Submit any files already in the inbox without blocking the main loop
    pre_scan_thread = Thread(
        target=_scan_existing,
        args=(stop_event,),
        daemon=True,
        name="pre-scan",
    )
    pre_scan_thread.start()

    event_handler = _PDFEventHandler(stop_event)
    observer = Observer()
    observer.schedule(event_handler, path=config.watch_dir, recursive=False)
    observer.start()

    logger.info(
        "Watching '%s' for new PDF files (max %d concurrent, processed→'%s', failed→'%s').",
        config.watch_dir,
        _MAX_WORKERS,
        config.processed_dir,
        config.failed_dir,
    )

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        logger.info("Stopping observer and waiting for in-flight extractions…")
        observer.stop()
        observer.join(timeout=10)
        _executor.shutdown(wait=True)
        logger.info("Watcher stopped.")
