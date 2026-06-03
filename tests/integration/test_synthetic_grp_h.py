"""Group H — Graceful degradation (1 real Claude call).

H1: blank page — pipeline must complete without exception and return ≤ 1 block.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration._compare import _make_relation_response

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"


@pytest.mark.e2e
@pytest.mark.grp_h
class TestGroupH:
    async def test_h1_blank_page(self):
        """Pipeline completes without exception on a blank page; returns ≤ 1 block."""
        from src.graph import build_app

        app = build_app(checkpointer=None)
        with (
            patch(
                "src.nodes.classifier_node._classify", new=AsyncMock(return_value="baseline_core")
            ),
            patch(
                "src.nodes.hierarchy_node._call_api",
                new=AsyncMock(return_value=_make_relation_response([])),
            ),
        ):
            result = await app.ainvoke({"file_path": str(_PDFS / "grp_h_blank.pdf")})

        blocks = result["hierarchical_document_tree"]["structured_payload"]
        assert len(blocks) <= 1, f"Expected ≤ 1 block for blank page, got {len(blocks)}"
        if blocks:
            assert len(blocks[0]["text"].strip()) < 30, (
                f"Block text on blank page should be < 30 chars, "
                f"got {len(blocks[0]['text'].strip())!r}: {blocks[0]['text']!r}"
            )
