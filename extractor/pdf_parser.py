"""
PDF text extraction module.

Primary strategy  : pymupdf (fitz) — fast, works on text-based PDFs.
Fallback strategy : pdf2image + pytesseract OCR — for scanned/image-only PDFs.

Public API
----------
extract_text(pdf_path)  -> str           Full document text (all pages joined)
extract_pages(pdf_path) -> list[str]     Per-page text list
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum character count on a page to consider it "text-based"
_TEXT_THRESHOLD = 50


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_text_page(page_text: str) -> bool:
    """Return True if the page contains substantial selectable text."""
    stripped = page_text.strip()
    return len(stripped) >= _TEXT_THRESHOLD


def _extract_via_pymupdf(pdf_path: str) -> list[str]:
    """
    Extract text from each page using pymupdf (fitz).

    Returns a list of strings — one per page. Pages with no selectable text
    are returned as empty strings (caller decides whether to OCR them).
    """
    import fitz  # type: ignore[import]

    pages: list[str] = []
    doc = fitz.open(pdf_path)
    try:
        for page in doc:
            text = page.get_text("text")  # type: ignore[attr-defined]
            pages.append(text)
    finally:
        doc.close()
    return pages


def _ocr_page_image(image) -> str:  # type: ignore[type-arg]
    """Run Tesseract OCR on a single PIL image and return the text."""
    import pytesseract  # type: ignore[import]

    return pytesseract.image_to_string(image, config="--psm 6")


def _extract_via_ocr(pdf_path: str) -> list[str]:
    """
    Convert each PDF page to an image and run OCR.

    Used as a fallback when pymupdf yields no useful text.
    """
    from pdf2image import convert_from_path  # type: ignore[import]

    logger.warning(
        "Falling back to OCR for '%s' — this may be slow.", pdf_path
    )
    images = convert_from_path(pdf_path, dpi=300)
    pages: list[str] = []
    for i, image in enumerate(images):
        logger.debug("OCR processing page %d of '%s'", i + 1, pdf_path)
        pages.append(_ocr_page_image(image))
    return pages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_pages(pdf_path: str) -> list[str]:
    """
    Extract text from a PDF, returning a list with one entry per page.

    Strategy:
    1. Attempt text extraction with pymupdf.
    2. If a page has insufficient text (image-only), OCR that page.
    3. If pymupdf raises an error, fall back to full OCR.

    Parameters
    ----------
    pdf_path : str
        Absolute or relative path to the PDF file.

    Returns
    -------
    list[str]
        Text content per page.  An empty list if the file cannot be read.
    """
    path = Path(pdf_path)
    if not path.exists():
        logger.error("PDF not found: '%s'", pdf_path)
        return []

    # ---- Primary: pymupdf ------------------------------------------------
    try:
        mupdf_pages = _extract_via_pymupdf(pdf_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pymupdf failed for '%s' (%s); falling back to full OCR.",
            pdf_path,
            exc,
        )
        try:
            return _extract_via_ocr(pdf_path)
        except Exception as ocr_exc:  # noqa: BLE001
            logger.error(
                "OCR also failed for '%s': %s", pdf_path, ocr_exc
            )
            return []

    # ---- Selective OCR for image-only pages ------------------------------
    result: list[str] = []
    needs_ocr_indices: list[int] = []

    for i, text in enumerate(mupdf_pages):
        if _is_text_page(text):
            result.append(text)
        else:
            logger.debug(
                "Page %d of '%s' appears to be image-based; scheduling OCR.",
                i + 1,
                pdf_path,
            )
            result.append("")  # placeholder
            needs_ocr_indices.append(i)

    if needs_ocr_indices:
        try:
            from pdf2image import convert_from_path  # type: ignore[import]

            # convert_from_path returns every page between first_page and
            # last_page inclusive, not just the ones we asked about.
            # needs_ocr_indices may be non-contiguous (e.g. pages 1 and 4),
            # so we cannot use enumerate() to map image slots back to page
            # indices — that would place page-2's image into page-4's slot.
            # Instead, derive the image index as the offset from the first
            # converted page so the mapping is always correct.
            first_ocr_page_idx = needs_ocr_indices[0]
            first_page = first_ocr_page_idx + 1          # 1-based for pdf2image
            last_page = needs_ocr_indices[-1] + 1
            images = convert_from_path(
                pdf_path,
                dpi=300,
                first_page=first_page,
                last_page=last_page,
            )
            for page_idx in needs_ocr_indices:
                img_idx = page_idx - first_ocr_page_idx
                if img_idx < len(images):
                    logger.warning(
                        "OCR used for page %d of '%s'.", page_idx + 1, pdf_path
                    )
                    result[page_idx] = _ocr_page_image(images[img_idx])
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "OCR failed for selective pages in '%s': %s", pdf_path, exc
            )

    return result


def extract_text(pdf_path: str) -> str:
    """
    Extract all text from a PDF as a single string.

    Pages are separated by a form-feed character (\\f) to preserve document
    structure when the LLM processes the content.

    Parameters
    ----------
    pdf_path : str
        Absolute or relative path to the PDF file.

    Returns
    -------
    str
        Full document text, or an empty string on failure.
    """
    pages = extract_pages(pdf_path)
    if not pages:
        return ""
    return "\f".join(pages)
