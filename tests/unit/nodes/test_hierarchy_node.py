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


def _stream_cm(response):
    """Mimic hierarchy_node's ``client.messages.stream(...)`` — an async context
    manager whose ``get_final_message()`` returns the final Message."""
    inner = MagicMock()
    inner.get_final_message = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


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
        # buckets are span-relative: xmin=10 and xmin=100 land in different buckets
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
            "b1",
            "b3",
            "b4",
            "b5",
            "b2",
            "b6",
            "b7",  # top band: left group then right group
            "b8",  # full-width Document table starts band 1
            "b9",
            "b10",
            "b11",
            "b12",  # Payment (left) / due-date (right)
            "b13",
            "b14",  # full-width line-item + VAT tables
            "b15",
            "b16",
            "b17",  # TOTAL (left) / notes (right)
            "b18",  # full-width footer
        ]

    def test_label_left_of_full_width_block_reads_first(self):
        # Sidebar-label layout (real Enel invoice p3): narrow label column at
        # x0-14, full-width text blocks at x15-100. The label must read before
        # the wide text at the same y — full-width blocks no longer lead their band.
        label_a = {
            "block_id": "la",
            "type": "heading",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [120, 0, 300, 140]},
        }
        text_a = {
            "block_id": "ta",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [100, 150, 400, 1000]},
        }
        label_b = {
            "block_id": "lb",
            "type": "heading",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [520, 0, 700, 140]},
        }
        text_b = {
            "block_id": "tb",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [500, 150, 800, 1000]},
        }
        result = [b["block_id"] for b in geometric_pre_sorter([text_b, label_a, text_a, label_b])]
        assert result == ["la", "ta", "lb", "tb"]

    def test_heading_above_full_width_table_pulled_into_band(self):
        # A heading directly above a full-width table joins the table's band
        # (adjacent in output) instead of being stranded before sidebar content
        # (real Enel p1 "DETTAGLIO FISCALE" / Irish bill p2 "Payments" pattern).
        heading = {
            "block_id": "h",
            "type": "heading",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [800, 0, 975, 300]},
        }
        sidebar = {
            "block_id": "s",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [100, 700, 600, 1000]},
        }
        table = {
            "block_id": "t",
            "type": "table",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [1000, 0, 1600, 1000]},
        }
        result = [b["block_id"] for b in geometric_pre_sorter([table, sidebar, heading])]
        assert result == ["s", "h", "t"]

    def test_paragraph_above_full_width_table_not_pulled(self):
        # Only heading/title blocks are pulled down — an ordinary paragraph
        # just above a table stays with its own column/band.
        para = {
            "block_id": "p",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [800, 0, 975, 300]},
        }
        sidebar = {
            "block_id": "s",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [100, 700, 600, 1000]},
        }
        table = {
            "block_id": "t",
            "type": "table",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [1000, 0, 1600, 1000]},
        }
        result = [b["block_id"] for b in geometric_pre_sorter([table, sidebar, para])]
        assert result == ["p", "s", "t"]

    def test_empty_input_returns_empty(self):
        assert geometric_pre_sorter([]) == []

    def test_zero_x_span_sorts_by_y(self):
        # Degenerate geometry: all blocks share one x — no bands, pure y order.
        blocks = [
            {
                "block_id": f"b{y}",
                "type": "paragraph",
                "text": "x",
                "bbox": {"page_number": 1, "coordinates": [y, 50, y + 10, 50]},
            }
            for y in (300, 100, 200)
        ]
        result = [b["block_id"] for b in geometric_pre_sorter(blocks)]
        assert result == ["b100", "b200", "b300"]

    def test_deterministic_on_identical_coordinates(self):
        # Ties break on block_id — same input always yields the same order.
        blocks = [
            {
                "block_id": bid,
                "type": "paragraph",
                "text": "x",
                "bbox": {"page_number": 1, "coordinates": [100, 0, 120, 900]},
            }
            for bid in ("z", "a", "m")
        ]
        first = [b["block_id"] for b in geometric_pre_sorter(list(blocks))]
        second = [b["block_id"] for b in geometric_pre_sorter(list(reversed(blocks)))]
        assert first == second == ["a", "m", "z"]

    def test_heading_with_jittered_overlap_still_pulled(self):
        # BBox noise: heading ymax slightly BELOW the table's ymin boundary
        # (overlapping it) must still be pulled — tolerance is symmetric.
        heading = {
            "block_id": "h",
            "type": "heading",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [950, 0, 1010, 300]},
        }
        sidebar = {
            "block_id": "s",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [100, 700, 600, 1000]},
        }
        table = {
            "block_id": "t",
            "type": "table",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [1000, 0, 1600, 1000]},
        }
        result = [b["block_id"] for b in geometric_pre_sorter([table, sidebar, heading])]
        assert result == ["s", "h", "t"]

    def test_heading_above_stacked_tables_joins_nearest(self):
        # Two consecutive full-width tables: the heading must join the FIRST
        # (nearest) one and read before it — not get pulled past it.
        heading = {
            "block_id": "h",
            "type": "heading",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [800, 0, 975, 300]},
        }
        t1 = {
            "block_id": "t1",
            "type": "table",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [1000, 0, 1200, 1000]},
        }
        t2 = {
            "block_id": "t2",
            "type": "table",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [1210, 0, 1400, 1000]},
        }
        result = [b["block_id"] for b in geometric_pre_sorter([t2, t1, heading])]
        assert result == ["h", "t1", "t2"]

    def test_heading_without_x_overlap_not_pulled(self):
        # A label in a left rail that does NOT x-overlap the full-width block
        # below-right of it must not be pulled (negative case for pull-down).
        label = {
            "block_id": "l",
            "type": "heading",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [900, 0, 980, 140]},
        }
        other = {
            "block_id": "o",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [100, 0, 200, 140]},
        }
        wide = {
            "block_id": "w",
            "type": "paragraph",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [1000, 150, 1300, 1000]},
        }
        result = [b["block_id"] for b in geometric_pre_sorter([wide, label, other])]
        # label stays in band 0 with 'other' (same rail), ordered by y
        assert result == ["o", "l", "w"]

    def test_scale_invariance_same_layout_different_units(self):
        # The same physical layout at two coordinate scales (model emits
        # different spans for the same page) must produce the same order.
        def layout(scale: float) -> list[dict]:
            raw = [
                ("intro", "paragraph", 40, 0, 90, 300),
                ("side", "paragraph", 40, 700, 400, 1000),
                ("head", "heading", 800, 0, 975, 300),
                ("tbl", "table", 1000, 0, 1600, 1000),
            ]
            return [
                {
                    "block_id": bid,
                    "type": t,
                    "text": "x",
                    "bbox": {
                        "page_number": 1,
                        "coordinates": [y0 * scale, x0 * scale, y1 * scale, x1 * scale],
                    },
                }
                for bid, t, y0, x0, y1, x1 in raw
            ]

        small = [b["block_id"] for b in geometric_pre_sorter(layout(0.76))]
        large = [b["block_id"] for b in geometric_pre_sorter(layout(1.0))]
        assert small == large == ["intro", "side", "head", "tbl"]

    def test_same_column_jittered_xmin_shares_bucket(self):
        # Blocks of one visual column whose xmin differs by <100px (logo at
        # x=90 vs column at x=45, real Enel p1) share a bucket and sort by y.
        logo = {
            "block_id": "logo",
            "type": "title",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [5, 90, 20, 300]},
        }
        col = {
            "block_id": "col",
            "type": "heading",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [30, 45, 45, 200]},
        }
        result = [b["block_id"] for b in geometric_pre_sorter([col, logo])]
        assert result == ["logo", "col"]


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
        mock_client.messages.stream.assert_not_called()
        assert result["hierarchical_document_tree"]["structured_payload"] == []

    async def test_single_block_skips_api_and_sets_parent_none(
        self, sample_state, sample_block, mocker
    ):
        mock_class = mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        state = {**sample_state, "extracted_flat_blocks": [sample_block]}
        result = await layout_hierarchy_agent_node(state)
        mock_client.messages.stream.assert_not_called()
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
        mock_client.messages.stream = MagicMock(
            return_value=_stream_cm(_make_relation_response(relations))
        )
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
        mock_client.messages.stream = MagicMock(
            return_value=_stream_cm(_make_relation_response(relations))
        )
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
        mock_client.messages.stream = MagicMock(return_value=_stream_cm(_make_text_only_response()))
        mocker.patch("tenacity.nap.sleep")
        state = {**sample_state, "extracted_flat_blocks": [sample_block, block2]}
        with pytest.raises(ValueError):
            await layout_hierarchy_agent_node(state)
