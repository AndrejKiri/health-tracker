"""
Command-line interface for the health data extraction service.

Usage
-----
    python -m extractor.cli extract   <pdf_path>       # Print JSON, no DB write
    python -m extractor.cli import    <pdf_path>       # Extract → DB
    python -m extractor.cli import-dir <dir_path>      # Process all PDFs in dir
    python -m extractor.cli watch                      # Watch WATCH_DIR
    python -m extractor.cli seed                       # Seed reference ranges
    python -m extractor.cli list                       # List processed files
    python -m extractor.cli query <measurement>        # Query lab results

All subcommands accept ``--verbose`` for DEBUG-level logging.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Shared extraction helper
# ---------------------------------------------------------------------------


async def _run_extraction(pdf_path: str) -> dict:
    """
    Extract text from ``pdf_path`` and call the LLM.

    Returns the validated extraction result dict.
    """
    from .llm_client import extract_from_text
    from .pdf_parser import extract_text

    logger.info("Extracting text from '%s'…", pdf_path)
    text = extract_text(pdf_path)
    if not text.strip():
        logger.warning("No text extracted from '%s'.", pdf_path)

    logger.info("Sending text to LLM (length=%d chars)…", len(text))
    result = await extract_from_text(text)
    result["source_file"] = Path(pdf_path).name
    result["extracted_at"] = datetime.utcnow().isoformat()
    return result


# ---------------------------------------------------------------------------
# Command: extract
# ---------------------------------------------------------------------------


async def _cmd_extract(args: argparse.Namespace) -> None:
    """Extract a PDF and print structured JSON to stdout (no DB write)."""
    pdf_path = args.pdf_path
    if not Path(pdf_path).exists():
        logger.error("File not found: '%s'", pdf_path)
        sys.exit(1)

    result = await _run_extraction(pdf_path)
    # Remove internal-only keys before printing
    output = {
        "source_file": result["source_file"],
        "extracted_at": result["extracted_at"],
        "lab_results": result["lab_results"],
        "events": result["events"],
    }
    if result.get("errors"):
        output["validation_errors"] = result["errors"]

    print(json.dumps(output, indent=2, default=str))


# ---------------------------------------------------------------------------
# Command: import
# ---------------------------------------------------------------------------


async def _cmd_import(args: argparse.Namespace) -> None:
    """Extract a PDF and write results to the database."""
    from .db import insert_events, insert_lab_results, is_processed, log_processing
    from .schema import LabResult, MedicalEvent

    pdf_path = args.pdf_path
    filename = Path(pdf_path).name

    if not Path(pdf_path).exists():
        logger.error("File not found: '%s'", pdf_path)
        sys.exit(1)

    if is_processed(filename):
        logger.info("'%s' has already been processed — skipping.", filename)
        return

    try:
        result = await _run_extraction(pdf_path)

        # Reconstruct Pydantic objects from validated dicts
        lab_results = [LabResult.model_validate(r) for r in result["lab_results"]]
        events = [MedicalEvent.model_validate(e) for e in result["events"]]

        insert_lab_results(lab_results, filename)
        insert_events(events, filename)
        log_processing(filename, "success")

        logger.info(
            "Imported '%s': %d lab results, %d events.",
            filename, len(lab_results), len(events),
        )

        if args.verbose and result.get("errors"):
            logger.debug("Validation errors during extraction: %s", result["errors"])

    except Exception as exc:  # noqa: BLE001
        logger.error("Import failed for '%s': %s", pdf_path, exc)
        log_processing(filename, "failed", str(exc))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Command: import-dir
# ---------------------------------------------------------------------------


async def _cmd_import_dir(args: argparse.Namespace) -> None:
    """Process all PDF files in a directory sequentially."""
    dir_path = Path(args.dir_path)
    if not dir_path.is_dir():
        logger.error("Not a directory: '%s'", dir_path)
        sys.exit(1)

    pdfs = sorted(dir_path.glob("*.pdf")) + sorted(dir_path.glob("*.PDF"))
    if not pdfs:
        logger.info("No PDF files found in '%s'.", dir_path)
        return

    logger.info("Found %d PDF(s) in '%s'.", len(pdfs), dir_path)
    for pdf in pdfs:
        # Reuse import command logic with a synthetic args object
        import_args = argparse.Namespace(pdf_path=str(pdf), verbose=args.verbose)
        await _cmd_import(import_args)


# ---------------------------------------------------------------------------
# Command: watch
# ---------------------------------------------------------------------------


def _cmd_watch(args: argparse.Namespace) -> None:
    """Start the file watcher on WATCH_DIR (blocking)."""
    from .watcher import start_watcher

    logger.info("Starting file watcher…")
    start_watcher()


# ---------------------------------------------------------------------------
# Command: seed
# ---------------------------------------------------------------------------


def _cmd_seed(args: argparse.Namespace) -> None:
    """Seed reference ranges from reference_ranges.json into the database."""
    import json as _json

    from .db import init_db, seed_reference_ranges

    # The canonical path for the reference file inside the container
    candidates = [
        Path("/app/reference_ranges.json"),
        Path("/app/extractor/reference_ranges.json"),
        Path("reference_ranges.json"),
    ]

    ref_path: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            ref_path = candidate
            break

    if ref_path is None:
        logger.error(
            "reference_ranges.json not found in any known location."
        )
        sys.exit(1)

    init_db()
    ranges = _json.loads(ref_path.read_text(encoding="utf-8"))
    count = seed_reference_ranges(ranges)
    logger.info("Seeded %d reference range(s) from '%s'.", count, ref_path)


# ---------------------------------------------------------------------------
# Command: list
# ---------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> None:
    """List all processed files from the database."""
    from .db import list_processed_files

    rows = list_processed_files()
    if not rows:
        print("No processed files found.")
        return

    print(f"{'Filename':<50} {'Status':<12} {'Processed At'}")
    print("-" * 85)
    for row in rows:
        processed_at = row.get("processed_at", "")
        if hasattr(processed_at, "isoformat"):
            processed_at = processed_at.isoformat()
        print(f"{row['filename']:<50} {row['status']:<12} {processed_at}")
        if row.get("error_message"):
            print(f"  ERROR: {row['error_message']}")


# ---------------------------------------------------------------------------
# Command: query
# ---------------------------------------------------------------------------


def _cmd_query(args: argparse.Namespace) -> None:
    """Query lab results for a specific measurement."""
    from .db import get_lab_results

    rows = get_lab_results(
        measurement=args.measurement,
        start_date=getattr(args, "start_date", None),
        end_date=getattr(args, "end_date", None),
    )
    if not rows:
        print(f"No results found for measurement='{args.measurement}'.")
        return

    print(
        f"{'Date':<12} {'Measurement':<30} {'Value':>10} {'Unit':<15} {'Flag':<5} "
        f"{'Category'}"
    )
    print("-" * 100)
    for r in rows:
        value = r["value"] if r["value"] is not None else r.get("value_text", "")
        flag = r.get("flag") or ""
        print(
            f"{str(r['date']):<12} {r['measurement']:<30} {str(value):>10} "
            f"{r['unit']:<15} {flag:<5} {r['category']}"
        )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m extractor.cli",
        description="Health data extraction service CLI",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # extract
    p_extract = sub.add_parser("extract", help="Extract PDF, print JSON (no DB)")
    p_extract.add_argument("pdf_path", help="Path to the PDF file")

    # import
    p_import = sub.add_parser("import", help="Extract PDF and write to database")
    p_import.add_argument("pdf_path", help="Path to the PDF file")

    # import-dir
    p_import_dir = sub.add_parser(
        "import-dir", help="Process all PDFs in a directory"
    )
    p_import_dir.add_argument("dir_path", help="Directory containing PDF files")

    # watch
    sub.add_parser("watch", help="Watch WATCH_DIR for new PDFs")

    # seed
    sub.add_parser("seed", help="Seed reference ranges into the database")

    # list
    sub.add_parser("list", help="List all processed files")

    # query
    p_query = sub.add_parser("query", help="Query lab results for a measurement")
    p_query.add_argument("measurement", help="Measurement name to query")
    p_query.add_argument("--start-date", dest="start_date", default=None,
                         help="Filter from date (YYYY-MM-DD)")
    p_query.add_argument("--end-date", dest="end_date", default=None,
                         help="Filter to date (YYYY-MM-DD)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)

    # Async commands
    async_commands = {"extract", "import", "import-dir"}
    sync_commands = {"watch", "seed", "list", "query"}

    if args.command in async_commands:
        dispatch = {
            "extract": _cmd_extract,
            "import": _cmd_import,
            "import-dir": _cmd_import_dir,
        }
        asyncio.run(dispatch[args.command](args))

    elif args.command in sync_commands:
        dispatch_sync = {
            "watch": _cmd_watch,
            "seed": _cmd_seed,
            "list": _cmd_list,
            "query": _cmd_query,
        }
        dispatch_sync[args.command](args)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
