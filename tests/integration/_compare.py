"""Shared assertion helpers and mock factories for synthetic integration tests."""

import re
import unicodedata
from typing import NamedTuple
from unittest.mock import MagicMock


class HierarchyRule(NamedTuple):
    child_type: str                    # block["type"] to match
    expected_parent_type: str | None   # None asserts parent_id is None (top-level)


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

def _make_tool_use_response(blocks: list) -> MagicMock:
    """Mock Anthropic response for worker/pioneer node.
    Moved here from test_graph_pipeline.py so all group tests can import without
    cross-test-file imports."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"blocks": blocks}
    response = MagicMock()
    response.content = [tool_block]
    return response


def _valid_block(page: int = 1) -> dict:
    """Minimal valid block for use as a worker mock return value.
    Includes all required fields (block_id, type, text, bbox, is_continued, metadata)
    and passes baseline_core, invoice, and scientific_paper schema validation so that
    pioneer_validation_route does not trigger retries in B tests."""
    return {
        "block_id": f"blk-p{page}",
        "type": "paragraph",
        "text": f"Content on page {page}.",
        "bbox": {"page_number": page, "coordinates": [50, 50, 100, 500]},
        "is_continued": False,
        "metadata": {},
    }


def _make_relation_response(relations: list) -> MagicMock:
    """Mock Anthropic response for hierarchy node.
    Moved here from test_graph_pipeline.py so all group tests can import without
    cross-test-file imports."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"relations": relations}
    response = MagicMock()
    response.content = [tool_block]
    return response


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Strip, collapse internal whitespace, and normalise unicode."""
    text = unicodedata.normalize("NFKC", text)
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    # normalise curly quotes → straight quotes
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    return text


# ---------------------------------------------------------------------------
# Block assertion helpers
# ---------------------------------------------------------------------------

def assert_blocks_match(
    expected: list[dict],
    actual: list[dict],
    *,
    check_bbox: bool = False,
    bbox_tolerance_pct: float = 0.05,
    normalize_text: bool = True,
) -> None:
    """Positional block matching: expected[i] compared against actual[i].

    - check_bbox=False: bbox assertions not viable; Phase 1 calibration confirmed non-linear/non-deterministic coordinates (see calibration_notes.md).
    - normalize_text: strip + collapse whitespace, normalise unicode quotes. No lowercasing.
    - bbox_tolerance_pct applies to the block's own dimension, not page dimension.
    """
    assert len(actual) >= len(expected), (
        f"Got {len(actual)} blocks, expected at least {len(expected)}"
    )
    for i, exp in enumerate(expected):
        act = actual[i]
        if "type" in exp:
            assert act["type"] == exp["type"], (
                f"Block {i}: type mismatch: got {act['type']!r}, expected {exp['type']!r}"
            )
        if "text" in exp:
            exp_text = _normalize(exp["text"]) if normalize_text else exp["text"]
            act_text = _normalize(act["text"]) if normalize_text else act["text"]
            assert exp_text in act_text or act_text == exp_text, (
                f"Block {i}: text mismatch:\n  expected: {exp_text!r}\n  got:      {act_text!r}"
            )
        if check_bbox and "bbox" in exp and "bbox" in act:
            _assert_bbox(i, exp["bbox"], act["bbox"], bbox_tolerance_pct)


def _assert_bbox(
    idx: int, expected_bbox: dict, actual_bbox: dict, tolerance_pct: float
) -> None:
    assert expected_bbox["page_number"] == actual_bbox["page_number"], (
        f"Block {idx}: bbox page_number mismatch"
    )
    exp_coords = expected_bbox["coordinates"]
    act_coords = actual_bbox["coordinates"]
    dims = [
        exp_coords[2] - exp_coords[0],  # height (ymax - ymin)
        exp_coords[3] - exp_coords[1],  # width  (xmax - xmin)
        exp_coords[2] - exp_coords[0],  # height again for ymax
        exp_coords[3] - exp_coords[1],  # width  again for xmax
    ]
    for j, (e, a, dim) in enumerate(zip(exp_coords, act_coords, dims)):
        tol = max(5, abs(dim) * tolerance_pct)
        assert abs(e - a) <= tol, (
            f"Block {idx}: coordinate[{j}] out of tolerance: "
            f"expected {e}, got {a}, tolerance ±{tol:.1f}"
        )


def assert_table_data(
    block: dict,
    expected_rows: int,
    expected_cols: int,
    header_row_count: int = 1,
    expected_values: list[str] | None = None,
) -> None:
    """Validate metadata.table_data dimensions and header flags.

    expected_rows is the TOTAL row count including header rows
    (e.g., 1 header + 3 data rows = 4).
    header_row_count rows starting from index 0 must have is_header=True; the rest False.
    When expected_values is provided, each string must appear in at least one cell's value.
    """
    td = block.get("metadata", {}).get("table_data")
    assert td is not None, "metadata.table_data is missing"
    assert td["total_rows"] == expected_rows, (
        f"table_data.total_rows: got {td['total_rows']}, expected {expected_rows}"
    )
    assert td["total_cols"] == expected_cols, (
        f"table_data.total_cols: got {td['total_cols']}, expected {expected_cols}"
    )
    cells = td["cells"]
    for r in range(header_row_count):
        row_cells = [c for c in cells if c["r"] == r]
        for cell in row_cells:
            assert cell.get("is_header", False), (
                f"table_data cell at row {r} should have is_header=True"
            )
    for r in range(header_row_count, expected_rows):
        row_cells = [c for c in cells if c["r"] == r]
        for cell in row_cells:
            assert not cell.get("is_header", False), (
                f"table_data cell at row {r} should have is_header=False"
            )
    if expected_values:
        all_values = [c["value"] for c in cells]
        for val in expected_values:
            assert any(val in v for v in all_values), (
                f"Expected value {val!r} not found in any table cell"
            )


def assert_hierarchy_structure(blocks: list[dict], rules: list[HierarchyRule]) -> None:
    """Check parent-child relationships without pinning exact block_id values.

    Each rule applies to ALL blocks of the given child_type, not just some.
    When expected_parent_type is None, asserts block["parent_id"] is None (top-level).
    When non-None, looks up the parent by parent_id and asserts
    parent["type"] == expected_parent_type.
    """
    by_id = {b["block_id"]: b for b in blocks}
    for rule in rules:
        matching = [b for b in blocks if b["type"] == rule.child_type]
        assert matching, f"No blocks of type {rule.child_type!r} found"
        for block in matching:
            if rule.expected_parent_type is None:
                assert block["parent_id"] is None, (
                    f"Block {block['block_id']!r} (type={rule.child_type!r}) "
                    f"expected parent_id=None, got {block['parent_id']!r}"
                )
            else:
                pid = block["parent_id"]
                assert pid is not None, (
                    f"Block {block['block_id']!r} (type={rule.child_type!r}) "
                    f"expected parent of type {rule.expected_parent_type!r} but parent_id is None"
                )
                parent = by_id.get(pid)
                assert parent is not None, (
                    f"Block {block['block_id']!r} has parent_id={pid!r} "
                    "which is not in the block list"
                )
                assert parent["type"] == rule.expected_parent_type, (
                    f"Block {block['block_id']!r} (type={rule.child_type!r}) "
                    f"parent type: got {parent['type']!r}, "
                    f"expected {rule.expected_parent_type!r}"
                )


def assert_nearest_heading_parent(blocks: list[dict]) -> None:
    """For each paragraph block, assert its parent_id points to the nearest preceding
    heading in the sorted block list (which must already be in geometric sort order).

    Raises AssertionError if any paragraph's parent is not its nearest heading.
    A paragraph with no preceding heading raises AssertionError — the fixture
    must ensure at least one heading appears before the first paragraph.
    """
    for i, block in enumerate(blocks):
        if block["type"] != "paragraph":
            continue
        # Find nearest preceding heading
        nearest_heading = None
        for j in range(i - 1, -1, -1):
            if blocks[j]["type"] == "heading":
                nearest_heading = blocks[j]
                break
        assert nearest_heading is not None, (
            f"Paragraph {block['block_id']!r} has no preceding heading — "
            "fixture must place at least one heading before the first paragraph"
        )
        assert block["parent_id"] == nearest_heading["block_id"], (
            f"Paragraph {block['block_id']!r} parent_id={block['parent_id']!r} "
            f"but nearest heading is {nearest_heading['block_id']!r}"
        )
