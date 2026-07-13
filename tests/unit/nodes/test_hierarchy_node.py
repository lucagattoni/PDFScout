from unittest.mock import AsyncMock, MagicMock

import pytest

from src.nodes.hierarchy_node import geometric_pre_sorter, layout_hierarchy_agent_node


def _grid_block(block_id: str, ymin: int, xmin: int, xmax: int) -> dict:
    return {
        "block_id": block_id,
        "type": "paragraph",
        "text": "x",
        "bbox": {"page_number": 1, "coordinates": [ymin, xmin, ymin + 10, xmax]},
    }


def _make_relation_response(relations: list):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"relations": relations}
    response = MagicMock()
    response.content = [tool_block]
    return response


def _make_text_only_response():
    text_block = MagicMock()
    text_block.type = "text"
    response = MagicMock()
    response.content = [text_block]
    return response


class TestGeometricPreSorter:
    def test_single_block_unchanged(self, sample_block):
        result = geometric_pre_sorter([sample_block])
        assert result == [sample_block]

    def test_sorts_by_page_number(self):
        b1 = {
            "block_id": "b1",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 2, "coordinates": [0, 0, 10, 10]},
        }
        b2 = {
            "block_id": "b2",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [0, 0, 10, 10]},
        }
        result = geometric_pre_sorter([b1, b2])
        assert result[0]["block_id"] == "b2"
        assert result[1]["block_id"] == "b1"

    def test_sorts_by_ymin_within_column(self):
        b1 = {
            "block_id": "b1",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [200, 10, 250, 50]},
        }
        b2 = {
            "block_id": "b2",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [50, 10, 100, 50]},
        }
        result = geometric_pre_sorter([b1, b2])
        assert result[0]["block_id"] == "b2"
        assert result[1]["block_id"] == "b1"

    def test_sorts_by_column_bucket(self):
        # xmin=10 → bucket 0, xmin=100 → bucket 2 (with COLUMN_BUCKET_PX=50)
        b1 = {
            "block_id": "b1",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [0, 100, 10, 150]},
        }
        b2 = {
            "block_id": "b2",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [0, 10, 10, 60]},
        }
        result = geometric_pre_sorter([b1, b2])
        assert result[0]["block_id"] == "b2"
        assert result[1]["block_id"] == "b1"

    def test_full_width_block_starts_a_band(self):
        # Two-column rows split by a full-width divider: the divider ends the
        # first band; blocks below it read after both top-row columns.
        # Page x-span here is 0..100, so full-width = width >= 60.
        left_top = _grid_block("lt", 10, 0, 40)  # band 0, left
        right_top = _grid_block("rt", 10, 60, 100)  # band 0, right
        divider = _grid_block("dv", 40, 0, 100)  # full-width → starts band 1
        left_bot = _grid_block("lb", 70, 0, 40)  # band 1, left
        right_bot = _grid_block("rb", 70, 60, 100)  # band 1, right
        result = geometric_pre_sorter([right_bot, divider, left_top, right_top, left_bot])
        assert [b["block_id"] for b in result] == ["lt", "rt", "dv", "lb", "rb"]

    def test_real_invoice_banded_order(self):
        # Regression fixture: the 18 blocks of the real aruba invoice
        # (coordinates [ymin, xmin, ymax, xmax]). Full-width tables/footer band
        # the page; side-by-side form fields read left-group then right-group.
        raw = [
            ("b1", 28, 28, 95, 200),
            ("b2", 28, 210, 95, 620),
            ("b3", 110, 28, 125, 100),
            ("b4", 125, 28, 230, 430),
            ("b5", 230, 28, 270, 430),
            ("b6", 110, 470, 125, 620),
            ("b7", 125, 470, 230, 870),
            ("b8", 295, 28, 345, 870),
            ("b9", 360, 28, 375, 150),
            ("b10", 375, 28, 460, 430),
            ("b11", 360, 470, 375, 700),
            ("b12", 375, 470, 395, 700),
            ("b13", 490, 28, 560, 870),
            ("b14", 580, 28, 650, 870),
            ("b15", 665, 28, 760, 430),
            ("b16", 665, 470, 685, 700),
            ("b17", 685, 470, 760, 870),
            ("b18", 820, 28, 840, 870),
        ]
        blocks = [
            {
                "block_id": bid,
                "type": "paragraph",
                "text": "x",
                "bbox": {"page_number": 1, "coordinates": [ymin, xmin, ymax, xmax]},
            }
            for bid, ymin, xmin, ymax, xmax in raw
        ]
        result = [b["block_id"] for b in geometric_pre_sorter(blocks)]
        assert result == [
            "b1", "b3", "b4", "b5", "b2", "b6", "b7",  # top band: left group then right group
            "b8",  # full-width Document table starts band 1
            "b9", "b10", "b11", "b12",  # Payment (left) / due-date (right)
            "b13", "b14",  # full-width line-item + VAT tables
            "b15", "b16", "b17",  # TOTAL (left) / notes (right)
            "b18",  # full-width footer
        ]


