from src.nodes.coverage_node import (
    audit_page_coverage,
    native_layer_usable,
    significant_words,
)


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
_GARBLED = "\x01\x1b#%\x17)\x19\x02\x06(\x15'\x11\x18\x0e\x1a 9988\x01=988\x02$0 \x061122334455 " * 5


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
