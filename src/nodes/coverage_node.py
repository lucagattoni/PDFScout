"""Completeness oracle: audit extracted blocks against the PDF's native text layer.

The extraction model can silently drop blocks or whole pages (observed on real
documents: a page dropped by output truncation; sections lost run-to-run). The
native text layer — when present and readable — is an independent witness of
what text exists on each page. This node compares the two and appends an
extraction warning when a large share of a page's native words is absent from
the extracted blocks. Warning-only: it never mutates blocks.

Design constraints (all thresholds principled, none document-specific):
- Word-level, order-free comparison — robust to line-break hyphenation, column
  reflow, and table linearization that break line-level containment.
- Scanned or subset-font-encoded PDFs have no usable native layer; a char-class
  check disables the audit for such pages rather than false-alarming.
- Figure content is *summarized* by the extractor by design, so pages that
  contain figure blocks get a lower warn threshold instead of being flagged
  for missing diagram text.
"""
import re
import unicodedata
from typing import Any

from pypdf import PdfReader

from src.config import (
    COVERAGE_CHAR_CLASS_MIN,
    COVERAGE_MIN_NATIVE_CHARS,
    COVERAGE_MIN_WORDS,
    COVERAGE_WARN_THRESHOLD,
    COVERAGE_WARN_THRESHOLD_FIGURE,
)

_DOC_CHARS = set(".,;:€$%()/-–—'\"@&*+=<>[]|_!?")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower().replace("-", "")


def significant_words(text: str) -> set[str]:
    """Alphabetic words of ≥5 chars — long enough to be content-bearing,
    short-word noise (articles, units, column fragments) excluded."""
    return set(re.findall(r"[a-z]{5,}", _norm(text)))


def native_layer_usable(text: str) -> bool:
    """True when the native layer looks like readable document text.

    Subset-font / custom-encoded PDFs extract as symbol soup; real document
    text is almost entirely alphanumerics, whitespace, and common punctuation."""
    if len(text) < COVERAGE_MIN_NATIVE_CHARS:
        return False
    ok = sum(1 for c in text if c.isalnum() or c.isspace() or c in _DOC_CHARS)
    return ok / len(text) >= COVERAGE_CHAR_CLASS_MIN


def _page_haystack(blocks: list[dict[str, Any]], page: int) -> set[str]:
    """All extracted text for a page: block text, table cells, metadata values."""
    parts: list[str] = []
    for b in blocks:
        if b["bbox"]["page_number"] != page:
            continue
        parts.append(b.get("text", ""))
        md = b.get("metadata") or {}
        for cell in (md.get("table_data") or {}).get("cells", []):
            parts.append(str(cell.get("value", "")))
        for v in (md.get("bibliographic") or {}).values():
            parts.append(" ".join(v) if isinstance(v, list) else str(v))
    return significant_words(" ".join(parts))


def audit_page_coverage(
    native_texts: dict[int, str], blocks: list[dict[str, Any]]
) -> list[str]:
    """Pure audit: page number → native text, plus extracted blocks → warnings."""
    warnings: list[str] = []
    for page, native in sorted(native_texts.items()):
        if not native_layer_usable(native):
            continue
        native_words = significant_words(native)
        if len(native_words) < COVERAGE_MIN_WORDS:
            continue
        page_blocks_words = _page_haystack(blocks, page)
        coverage = len(native_words & page_blocks_words) / len(native_words)
        has_figure = any(
            b["bbox"]["page_number"] == page and b.get("type") == "figure" for b in blocks
        )
        threshold = COVERAGE_WARN_THRESHOLD_FIGURE if has_figure else COVERAGE_WARN_THRESHOLD
        if coverage < threshold:
            sample = sorted(native_words - page_blocks_words)[:8]
            warnings.append(
                f"Page {page}: only {coverage:.0%} of the native text layer's "
                f"significant words appear in the extracted blocks "
                f"(threshold {threshold:.0%}) — content may have been dropped. "
                f"Missing examples: {', '.join(sample)}"
            )
    return warnings


async def coverage_auditor_node(state: dict[str, Any]) -> dict[str, Any]:
    """Graph node: read native text per page and audit the extracted blocks."""
    try:
        reader = PdfReader(state["file_path"])
        native_texts = {
            i: (page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)
        }
    except Exception as e:  # noqa: BLE001 — a broken native layer must never fail the run
        return {
            "extraction_warnings": [
                f"Coverage audit skipped: could not read native text layer ({e})."
            ]
        }
    warnings = audit_page_coverage(native_texts, state["extracted_flat_blocks"] or [])
    return {"extraction_warnings": warnings}
