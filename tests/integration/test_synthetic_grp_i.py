"""Group I — Full-chain integration (no LLM tier mocked).

Only the classifier is mocked; window_parser_node and layout_hierarchy_agent_node
both make real API calls.

These tests cover the gap between E-group (hierarchy mocked) and F-group
(pre-built blocks, no extraction): verifying that extraction and hierarchy
work correctly in a single pipeline run.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"


@pytest.mark.e2e
@pytest.mark.grp_i
class TestGroupI:
    async def test_i1_continuation_full_chain(self):
        """Cross-page paragraph: extraction sets is_continued=True on the page-1 fragment;
        hierarchy Rule 2 assigns the page-2 continuation as its child.
        Only classifier is mocked — both LLM tiers are real calls."""
        from src.graph import build_app

        app = build_app(checkpointer=None)
        with patch(
            "src.nodes.classifier_node._classify",
            new=AsyncMock(return_value="baseline_core"),
        ):
            result = await app.ainvoke({"file_path": str(_PDFS / "grp_e_continuation.pdf")})

        blocks = result["hierarchical_document_tree"]["structured_payload"]
        page1 = [b for b in blocks if b["bbox"]["page_number"] == 1]
        page2 = [b for b in blocks if b["bbox"]["page_number"] == 2]

        assert page1, "No blocks found on page 1"
        assert page2, "No blocks found on page 2"

        continued = [b for b in page1 if b.get("is_continued") is True]
        assert len(continued) == 1, (
            f"Expected exactly 1 is_continued=True block on page 1, got {len(continued)}"
        )
        fragment = continued[0]

        continuation = min(page2, key=lambda b: b["bbox"]["coordinates"][0])
        assert continuation["parent_id"] == fragment["block_id"], (
            f"Expected page-2 continuation parent_id={fragment['block_id']!r}, "
            f"got {continuation['parent_id']!r} — hierarchy Rule 2 may not have triggered"
        )
