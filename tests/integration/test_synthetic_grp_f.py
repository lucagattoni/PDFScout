"""Group F — Hierarchy assignment quality (narrow tests, no PDF required).

Node under test: layout_hierarchy_agent_node called directly as a function.
Real hierarchy LLM call. No graph, no PDF, no classifier.
"""

import pytest

from tests.fixtures.generators.grp_f_hierarchy import (
    F1_BLOCKS,
    F2_BLOCKS,
    F3_BLOCKS,
    F4_BLOCKS,
    F5_BLOCKS,
    make_state,
)
from tests.integration._compare import (
    HierarchyRule,
    assert_hierarchy_structure,
    assert_nearest_heading_parent,
)


@pytest.mark.e2e
@pytest.mark.grp_f
class TestGroupF:
    async def test_f1_heading_paragraph(self):
        """[heading, paragraph] → paragraph under heading; heading at root."""
        from src.nodes.hierarchy_node import layout_hierarchy_agent_node

        result = await layout_hierarchy_agent_node(make_state(list(F1_BLOCKS)))
        blocks = result["hierarchical_document_tree"]["structured_payload"]

        heading = next(b for b in blocks if b["type"] == "heading")
        paragraph = next(b for b in blocks if b["type"] == "paragraph")

        assert heading["parent_id"] is None, "heading should be root-level"
        assert paragraph["parent_id"] == heading["block_id"], (
            f"paragraph.parent_id should be {heading['block_id']!r}, got {paragraph['parent_id']!r}"
        )

    async def test_f2_heading_with_paragraph_and_table(self):
        """[heading, paragraph, paragraph, table] → all three under heading."""
        from src.nodes.hierarchy_node import layout_hierarchy_agent_node

        result = await layout_hierarchy_agent_node(make_state(list(F2_BLOCKS)))
        blocks = result["hierarchical_document_tree"]["structured_payload"]
        assert_hierarchy_structure(
            blocks,
            [
                HierarchyRule("paragraph", "heading"),
                HierarchyRule("table", "heading"),
            ],
        )

    async def test_f3_title_heading_paragraph(self):
        """[title, heading, paragraph] → title at root; heading at root; paragraph under heading."""
        from src.nodes.hierarchy_node import layout_hierarchy_agent_node

        result = await layout_hierarchy_agent_node(make_state(list(F3_BLOCKS)))
        blocks = result["hierarchical_document_tree"]["structured_payload"]
        assert_hierarchy_structure(
            blocks,
            [
                HierarchyRule("title", None),
                HierarchyRule("heading", None),
                HierarchyRule("paragraph", "heading"),
            ],
        )

    async def test_f4_multi_heading_disambiguation(self):
        """[hA, pA1, pA2, hB, pB1, pB2] → each paragraph under its nearest preceding heading."""
        from src.nodes.hierarchy_node import layout_hierarchy_agent_node

        result = await layout_hierarchy_agent_node(make_state(list(F4_BLOCKS)))
        blocks = result["hierarchical_document_tree"]["structured_payload"]
        assert_nearest_heading_parent(blocks)

    async def test_f5_cross_page_continuation(self):
        """[page-1 is_continued para, page-2 para] → page-2 block is child of page-1 block
        (hierarchy Rule 2)."""
        from src.nodes.hierarchy_node import layout_hierarchy_agent_node

        result = await layout_hierarchy_agent_node(make_state(list(F5_BLOCKS)))
        blocks = result["hierarchical_document_tree"]["structured_payload"]
        by_id = {b["block_id"]: b for b in blocks}

        assert by_id["p1c"]["parent_id"] is None, (
            "Page-1 fragment should be root-level (no preceding heading)"
        )
        assert by_id["p2c"]["parent_id"] == "p1c", (
            f"Expected page-2 continuation parent_id='p1c', "
            f"got {by_id['p2c']['parent_id']!r} — hierarchy Rule 2 may not have triggered"
        )
