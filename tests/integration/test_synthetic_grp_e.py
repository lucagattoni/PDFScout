"""Group E — Multi-page pipeline / burst + merge (N real Claude calls per test).

Nodes under test: burst_dispatcher_node, window_parser_node (pages 2-N), merge_flat_blocks.
Classifier mocked; hierarchy mocked; worker NOT mocked (real LLM calls per page).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration._compare import _make_relation_response

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"


async def _run_e_test(pdf_path: str) -> list[dict]:
    from src.graph import build_app

    app = build_app(checkpointer=None)
    with (
        patch("src.nodes.classifier_node._classify", new=AsyncMock(return_value="baseline_core")),
        patch(
            "src.nodes.hierarchy_node._call_api",
            new=AsyncMock(return_value=_make_relation_response([])),
        ),
    ):
        result = await app.ainvoke({"file_path": pdf_path})
    return result["hierarchical_document_tree"]["structured_payload"]


@pytest.mark.e2e
@pytest.mark.grp_e
class TestGroupE:
    async def test_e1_two_page(self):
        """2-page doc: at least one block per page, no duplicate block_ids."""
        blocks = await _run_e_test(str(_PDFS / "grp_e_2page.pdf"))
        pages = {b["bbox"]["page_number"] for b in blocks}
        assert 1 in pages, "No blocks found from page 1"
        assert 2 in pages, "No blocks found from page 2"
        block_ids = [b["block_id"] for b in blocks]
        assert len(block_ids) == len(set(block_ids)), "Duplicate block_ids after merge"

    async def test_e2_five_page(self):
        """5-page doc: at least one block from each page, no duplicate block_ids."""
        blocks = await _run_e_test(str(_PDFS / "grp_e_5page.pdf"))
        pages = {b["bbox"]["page_number"] for b in blocks}
        for expected_page in range(1, 6):
            assert expected_page in pages, f"No blocks found from page {expected_page}"
        block_ids = [b["block_id"] for b in blocks]
        assert len(block_ids) == len(set(block_ids)), "Duplicate block_ids after merge"

    async def test_e3_continuation(self):
        """Paragraph split across pages: page-1 fragment has is_continued=True.
        Hierarchy is mocked (E-group convention); only extraction is asserted."""
        blocks = await _run_e_test(str(_PDFS / "grp_e_continuation.pdf"))

        page1_blocks = [b for b in blocks if b["bbox"]["page_number"] == 1]
        page2_blocks = [b for b in blocks if b["bbox"]["page_number"] == 2]
        assert page1_blocks, "No blocks found on page 1"
        assert page2_blocks, "No blocks found on page 2"

        continued = [b for b in page1_blocks if b.get("is_continued") is True]
        assert continued, (
            "No page-1 block has is_continued=True — extraction prompt instruction "
            "or schema description may be insufficient"
        )
        assert len(continued) == 1, (
            f"Expected exactly 1 is_continued=True block on page 1, got {len(continued)}"
        )