class TestLayoutHierarchyAgentNode:
    async def test_none_blocks_raises_type_error(self, sample_state):
        state = {**sample_state, "extracted_flat_blocks": None}
        with pytest.raises(TypeError):
            await layout_hierarchy_agent_node(state)

    async def test_empty_blocks_skips_api(self, sample_state, mocker):
        mock_class = mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        state = {**sample_state, "extracted_flat_blocks": []}
        result = await layout_hierarchy_agent_node(state)
        mock_client.messages.create.assert_not_called()
        assert result["hierarchical_document_tree"]["structured_payload"] == []

    async def test_single_block_skips_api_and_sets_parent_none(
        self, sample_state, sample_block, mocker
    ):
        mock_class = mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        state = {**sample_state, "extracted_flat_blocks": [sample_block]}
        result = await layout_hierarchy_agent_node(state)
        mock_client.messages.create.assert_not_called()
        payload = result["hierarchical_document_tree"]["structured_payload"]
        assert len(payload) == 1
        assert payload[0]["parent_id"] is None

    async def test_multiple_blocks_with_api_response(self, sample_state, sample_block, mocker):
        block2 = {
            **sample_block,
            "block_id": "blk-002",
            "bbox": {**sample_block["bbox"], "coordinates": [200, 50, 300, 80]},
        }
        relations = [
            {"block_id": "blk-001", "parent_id": None},
            {"block_id": "blk-002", "parent_id": "blk-001"},
        ]
        mock_class = mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        mock_client.messages.create = AsyncMock(return_value=_make_relation_response(relations))
        state = {**sample_state, "extracted_flat_blocks": [sample_block, block2]}
        result = await layout_hierarchy_agent_node(state)
        payload = result["hierarchical_document_tree"]["structured_payload"]
        by_id = {b["block_id"]: b for b in payload}
        assert by_id["blk-001"]["parent_id"] is None
        assert by_id["blk-002"]["parent_id"] == "blk-001"

    async def test_duplicate_block_ids_deduplicated(self, sample_state, sample_block, mocker):
        mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        state = {**sample_state, "extracted_flat_blocks": [sample_block, sample_block]}
        result = await layout_hierarchy_agent_node(state)
        payload = result["hierarchical_document_tree"]["structured_payload"]
        assert len(payload) == 1

    async def test_missing_from_relation_map_gets_orphan_warning(
        self, sample_state, sample_block, mocker
    ):
        block2 = {
            **sample_block,
            "block_id": "blk-002",
            "bbox": {**sample_block["bbox"], "coordinates": [200, 50, 300, 80]},
        }
        # Only blk-001 in relation map; blk-002 is missing
        relations = [{"block_id": "blk-001", "parent_id": None}]
        mock_class = mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        mock_client.messages.create = AsyncMock(return_value=_make_relation_response(relations))
        state = {**sample_state, "extracted_flat_blocks": [sample_block, block2]}
        result = await layout_hierarchy_agent_node(state)
        payload = result["hierarchical_document_tree"]["structured_payload"]
        by_id = {b["block_id"]: b for b in payload}
        assert by_id["blk-002"]["parent_id"] is None
        assert any("blk-002" in w for w in result["extraction_warnings"])

    async def test_no_tool_use_raises(self, sample_state, sample_block, mocker):
        block2 = {
            **sample_block,
            "block_id": "blk-002",
            "bbox": {**sample_block["bbox"], "coordinates": [200, 50, 300, 80]},
        }
        mock_class = mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        mock_client.messages.create = AsyncMock(return_value=_make_text_only_response())
        mocker.patch("tenacity.nap.sleep")
        state = {**sample_state, "extracted_flat_blocks": [sample_block, block2]}
        with pytest.raises(ValueError):
            await layout_hierarchy_agent_node(state)
