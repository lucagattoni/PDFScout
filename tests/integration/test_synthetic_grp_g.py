"""Group G — Layout / reading order (1 real Claude call).

Node under test: window_parser_node (extraction quality on multi-column layout).
Classifier mocked; hierarchy mocked; burst doesn't fire (1-page PDF).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration._compare import _make_relation_response


def _first_index(blocks: list, marker: str) -> int | None:
    """Index of the first block whose text contains marker (case-insensitive)."""
    for i, b in enumerate(blocks):
        if marker.lower() in b["text"].lower():
            return i
    return None


_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"
_GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


@pytest.mark.e2e
@pytest.mark.grp_g
class TestGroupG:
    async def test_g1_two_column_reading_order(self):
        """Left-column blocks should appear before right-column blocks in structured_payload."""
        from src.config import COLUMN_BUCKET_FRAC
        from src.graph import build_app

        golden = json.loads((_GOLDEN / "grp_g_two_column.json").read_text())

        app = build_app(checkpointer=None)
        with (
            patch(
                "src.nodes.classifier_node._classify",
                new=AsyncMock(
                    return_value=(
                        "baseline_core",
                        {
                            "context": "classifier",
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "stop_reason": "end_turn",
                        },
                    )
                ),
            ),
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
        xs = [b["bbox"]["coordinates"] for b in blocks]
        span = max(c[3] for c in xs) - min(c[1] for c in xs)
        bucket_w = max(span * COLUMN_BUCKET_FRAC, 1)
        buckets = [b["bbox"]["coordinates"][1] // bucket_w for b in blocks]
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

    async def test_g2_three_column_reading_order(self):
        """Three-column layout: col-1 blocks before col-2, col-2 before col-3."""
        import re
        import unicodedata

        from src.config import COLUMN_BUCKET_FRAC
        from src.graph import build_app

        golden = json.loads((_GOLDEN / "grp_g_three_column.json").read_text())

        app = build_app(checkpointer=None)
        with (
            patch(
                "src.nodes.classifier_node._classify",
                new=AsyncMock(
                    return_value=(
                        "baseline_core",
                        {
                            "context": "classifier",
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "stop_reason": "end_turn",
                        },
                    )
                ),
            ),
            patch(
                "src.nodes.hierarchy_node._call_api",
                new=AsyncMock(return_value=_make_relation_response([])),
            ),
        ):
            result = await app.ainvoke({"file_path": str(_PDFS / "grp_g_three_column.pdf")})

        blocks = result["hierarchical_document_tree"]["structured_payload"]

        xs = [b["bbox"]["coordinates"] for b in blocks]
        span = max(c[3] for c in xs) - min(c[1] for c in xs)
        bucket_w = max(span * COLUMN_BUCKET_FRAC, 1)
        buckets = [b["bbox"]["coordinates"][1] // bucket_w for b in blocks]
        unique_buckets = sorted(set(buckets))
        assert len(unique_buckets) >= 3, (
            f"Expected ≥3 column buckets, got {unique_buckets} — "
            "three-column layout may not have been detected"
        )

        col1_bucket = unique_buckets[0]
        col2_bucket = unique_buckets[1]
        col3_bucket = unique_buckets[2]

        col1_indices = [i for i, bkt in enumerate(buckets) if bkt == col1_bucket]
        col2_indices = [i for i, bkt in enumerate(buckets) if bkt == col2_bucket]
        col3_indices = [i for i, bkt in enumerate(buckets) if bkt == col3_bucket]

        assert col1_indices, "No blocks in col-1 bucket"
        assert col2_indices, "No blocks in col-2 bucket"
        assert col3_indices, "No blocks in col-3 bucket"

        assert max(col1_indices) < min(col2_indices), (
            f"All col-1 blocks must precede col-2 blocks in output. "
            f"Col-1 indices: {col1_indices}, col-2 indices: {col2_indices}"
        )
        assert max(col2_indices) < min(col3_indices), (
            f"All col-2 blocks must precede col-3 blocks in output. "
            f"Col-2 indices: {col2_indices}, col-3 indices: {col3_indices}"
        )

        def norm(s: str) -> str:
            return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).strip()).lower()

        for expected_text in golden["expected"]["texts"]:
            assert any(norm(expected_text) in norm(b["text"]) for b in blocks), (
                f"Expected text {expected_text!r} not found in any block"
            )

    async def test_g3_label_sidebar_interleaved_order(self):
        """Label-sidebar rows (real Enel p3 pattern): each label reads before
        its own full-width text, interleaved row by row - not text-then-label."""
        from src.graph import build_app

        golden = json.loads((_GOLDEN / "grp_g_label_sidebar.json").read_text())

        app = build_app(checkpointer=None)
        with (
            patch(
                "src.nodes.classifier_node._classify",
                new=AsyncMock(
                    return_value=(
                        "baseline_core",
                        {
                            "context": "classifier",
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "stop_reason": "end_turn",
                        },
                    )
                ),
            ),
            patch(
                "src.nodes.hierarchy_node._call_api",
                new=AsyncMock(return_value=_make_relation_response([])),
            ),
        ):
            result = await app.ainvoke({"file_path": str(_PDFS / "grp_g_label_sidebar.pdf")})

        blocks = result["hierarchical_document_tree"]["structured_payload"]
        positions = [_first_index(blocks, marker) for marker in golden["expected"]["order"]]
        assert None not in positions, (
            f"Missing markers: "
            f"{[m for m, p in zip(golden['expected']['order'], positions) if p is None]}"
        )
        assert positions == sorted(positions), (
            f"Expected reading order {golden['expected']['order']}, got positions {positions}"
        )

    async def test_g4_heading_adjacent_to_its_table(self):
        """A heading directly above a full-width table (real bill pattern) must
        stay adjacent to the table, after the intro and sidebar content."""
        from src.graph import build_app

        golden = json.loads((_GOLDEN / "grp_g_heading_table_sidebar.json").read_text())

        app = build_app(checkpointer=None)
        with (
            patch(
                "src.nodes.classifier_node._classify",
                new=AsyncMock(
                    return_value=(
                        "baseline_core",
                        {
                            "context": "classifier",
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "stop_reason": "end_turn",
                        },
                    )
                ),
            ),
            patch(
                "src.nodes.hierarchy_node._call_api",
                new=AsyncMock(return_value=_make_relation_response([])),
            ),
        ):
            result = await app.ainvoke(
                {"file_path": str(_PDFS / "grp_g_heading_table_sidebar.pdf")}
            )

        blocks = result["hierarchical_document_tree"]["structured_payload"]
        positions = [_first_index(blocks, marker) for marker in golden["expected"]["order"]]
        assert None not in positions, (
            f"Missing markers: "
            f"{[m for m, p in zip(golden['expected']['order'], positions) if p is None]}"
        )
        assert positions == sorted(positions), (
            f"Expected reading order {golden['expected']['order']}, got positions {positions}"
        )
        # Heading immediately before its table content (allow the table itself
        # to be one or two blocks, but nothing unrelated in between).
        head_pos = _first_index(blocks, golden["expected"]["adjacent"][0])
        table_pos = _first_index(blocks, golden["expected"]["adjacent"][1])
        assert table_pos - head_pos <= 2, (
            f"Heading (pos {head_pos}) must be adjacent to its table (pos {table_pos})"
        )
