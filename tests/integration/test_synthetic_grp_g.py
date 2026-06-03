"""Group G — Layout / reading order (1 real Claude call).

Node under test: window_parser_node (extraction quality on multi-column layout).
Classifier mocked; hierarchy mocked; burst doesn't fire (1-page PDF).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration._compare import _make_relation_response

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"
_GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


@pytest.mark.e2e
@pytest.mark.grp_g
class TestGroupG:
    async def test_g1_two_column_reading_order(self):
        """Left-column blocks should appear before right-column blocks in structured_payload."""
        from src.config import COLUMN_BUCKET_PX
        from src.graph import build_app

        golden = json.loads((_GOLDEN / "grp_g_two_column.json").read_text())

        app = build_app(checkpointer=None)
        with (
            patch("src.nodes.classifier_node._classify", new=AsyncMock(return_value="baseline_core")),
            patch(
                "src.nodes.hierarchy_node._call_api",
                new=AsyncMock(return_value=_make_relation_response([])),
            ),
        ):
            result = await app.ainvoke({"file_path": str(_PDFS / "grp_g_two_column.pdf")})

        blocks = result["hierarchical_document_tree"]["structured_payload"]

        # (1) Column ordering: all left-column blocks before all right-column blocks.
        # Identify the two columns by their natural xmin bucket split rather than
        # hardcoding specific bucket numbers (Claude's coordinate output varies slightly).
        buckets = [b["bbox"]["coordinates"][1] // COLUMN_BUCKET_PX for b in blocks]
        unique_buckets = sorted(set(buckets))
        assert len(unique_buckets) >= 2, f"Expected ≥2 column buckets, got {unique_buckets}"
        left_bucket = unique_buckets[0]

        left_indices = [i for i, bkt in enumerate(buckets) if bkt == left_bucket]
        right_indices = [i for i, bkt in enumerate(buckets) if bkt != left_bucket]
        assert left_indices, "No blocks found in left column"
        assert right_indices, "No blocks found in right column"
        assert max(left_indices) < min(right_indices), (
            "All left-column blocks must appear before all right-column blocks "
            f"in structured_payload. Left indices: {left_indices}, right indices: {right_indices}"
        )

        # (2) & (3) All expected texts present in some block
        import re
        import unicodedata

        def norm(s: str) -> str:
            return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).strip()).lower()

        for expected_text in golden["expected"]["texts"]:
            assert any(norm(expected_text) in norm(b["text"]) for b in blocks), (
                f"Expected text {expected_text!r} not found in any block"
            )
