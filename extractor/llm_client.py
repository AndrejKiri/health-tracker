"""
Async Ollama LLM client for the health data extraction service.

Responsibilities
----------------
- Send PDF text to the Ollama /api/generate endpoint.
- Parse JSON from the model response (handles markdown code fences).
- Retry up to 3 times with exponential backoff on transient errors.
- Validate the parsed JSON against Pydantic schemas.
- Log token usage and wall-clock timing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import date as _date
from typing import Any

import httpx

from .config import config
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schema import ExtractionResult, LabResult, MedicalEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BASE_BACKOFF = 2.0        # seconds (doubled each retry)
_REQUEST_TIMEOUT = 600.0   # seconds per individual request

# Regex to extract a JSON block from LLM output that may include
# markdown code fences (```json ... ```) or bare JSON.
_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*([\s\S]+?)\s*```",
    re.IGNORECASE,
)

# Patterns for dates commonly found in lab reports.
# Tries ISO first, then "Month DD, YYYY", then "DD Month YYYY".
_DATE_PATTERNS = [
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
]

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


_REPORT_DATE_LABEL_RE = re.compile(
    r"(?:report\s+date|date\s+of\s+service|collected?(?:ion)?(?:\s+date)?|"
    r"specimen\s+date|test\s+date|result\s+date)\s*[:\-]?\s*",
    re.IGNORECASE,
)


def _parse_date_at(text: str, pos: int) -> str | None:
    """Try to parse a date starting near position pos in text."""
    snippet = text[pos:pos + 40]
    m = _DATE_PATTERNS[0].match(snippet)
    if m:
        return m.group(1)
    m = _DATE_PATTERNS[1].match(snippet)
    if m:
        month = _MONTH_MAP[m.group(1).lower()]
        return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"
    m = _DATE_PATTERNS[2].match(snippet)
    if m:
        month = _MONTH_MAP[m.group(2).lower()]
        return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}"
    return None


def _extract_fallback_date(text: str) -> str | None:
    """Return the report/collection date from the PDF text as YYYY-MM-DD.

    Prefers dates that follow a label like 'Report Date:' or 'Collected:'.
    Falls back to the most recent date found anywhere in the text.
    """
    # 1. Look for labelled dates first
    for label_match in _REPORT_DATE_LABEL_RE.finditer(text):
        d = _parse_date_at(text, label_match.end())
        if d:
            return d

    # 2. Fallback: collect all dates, return the most recent one
    candidates: list[str] = []
    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            if pattern == _DATE_PATTERNS[0]:
                candidates.append(m.group(1))
            elif pattern == _DATE_PATTERNS[1]:
                month = _MONTH_MAP[m.group(1).lower()]
                candidates.append(f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}")
            else:
                month = _MONTH_MAP[m.group(2).lower()]
                candidates.append(f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(1)):02d}")

    return max(candidates) if candidates else None


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------


def _parse_json_from_response(text: str) -> dict[str, Any]:
    """
    Extract and parse JSON from raw LLM output.

    Tries the following in order:
    1. Pull the first ```json ... ``` code block.
    2. Pull the first ``` ... ``` code block (language-unspecified).
    3. Find the first ``{`` … last ``}`` substring and parse it directly.

    Raises
    ------
    ValueError
        If no parseable JSON is found.
    """
    # Try fenced code block first
    match = _JSON_BLOCK_RE.search(text)
    if match:
        candidate = match.group(1).strip()
        return json.loads(candidate)

    # Try raw JSON delimited by outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        return json.loads(candidate)

    raise ValueError(
        "No JSON object found in LLM response. "
        f"Response snippet: {text[:300]!r}"
    )


# ---------------------------------------------------------------------------
# Pydantic validation helper
# ---------------------------------------------------------------------------


def _validate_response(raw: dict[str, Any], fallback_date: str | None = None) -> dict[str, Any]:
    """
    Validate and normalise the LLM JSON output against Pydantic schemas.

    Returns a dict with keys:
        lab_results : list[dict]   — validated LabResult dicts
        events      : list[dict]   — validated MedicalEvent dicts
        errors      : list[str]    — per-item validation errors (non-fatal)
    """
    validated_results: list[dict] = []
    validated_events: list[dict] = []
    errors: list[str] = []

    for item in raw.get("lab_results", []):
        if item.get("date") is None and fallback_date:
            logger.info("Patching null date → %s for: %s", fallback_date, item.get("measurement"))
            item = {**item, "date": fallback_date}
        try:
            lr = LabResult.model_validate(item)
            validated_results.append(lr.model_dump())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"LabResult validation error: {exc} | data={item}")
            logger.warning("Skipping invalid lab result: %s | %s", exc, item)

    for item in raw.get("events", []):
        if item.get("date") is None and fallback_date:
            item = {**item, "date": fallback_date}
        try:
            ev = MedicalEvent.model_validate(item)
            validated_events.append(ev.model_dump())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"MedicalEvent validation error: {exc} | data={item}")
            logger.warning("Skipping invalid event: %s | %s", exc, item)

    return {
        "lab_results": validated_results,
        "events": validated_events,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Core async extraction function
# ---------------------------------------------------------------------------


async def extract_from_text(
    text: str,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Send ``text`` to Ollama and return structured extraction results.

    Parameters
    ----------
    text : str
        Raw PDF text to extract data from.
    model : str | None
        Ollama model name.  Defaults to ``config.ollama_model``.

    Returns
    -------
    dict with keys:
        lab_results : list[dict]
        events      : list[dict]
        errors      : list[str]      — validation errors (non-fatal)
        token_usage : dict           — prompt/eval token counts from Ollama
        elapsed_sec : float          — wall-clock seconds for the call

    Raises
    ------
    RuntimeError
        After all retry attempts are exhausted.
    """
    model = model or config.ollama_model
    fallback_date = _extract_fallback_date(text)
    if fallback_date:
        logger.info("Fallback date extracted from PDF text: %s", fallback_date)
    user_prompt = build_user_prompt(text)

    payload = {
        "model": model,
        "system": SYSTEM_PROMPT,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,   # deterministic extraction
            "num_predict": 2048,  # sufficient for structured lab JSON on CPU
        },
    }

    url = f"{config.ollama_url}/api/generate"
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            logger.info(
                "Ollama request (attempt %d/%d): model=%s, text_len=%d",
                attempt,
                _MAX_RETRIES,
                model,
                len(text),
            )
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

            elapsed = time.monotonic() - t0
            body = response.json()

            # ---- Log token usage -----------------------------------------
            token_usage = {
                "prompt_eval_count": body.get("prompt_eval_count"),
                "eval_count": body.get("eval_count"),
            }
            logger.info(
                "Ollama response received in %.1fs | tokens: prompt=%s eval=%s",
                elapsed,
                token_usage["prompt_eval_count"],
                token_usage["eval_count"],
            )

            # ---- Parse JSON from model output ----------------------------
            raw_response: str = body.get("response", "")
            logger.debug("Raw LLM output (first 500 chars): %s", raw_response[:500])

            parsed = _parse_json_from_response(raw_response)
            validated = _validate_response(parsed, fallback_date=fallback_date)
            validated["token_usage"] = token_usage
            validated["elapsed_sec"] = elapsed
            return validated

        except httpx.TimeoutException as exc:
            last_exc = exc
            logger.warning(
                "Ollama request timed out (attempt %d/%d): %s",
                attempt, _MAX_RETRIES, exc,
            )
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            logger.warning(
                "Ollama HTTP error %d (attempt %d/%d): %s",
                exc.response.status_code, attempt, _MAX_RETRIES, exc,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            last_exc = exc
            logger.warning(
                "JSON parse error (attempt %d/%d): %s",
                attempt, _MAX_RETRIES, exc,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "Unexpected error (attempt %d/%d): %s",
                attempt, _MAX_RETRIES, exc,
            )

        if attempt < _MAX_RETRIES:
            backoff = _BASE_BACKOFF ** attempt
            logger.info("Retrying in %.1f seconds...", backoff)
            await asyncio.sleep(backoff)

    raise RuntimeError(
        f"Ollama extraction failed after {_MAX_RETRIES} attempts. "
        f"Last error: {last_exc}"
    )
