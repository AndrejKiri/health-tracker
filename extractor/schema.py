"""
Pydantic v2 data models for the health data extraction service.

These models define the canonical shape of extracted lab results and medical
events, and are used both for LLM response validation and database insertion.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_YEAR = 1950
_MAX_YEAR = 2050
_VALID_FLAGS = {"H", "L", None}

# Formats tried in order when the input is not ISO 8601.
# Handles common LLM outputs like "June 15, 2024" or "15 Jun 2024".
_DATE_FORMATS = [
    "%B %d, %Y",   # June 15, 2024
    "%b %d, %Y",   # Jun 15, 2024
    "%d %B %Y",    # 15 June 2024
    "%d %b %Y",    # 15 Jun 2024
    "%m/%d/%Y",    # 06/15/2024
    "%Y/%m/%d",    # 2024/06/15
]


def _parse_date(v: object) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if not isinstance(v, str):
        raise ValueError(f"Cannot parse date from {v!r}")
    v = v.strip()
    try:
        return date.fromisoformat(v)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {v!r}")


# ---------------------------------------------------------------------------
# Lab Result
# ---------------------------------------------------------------------------


class LabResult(BaseModel):
    """A single quantitative (or qualitative) measurement from a lab report."""

    date: date
    category: str
    measurement: str
    value: Optional[float] = None
    value_text: Optional[str] = None
    unit: str
    flag: Optional[str] = None  # "H" (high), "L" (low), or None

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    @field_validator("date", mode="before")
    @classmethod
    def validate_date_range(cls, v: object) -> object:
        """Normalise and reject dates outside a reasonable human lifespan window."""
        d = _parse_date(v)
        if not (_MIN_YEAR <= d.year <= _MAX_YEAR):
            raise ValueError(
                f"Date {d} is outside the accepted range "
                f"{_MIN_YEAR}–{_MAX_YEAR}"
            )
        return d

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value(cls, v: object) -> Optional[float]:
        """
        Accept numeric strings and convert them; return None for explicitly
        absent or non-numeric values (textual results should use value_text).
        """
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @field_validator("flag", mode="before")
    @classmethod
    def validate_flag(cls, v: object) -> Optional[str]:
        """Normalise flag to H / L / None; reject anything else."""
        if v is None or v == "" or v == "N" or v == "Normal":
            return None
        normalised = str(v).strip().upper()
        if normalised not in ("H", "L"):
            raise ValueError(
                f"flag must be 'H', 'L', or None — got {v!r}"
            )
        return normalised

    @model_validator(mode="after")
    def require_value_or_text(self) -> "LabResult":
        """At least one of value or value_text must be set."""
        if self.value is None and not self.value_text:
            raise ValueError(
                "LabResult requires either a numeric 'value' or a 'value_text'"
            )
        return self


# ---------------------------------------------------------------------------
# Medical Event
# ---------------------------------------------------------------------------


class MedicalEvent(BaseModel):
    """A clinical event such as an imaging study, procedure, or diagnosis."""

    date: date
    end_date: Optional[date] = None
    category: Literal[
        "Imaging", "Procedure", "Diagnosis", "Medication",
        "Vaccination", "Visit", "Other",
    ]
    subcategory: Optional[str] = None  # e.g. "MRI", "CT", "Surgery"
    title: str
    description: Optional[str] = None

    @field_validator("date", "end_date", mode="before")
    @classmethod
    def validate_date_range(cls, v: object) -> Optional[object]:
        if v is None or v == "":
            return None
        d = _parse_date(v)
        if not (_MIN_YEAR <= d.year <= _MAX_YEAR):
            raise ValueError(
                f"Date {d} is outside the accepted range "
                f"{_MIN_YEAR}–{_MAX_YEAR}"
            )
        return d

    @model_validator(mode="after")
    def end_date_after_start(self) -> "MedicalEvent":
        """end_date must not precede date when both are present."""
        if self.end_date is not None and self.end_date < self.date:
            raise ValueError("end_date must not be before date")
        return self


# ---------------------------------------------------------------------------
# Extraction Result (top-level LLM output wrapper)
# ---------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """
    Full output of a single PDF extraction run.
    Contains all lab results and medical events parsed from one document.
    """

    lab_results: list[LabResult]
    events: list[MedicalEvent]
    source_file: str
    extracted_at: datetime
    raw_text: Optional[str] = None
