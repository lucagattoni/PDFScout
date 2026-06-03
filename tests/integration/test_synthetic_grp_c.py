"""Group C — Block-type extraction (1–2 real Claude calls per test).

Node under test: window_parser_node (pioneer, 1-page PDFs so burst never fires).
Classifier mocked via _classify patch; hierarchy mocked via _call_api patch.
All assertions use scan-based matching (>= minimum count, text in some block).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration._compare import _make_relation_response, assert_valid_bbox_fields

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"


async def _run_c_test(pdf_path: str, doc_type: str = "baseline_core") -> list[dict]:
    from src.graph import build_app

    app = build_app(checkpointer=None)
    with (
        patch("src.nodes.classifier_node._classify", new=AsyncMock(return_value=doc_type)),
        patch(
            "src.nodes.hierarchy_node._call_api",
            new=AsyncMock(return_value=_make_relation_response([])),
        ),
    ):
        result = await app.ainvoke({"file_path": pdf_path})
    return result["hierarchical_document_tree"]["structured_payload"]


def _text_in_some_block(text: str, blocks: list[dict], normalize: bool = True) -> bool:
    import re
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s).strip()
        return re.sub(r"\s+", " ", s).lower()

    target = norm(text) if normalize else text.lower()
    return any(target in norm(b["text"]) for b in blocks)


@pytest.mark.e2e
@pytest.mark.grp_c
class TestGroupC:
    async def test_c1_paragraph(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_paragraph.pdf"))
        assert len(blocks) >= 1
        assert _text_in_some_block("quick brown fox", blocks)
        assert_valid_bbox_fields(blocks)

    async def test_c2_title(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_title.pdf"))
        assert len(blocks) >= 1
        assert any(b["type"] == "title" for b in blocks)
        assert _text_in_some_block("Synthetic Document Analysis", blocks)

    async def test_c3_heading(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_heading.pdf"))
        assert len(blocks) >= 1
        assert any(b["type"] == "heading" for b in blocks)
        assert _text_in_some_block("Introduction", blocks)

    async def test_c4_list_items(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_list_items.pdf"))
        assert len(blocks) >= 3
        list_blocks = [b for b in blocks if b["type"] == "list_item"]
        assert len(list_blocks) >= 3
        for item in ["First list item", "Second list item", "Third list item"]:
            assert _text_in_some_block(item, blocks)

    async def test_c5_footnote(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_footnote.pdf"))
        assert len(blocks) >= 2
        assert any(b["type"] == "footnote" for b in blocks)

    async def test_c6_margin_element(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_margin_element.pdf"))
        assert any(b["type"] == "margin_element" for b in blocks)

    async def test_c7_table(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_table.pdf"))
        table_blocks = [b for b in blocks if b["type"] == "table"]
        assert len(table_blocks) >= 1
        assert any(b["text"].strip() for b in table_blocks), (
            "table block should have non-empty text"
        )

    async def test_c8_figure(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_figure.pdf"))
        # Passes if any block mentions "Figure 1:" (type may be figure or paragraph)
        assert _text_in_some_block("Figure 1", blocks), (
            "Expected some block to contain 'Figure 1:' but none did"
        )

    async def test_c9_long_paragraph(self):
        blocks = await _run_c_test(str(_PDFS / "grp_c_long_paragraph.pdf"))
        assert len(blocks) >= 1
        assert _text_in_some_block("synthetic document generation", blocks)
        assert _text_in_some_block("splitting it at arbitrary boundaries", blocks)

    async def test_c10_unicode(self):
        """Paragraph with Latin-1 extended chars → extracted text contains accented terms."""
        blocks = await _run_c_test(str(_PDFS / "grp_c_unicode.pdf"))
        assert len(blocks) >= 1
        # Accept either unicode-preserved or ASCII-normalized form
        assert _text_in_some_block("naïve", blocks) or _text_in_some_block("naive", blocks), (
            "Expected naïve/naive in extracted text"
        )
        assert _text_in_some_block("café", blocks) or _text_in_some_block("cafe", blocks), (
            "Expected café/cafe in extracted text"
        )

    async def test_c12_emphasis(self):
        """Page with normal / bold / italic / bold-italic text → all variants extracted."""
        blocks = await _run_c_test(str(_PDFS / "grp_c_emphasis.pdf"))
        assert len(blocks) >= 1
        assert _text_in_some_block("Normal text", blocks), "Normal text not found"
        assert _text_in_some_block("Bold text", blocks), "Bold text not found"
        assert _text_in_some_block("Italic text", blocks), "Italic text not found"
        assert _text_in_some_block("Bold italic text", blocks), "Bold italic text not found"
