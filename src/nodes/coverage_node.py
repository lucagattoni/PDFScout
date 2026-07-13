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
    COVERAGE_RETRY_MAX_PAGES,
    COVERAGE_WARN_THRESHOLD,
    COVERAGE_WARN_THRESHOLD_FIGURE,
    CROSS_PAGE_DUP_MIN_BLOCKS,
    CROSS_PAGE_DUP_MIN_CHARS,
    CROSS_PAGE_DUP_RATIO,
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


def page_word_coverage(native: str, blocks: list[dict[str, Any]], page: int) -> float | None:
    """Fraction of a page's significant native words present in its extracted
    blocks; None when the page is not auditable."""
    if not native_layer_usable(native):
        return None
    native_words = significant_words(native)
    if len(native_words) < COVERAGE_MIN_WORDS:
        return None
    return len(native_words & _page_haystack(blocks, page)) / len(native_words)


def coverage_findings(
    native_texts: dict[int, str], blocks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Structured per-page findings for pages below their warn threshold."""
    findings: list[dict[str, Any]] = []
    for page, native in sorted(native_texts.items()):
        coverage = page_word_coverage(native, blocks, page)
        if coverage is None:
            continue
        has_figure = any(
            b["bbox"]["page_number"] == page and b.get("type") == "figure" for b in blocks
        )
        threshold = COVERAGE_WARN_THRESHOLD_FIGURE if has_figure else COVERAGE_WARN_THRESHOLD
        if coverage < threshold:
            native_words = significant_words(native)
            sample = sorted(native_words - _page_haystack(blocks, page))[:8]
            findings.append(
                {"page": page, "coverage": coverage, "threshold": threshold, "sample": sample}
            )
    return findings


def audit_page_coverage(
    native_texts: dict[int, str], blocks: list[dict[str, Any]], *, suffix: str = ""
) -> list[str]:
    """Pure audit: page number → native text, plus extracted blocks → warnings."""
    return [
        (
            f"Page {f['page']}: only {f['coverage']:.0%} of the native text layer's "
            f"significant words appear in the extracted blocks "
            f"(threshold {f['threshold']:.0%}) — content may have been dropped{suffix}. "
            f"Missing examples: {', '.join(f['sample'])}"
        )
        for f in coverage_findings(native_texts, blocks)
    ]


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", _norm(s)).strip()


def duplication_findings(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect page-attribution failures: a worker that extracted the wrong
    page re-emits another page's content under its own page number (observed
    on a real 16-page paper: page 5's worker re-described page 4, so page 5's
    real content was silently dropped). Flag any page whose substantial blocks
    mostly duplicate another single page's text. Returns structured findings."""
    by_page: dict[int, list[str]] = {}
    for b in blocks:
        text = _squash(b.get("text", ""))
        if len(text) >= CROSS_PAGE_DUP_MIN_CHARS:
            by_page.setdefault(b["bbox"]["page_number"], []).append(text)

    warnings: list[str] = []
    pages = sorted(by_page)
    reported: set[tuple[int, int]] = set()
    for n in pages:
        if len(by_page[n]) < CROSS_PAGE_DUP_MIN_BLOCKS:
            continue
        # Ratio of page n's substantial blocks found on each other page. A
        # genuine wrong-page extraction duplicates ONE specific page; templated
        # boilerplate (repeated section boxes, headers) matches MANY pages —
        # suppress the warning in that case rather than flooding.
        ratios = {}
        for m in pages:
            if m == n:
                continue
            other = set(by_page[m])
            ratios[m] = sum(1 for t in by_page[n] if t in other) / len(by_page[n])
        above = [m for m, r in ratios.items() if r >= CROSS_PAGE_DUP_RATIO]
        if len(above) != 1:
            continue
        m = above[0]
        pair = (min(n, m), max(n, m))
        if pair in reported:
            continue
        reported.add(pair)
        warnings.append({"page": n, "other": m, "ratio": ratios[m]})
    return warnings


def audit_cross_page_duplication(blocks: list[dict[str, Any]], *, suffix: str = "") -> list[str]:
    return [
        (
            f"Pages {f['page']} and {f['other']}: {f['ratio']:.0%} of page {f['page']}'s "
            f"substantial blocks duplicate page {f['other']}'s text — a worker may have "
            f"extracted the wrong page, and page {f['page']}'s real content may be "
            f"missing{suffix}."
        )
        for f in duplication_findings(blocks)
    ]


def page_anchors(native_text: str) -> tuple[str, str] | None:
    """First and last significant native-layer lines of a page — used to anchor
    the extraction prompt to the physical page and prevent wrong-page
    extraction. None when the native layer is unusable."""
    if not native_layer_usable(native_text):
        return None
    lines = [ln.strip() for ln in native_text.splitlines()
             if len(ln.strip()) >= 8 and sum(c.isalnum() for c in ln) >= 5]
    if len(lines) < 2:
        return None
    return lines[0][:120], lines[-1][:120]


async def coverage_auditor_node(state: dict[str, Any]) -> dict[str, Any]:
    """Graph node: audit the extracted blocks against the native text layer,
    then re-extract up to COVERAGE_RETRY_MAX_PAGES flagged pages once each,
    keeping whichever block set scores better native coverage (never regress)."""
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
    blocks = state["extracted_flat_blocks"] or []

    flagged: list[int] = []
    for f in coverage_findings(native_texts, blocks):
        flagged.append(f["page"])
    for f in duplication_findings(blocks):
        # A duplicate pair means one page's real content is missing — retry the
        # page with the LOWER native coverage (that's the misattributed one;
        # observed: pages 4/5 duplicated, page 5's real content was gone).
        n, m = f["page"], f["other"]
        cov_n = page_word_coverage(native_texts.get(n, ""), blocks, n)
        cov_m = page_word_coverage(native_texts.get(m, ""), blocks, m)
        if cov_n is None and cov_m is not None:
            pick = m
        elif cov_m is None or cov_n is None:
            pick = n
        else:
            pick = n if cov_n <= cov_m else m
        if pick not in flagged:
            flagged.append(pick)

    if not flagged:
        return {"extraction_warnings": []}

    # Late import: worker_node imports page_anchors from this module.
    from src.nodes.worker_node import burst_worker_node

    usage_log: list[dict] = []
    extra_warnings: list[str] = []
    replaced_pages: list[int] = []
    replacement_blocks: list[dict[str, Any]] = []
    for page in flagged[:COVERAGE_RETRY_MAX_PAGES]:
        # A retry can only be kept if the result is scoreable against the
        # native layer — skip the paid call when it isn't (never-regress rule).
        if page_word_coverage(native_texts.get(page, ""), blocks, page) is None and not (
            native_layer_usable(native_texts.get(page, ""))
        ):
            extra_warnings.append(
                f"Coverage retry: page {page} flagged but not retried — its native "
                f"text layer is unusable, so an improvement could not be verified."
            )
            continue
        result = await burst_worker_node(
            {**state, "current_page": page, "last_validation_error": None}
        )
        usage_log += result.get("usage_log", [])
        extra_warnings += result.get("extraction_warnings", [])
        # Strict page scope: only blocks the retry attributes to this page count.
        new_page_blocks = [
            b for b in (result.get("extracted_flat_blocks") or [])
            if b.get("bbox", {}).get("page_number") == page
        ]
        old_cov = page_word_coverage(native_texts.get(page, ""), blocks, page)
        new_cov = page_word_coverage(native_texts.get(page, ""), new_page_blocks, page)
        if new_cov is not None and (old_cov is None or new_cov > old_cov):
            replaced_pages.append(page)
            replacement_blocks += new_page_blocks

    if replaced_pages:
        final_blocks = [
            b for b in blocks
            if b.get("bbox", {}).get("page_number") not in set(replaced_pages)
        ] + replacement_blocks
        extra_warnings.append(
            f"Coverage retry: re-extracted page(s) "
            f"{', '.join(str(p) for p in replaced_pages)} after audit flags; "
            f"better-scoring result kept."
        )
    else:
        final_blocks = blocks

    skipped = flagged[COVERAGE_RETRY_MAX_PAGES:]
    if skipped:
        extra_warnings.append(
            f"Coverage retry: page(s) {', '.join(str(p) for p in skipped)} also "
            f"flagged but not retried (COVERAGE_RETRY_MAX_PAGES={COVERAGE_RETRY_MAX_PAGES})."
        )

    warnings = audit_page_coverage(native_texts, final_blocks, suffix=" (after retry)" if replaced_pages else "")
    warnings += audit_cross_page_duplication(final_blocks, suffix=" (after retry)" if replaced_pages else "")

    out: dict[str, Any] = {"extraction_warnings": warnings + extra_warnings, "usage_log": usage_log}
    if replaced_pages:
        out["extracted_flat_blocks"] = (
            [{"__replace_pages__": replaced_pages}] + replacement_blocks
        )
    return out
