from unittest.mock import AsyncMock, MagicMock

from src.nodes.coverage_node import (
    audit_cross_page_duplication,
    audit_page_coverage,
    coverage_auditor_node,
    native_layer_usable,
    page_anchors,
    significant_words,
)
from src.state import merge_flat_blocks


def _block(page: int, text: str, btype: str = "paragraph", cells: list | None = None):
    b = {
        "block_id": f"b{page}-{abs(hash(text)) % 9999}",
        "type": btype,
        "text": text,
        "bbox": {"page_number": page, "coordinates": [0, 0, 10, 10]},
    }
    if cells is not None:
        b["metadata"] = {
            "table_data": {
                "total_rows": 1,
                "total_cols": len(cells),
                "cells": [{"r": 0, "c": i, "value": v} for i, v in enumerate(cells)],
            }
        }
    return b


_CLEAN_TEXT = (
    "The quarterly statement summarises electricity consumption across the billing "
    "period including standing charges, government levies and applicable taxation. "
    "Payment terms require settlement within fourteen days of issuance."
)

# Subset-font PDFs map glyphs to control codes — the native layer extracts as
# control-character soup (observed on a real invoice: \x01, \x1b, \x17 dominate).
_GARBLED = (
    "\x01\x1b#%\x17)\x19\x02\x06(\x15'\x11\x18\x0e\x1a 9988\x01=988\x02$0 \x061122334455 " * 5
)


class TestNativeLayerUsable:
    def test_clean_text_usable(self):
        assert native_layer_usable(_CLEAN_TEXT)

    def test_garbled_subset_font_unusable(self):
        assert not native_layer_usable(_GARBLED)

    def test_short_text_unusable(self):
        assert not native_layer_usable("Hello world")

    def test_empty_unusable(self):
        assert not native_layer_usable("")

    def test_number_heavy_form_text_usable(self):
        # Utility-bill pages are number/currency-heavy but perfectly readable —
        # the char-class check must not classify them as garbled.
        form = (
            "Your last bill €82.68 Payments €82.68 cr Balance €0.00 "
            "Charges for this period €106.23 Savings €2.89 cr VAT €9.30 "
            "Total due €112.64 Billing period 28 Mar 26 to 28 May 26 62 days"
        )
        assert native_layer_usable(form)


class TestSignificantWords:
    def test_short_words_excluded(self):
        assert significant_words("the cat sat on a mat") == set()

    def test_hyphenation_canonicalized(self):
        # 'task-specific' at a line break must equal 'taskspecific'
        assert significant_words("task-specific") == significant_words("taskspecific")

    def test_ligatures_normalized(self):
        assert significant_words("ﬁne-tuning") == significant_words("fine-tuning")


class TestAuditPageCoverage:
    def test_full_coverage_no_warning(self):
        warnings = audit_page_coverage({1: _CLEAN_TEXT}, [_block(1, _CLEAN_TEXT)])
        assert warnings == []

    def test_dropped_page_warns(self):
        # Page 2 extracted zero blocks — the truncation failure class.
        warnings = audit_page_coverage(
            {1: _CLEAN_TEXT, 2: _CLEAN_TEXT},
            [_block(1, _CLEAN_TEXT)],
        )
        assert len(warnings) == 1
        assert warnings[0].startswith("Page 2:")
        assert "0%" in warnings[0]

    def test_garbled_native_layer_silently_skipped(self):
        warnings = audit_page_coverage({1: _GARBLED}, [])
        assert warnings == []

    def test_table_cells_count_as_coverage(self):
        # Values captured only in table_data cells (not block text) must count.
        native = (
            "Standing charge quantity amount consumption kilowatt levies "
            "government taxation settlement electricity statement summarises"
        )
        blocks = [
            _block(
                1,
                "Charges table",
                btype="table",
                cells=[
                    "Standing charge quantity amount",
                    "consumption kilowatt levies",
                    "government taxation settlement electricity statement summarises",
                ],
            )
        ]
        assert audit_page_coverage({1: native}, blocks) == []

    def test_figure_page_gets_lower_threshold(self):
        # ~35% coverage: warns on a text page, tolerated on a figure page
        # (figures are summarized by design).
        native_words = (
            "alpha1 bravo2 charlie3 delta4 echo5 foxtrot6 golfing hotels indiana "
            "juliet kilo95 lima77 mike88 november oscar9 papa42 quebec romeo "
            "sierra tango1"
        )
        native = " ".join(w for w in native_words.split())
        covered = " ".join(native.split()[:7])
        figure_blocks = [_block(1, covered, btype="figure")]
        assert audit_page_coverage({1: native}, figure_blocks) == []
        text_blocks = [_block(1, covered, btype="paragraph")]
        assert len(audit_page_coverage({1: native}, text_blocks)) == 1

    def test_empty_native_texts_no_warning(self):
        assert audit_page_coverage({}, [_block(1, "anything")]) == []

    def test_too_few_native_words_skipped(self):
        # A page with almost no significant words (cover page, separator)
        # is not auditable — no warning.
        assert audit_page_coverage({1: "Appendix " * 12}, []) == []


class TestCrossPageDuplication:
    def test_wrong_page_extraction_flagged(self):
        # Page 5's worker re-emitted page 4's content (real observed failure):
        # most of page 5's substantial blocks duplicate page 4's text.
        texts = [
            "Although this allows us to obtain a bidirectional pre-trained model",
            "To make BERT handle a variety of down-stream tasks our inputs",
            "Unlike prior encoders the representation fuses both directions",
            "In order to train a deep bidirectional representation we mask",
            "Many important downstream tasks such as question answering",
        ]
        blocks = [_block(4, t) for t in texts] + [_block(5, t) for t in texts[:4]]
        blocks.append(_block(5, "One genuinely new page five sentence about experiments"))
        warnings = audit_cross_page_duplication(blocks)
        assert len(warnings) == 1
        assert "worker may have extracted the wrong page" in warnings[0]

    def test_repeated_page_furniture_not_flagged(self):
        # Headers/footers repeat on every page — short strings are excluded
        # and one repeated block never crosses the ratio on a full page.
        pages = []
        for p in (1, 2, 3):
            pages.append(_block(p, "VAT Reg No IE 8F 52100V E&OE all rights reserved"))
            for i in range(5):
                pages.append(
                    _block(p, f"Unique page {p} paragraph number {i} with distinct content here")
                )
        assert audit_cross_page_duplication(pages) == []

    def test_small_pages_skipped(self):
        # Below CROSS_PAGE_DUP_MIN_BLOCKS the ratio is meaningless.
        blocks = [
            _block(1, "Shared long sentence appearing on both pages equally"),
            _block(2, "Shared long sentence appearing on both pages equally"),
        ]
        assert audit_cross_page_duplication(blocks) == []

    def test_empty_blocks_no_warning(self):
        assert audit_cross_page_duplication([]) == []


class TestPageAnchors:
    def test_clean_page_yields_first_and_last_lines(self):
        text = "Opening heading line\n" + _CLEAN_TEXT + "\nClosing footer line here"
        anchors = page_anchors(text)
        assert anchors is not None
        first, last = anchors
        assert first.startswith("Opening heading")
        assert last.startswith("Closing footer")

    def test_garbled_layer_yields_none(self):
        assert page_anchors(_GARBLED) is None

    def test_single_line_yields_none(self):
        assert page_anchors("Just one line of sufficient length here " * 3) is None


class TestReplacePagesReducer:
    def test_replace_drops_old_page_blocks(self):
        existing = [_block(1, "page one text"), _block(2, "old page two text")]
        new = [{"__replace_pages__": [2]}, _block(2, "new page two text")]
        merged = merge_flat_blocks(existing, new)
        texts = [b["text"] for b in merged]
        assert "old page two text" not in texts
        assert "new page two text" in texts
        assert "page one text" in texts

    def test_normal_append_unchanged(self):
        merged = merge_flat_blocks([_block(1, "a")], [_block(2, "b")])
        assert len(merged) == 2

    def test_none_still_resets(self):
        assert merge_flat_blocks([_block(1, "a")], None) == []


def _reader_mock(mocker, page_texts: list[str]):
    pages = []
    for t in page_texts:
        pg = MagicMock()
        pg.extract_text.return_value = t
        pages.append(pg)
    reader = MagicMock()
    reader.pages = pages
    mocker.patch("src.nodes.coverage_node.PdfReader", return_value=reader)


class TestCoverageRetry:
    async def test_clean_document_makes_no_retry_call(self, mocker):
        _reader_mock(mocker, [_CLEAN_TEXT])
        worker = mocker.patch("src.nodes.worker_node.burst_worker_node", new=AsyncMock())
        result = await coverage_auditor_node(
            {"file_path": "x.pdf", "extracted_flat_blocks": [_block(1, _CLEAN_TEXT)]}
        )
        worker.assert_not_called()
        assert result["extraction_warnings"] == []

    async def test_flagged_page_retried_and_replaced_when_better(self, mocker):
        # Page 2 extracted nothing; retry returns full coverage -> replaced.
        _reader_mock(mocker, [_CLEAN_TEXT, _CLEAN_TEXT])
        good = _block(2, _CLEAN_TEXT)
        worker = mocker.patch(
            "src.nodes.worker_node.burst_worker_node",
            new=AsyncMock(
                return_value={
                    "extracted_flat_blocks": [good],
                    "usage_log": [
                        {
                            "context": "burst page 2 attempt 1",
                            "input_tokens": 1,
                            "output_tokens": 1,
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "stop_reason": "tool_use",
                        }
                    ],
                }
            ),
        )
        result = await coverage_auditor_node(
            {"file_path": "x.pdf", "extracted_flat_blocks": [_block(1, _CLEAN_TEXT)]}
        )
        worker.assert_called_once()
        assert worker.call_args.args[0]["current_page"] == 2
        assert result["extracted_flat_blocks"][0] == {"__replace_pages__": [2]}
        assert result["extracted_flat_blocks"][1]["text"] == _CLEAN_TEXT
        assert any("re-extracted page(s) 2" in w for w in result["extraction_warnings"])
        # coverage warning resolved after retry
        assert not any(w.startswith("Page 2:") for w in result["extraction_warnings"])
        assert len(result["usage_log"]) == 1

    async def test_worse_retry_never_regresses(self, mocker):
        # Page 2 has partial coverage; retry returns empty -> original kept.
        _reader_mock(mocker, [_CLEAN_TEXT, _CLEAN_TEXT])
        partial = _block(2, "quarterly statement summarises electricity")
        worker = mocker.patch(
            "src.nodes.worker_node.burst_worker_node",
            new=AsyncMock(return_value={"extracted_flat_blocks": [], "usage_log": []}),
        )
        result = await coverage_auditor_node(
            {"file_path": "x.pdf", "extracted_flat_blocks": [_block(1, _CLEAN_TEXT), partial]}
        )
        worker.assert_called_once()
        assert "extracted_flat_blocks" not in result
        assert any(w.startswith("Page 2:") for w in result["extraction_warnings"])

    async def test_retry_cost_cap_respected(self, mocker):
        # Three empty pages flagged; only COVERAGE_RETRY_MAX_PAGES (2) retried.
        _reader_mock(mocker, [_CLEAN_TEXT, _CLEAN_TEXT, _CLEAN_TEXT, _CLEAN_TEXT])
        worker = mocker.patch(
            "src.nodes.worker_node.burst_worker_node",
            new=AsyncMock(return_value={"extracted_flat_blocks": [], "usage_log": []}),
        )
        result = await coverage_auditor_node(
            {"file_path": "x.pdf", "extracted_flat_blocks": [_block(1, _CLEAN_TEXT)]}
        )
        assert worker.call_count == 2
        assert any("not retried" in w for w in result["extraction_warnings"])

    async def test_unscoreable_page_not_retried(self, mocker):
        # A duplicate pair on a document with a garbled native layer cannot be
        # scored — the paid retry is skipped (never-regress rule).
        _reader_mock(mocker, [_GARBLED, _GARBLED])
        dup = [
            _block(1, f"Shared substantial sentence number {i} appearing twice") for i in range(4)
        ] + [_block(2, f"Shared substantial sentence number {i} appearing twice") for i in range(4)]
        worker = mocker.patch("src.nodes.worker_node.burst_worker_node", new=AsyncMock())
        result = await coverage_auditor_node({"file_path": "x.pdf", "extracted_flat_blocks": dup})
        worker.assert_not_called()
        assert any("could not be verified" in w for w in result["extraction_warnings"])

    async def test_duplicate_pair_retries_lower_coverage_page(self, mocker):
        # Real sp-5 shape: pages 4/5 duplicated; the page whose native words
        # are missing (page 2 here) is the one retried — not the reported page.
        page2_native = (
            "Entirely different second page content about experiments results "
            "methodology evaluation benchmarks metrics baselines comparisons "
            "training procedure hyperparameters optimization convergence"
        )
        _reader_mock(mocker, [_CLEAN_TEXT, page2_native])
        shared = [
            _block(1, f"Shared substantial duplicated sentence number {i} here") for i in range(4)
        ]
        dup_on_2 = [
            _block(2, f"Shared substantial duplicated sentence number {i} here") for i in range(4)
        ]
        blocks = [_block(1, _CLEAN_TEXT)] + shared + dup_on_2
        worker = mocker.patch(
            "src.nodes.worker_node.burst_worker_node",
            new=AsyncMock(
                return_value={
                    "extracted_flat_blocks": [_block(2, page2_native)],
                    "usage_log": [],
                }
            ),
        )
        result = await coverage_auditor_node(
            {"file_path": "x.pdf", "extracted_flat_blocks": blocks}
        )
        worker.assert_called_once()
        assert worker.call_args.args[0]["current_page"] == 2
        assert result["extracted_flat_blocks"][0] == {"__replace_pages__": [2]}
