from unittest.mock import AsyncMock, MagicMock

from src.config import VALIDATION_MAX_RETRIES
from src.graph import build_app


def _make_tool_use_response(blocks: list):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"blocks": blocks}
    response = MagicMock()
    response.content = [tool_block]
    return response


def _make_relation_response(relations: list):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"relations": relations}
    response = MagicMock()
    response.content = [tool_block]
    return response


def _valid_block(page: int = 1):
    return {
        "block_id": f"blk-p{page}",
        "type": "paragraph",
        "text": f"Content page {page}.",
        "bbox": {"page_number": page, "coordinates": [50, 50, 200, 80]},
        "is_continued": False,
        "metadata": {},
    }


async def _stream_graph(minimal_pdf_path):
    """Run the graph once, collecting node-name events and the final state."""
    app = build_app(checkpointer=None)
    node_events = []
    final_state = None
    async for mode, data in app.astream(
        {"file_path": minimal_pdf_path}, stream_mode=["updates", "values"]
    ):
        if mode == "updates":
            node_events.append(list(data.keys())[0])
        elif mode == "values":
            final_state = data
    return node_events, final_state


class TestGraphPipelineHappyPath:
    async def test_single_page_baseline_core(self, minimal_pdf_path, mocker):
        mocker.patch("src.nodes.extractor_node.get_page_count", return_value=1)
        mocker.patch("src.nodes.extractor_node.hash_file", return_value="a" * 64)
        mocker.patch(
            "src.nodes.classifier_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZQ=="),
        )
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZQ=="),
        )

        classifier_mock = mocker.patch("src.nodes.classifier_node.AsyncAnthropic")
        classifier_client = classifier_mock.return_value
        classify_response = MagicMock()
        classify_response.content = [MagicMock(text="baseline_core")]
        classifier_client.messages.create = AsyncMock(return_value=classify_response)

        worker_mock = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        worker_client = worker_mock.return_value
        worker_client.messages.create = AsyncMock(
            return_value=_make_tool_use_response([_valid_block(1)])
        )

        mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        # single block → hierarchy skips API call

        _, final_state = await _stream_graph(minimal_pdf_path)

        tree = final_state.get("hierarchical_document_tree")
        assert tree is not None
        assert len(tree["structured_payload"]) == 1
        assert tree["structured_payload"][0]["parent_id"] is None


class TestGraphPipelineRetry:
    async def test_pioneer_retry_then_success(self, minimal_pdf_path, mocker):
        mocker.patch("src.nodes.extractor_node.get_page_count", return_value=2)
        mocker.patch("src.nodes.extractor_node.hash_file", return_value="b" * 64)
        mocker.patch(
            "src.nodes.classifier_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZQ=="),
        )
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZQ=="),
        )

        classifier_mock = mocker.patch("src.nodes.classifier_node.AsyncAnthropic")
        classifier_client = classifier_mock.return_value
        classify_response = MagicMock()
        classify_response.content = [MagicMock(text="baseline_core")]
        classifier_client.messages.create = AsyncMock(return_value=classify_response)

        # pioneer first call → invalid block → retried → valid block; page 2 → valid block
        invalid_block = {
            "block_id": "bad-blk",
            "type": "invalid_type",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [0, 0, 10, 10]},
        }
        worker_mock = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        worker_client = worker_mock.return_value
        worker_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response([invalid_block]),  # pioneer call 1 → invalid
                _make_tool_use_response([_valid_block(1)]),  # pioneer call 2 (after retry) → valid
                _make_tool_use_response([_valid_block(2)]),  # page 2 burst worker
            ]
        )

        hierarchy_mock = mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        hierarchy_client = hierarchy_mock.return_value
        hierarchy_client.messages.create = AsyncMock(
            return_value=_make_relation_response(
                [
                    {"block_id": "blk-p1", "parent_id": None},
                    {"block_id": "blk-p2", "parent_id": None},
                ]
            )
        )

        node_sequence, final_state = await _stream_graph(minimal_pdf_path)

        assert "retry_node" in node_sequence
        assert node_sequence.index("retry_node") < node_sequence.index("burst_dispatcher")

        warnings = final_state.get("extraction_warnings", []) if final_state else []
        assert warnings == []


class TestBurstAdversarial:
    async def test_c1_burst_malformed_block_retried_then_filtered(self, minimal_pdf_path, mocker):
        """Burst page 2 returns a block missing the required 'block_id' field on all 3 attempts.
        burst_worker_node retries inline, exhausts attempts, logs a warning, and returns the
        malformed block. hierarchy_node then filters it. Pipeline must complete with only the
        page-1 block in output and at least one warning logged."""
        mocker.patch("src.nodes.extractor_node.get_page_count", return_value=2)
        mocker.patch("src.nodes.extractor_node.hash_file", return_value="e" * 64)
        mocker.patch(
            "src.nodes.classifier_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZQ=="),
        )
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZQ=="),
        )

        classifier_mock = mocker.patch("src.nodes.classifier_node.AsyncAnthropic")
        classifier_client = classifier_mock.return_value
        classify_response = MagicMock()
        classify_response.content = [MagicMock(text="baseline_core")]
        classifier_client.messages.create = AsyncMock(return_value=classify_response)

        malformed_block = {
            # Intentionally missing "block_id" — required field
            "type": "paragraph",
            "text": "This page-2 block is missing its block_id.",
            "bbox": {"page_number": 2, "coordinates": [50, 50, 200, 80]},
            "is_continued": False,
            "metadata": {},
        }
        worker_mock = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        worker_client = worker_mock.return_value
        worker_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response([_valid_block(1)]),   # pioneer page 1 → valid
                _make_tool_use_response([malformed_block]),   # burst page 2, attempt 1 → invalid
                _make_tool_use_response([malformed_block]),   # burst page 2, attempt 2 → invalid
                _make_tool_use_response([malformed_block]),   # burst page 2, attempt 3 → invalid
            ]
        )

        hierarchy_mock = mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")
        hierarchy_client = hierarchy_mock.return_value
        hierarchy_client.messages.create = AsyncMock(
            return_value=_make_relation_response([{"block_id": "blk-p1", "parent_id": None}])
        )

        _, final_state = await _stream_graph(minimal_pdf_path)

        tree = final_state.get("hierarchical_document_tree")
        assert tree is not None, "Pipeline must produce a tree"

        blocks = tree["structured_payload"]
        assert any(b["block_id"] == "blk-p1" for b in blocks), "Page-1 block must be in output"
        assert all("block_id" in b for b in blocks), (
            "Malformed block (missing block_id) must not appear in structured_payload"
        )

        warnings = tree.get("extraction_warnings", [])
        assert len(warnings) >= 1, f"Expected at least one warning, got: {warnings}"


class TestGraphPipelineMaxRetryDegradation:
    async def test_pioneer_max_retry_adds_warning(self, minimal_pdf_path, mocker):
        mocker.patch("src.nodes.extractor_node.get_page_count", return_value=1)
        mocker.patch("src.nodes.extractor_node.hash_file", return_value="c" * 64)
        mocker.patch(
            "src.nodes.classifier_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZQ=="),
        )
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZQ=="),
        )

        classifier_mock = mocker.patch("src.nodes.classifier_node.AsyncAnthropic")
        classifier_client = classifier_mock.return_value
        classify_response = MagicMock()
        classify_response.content = [MagicMock(text="baseline_core")]
        classifier_client.messages.create = AsyncMock(return_value=classify_response)

        invalid_block = {
            "block_id": "bad-blk",
            "type": "invalid_type",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [0, 0, 10, 10]},
        }
        # All 4 attempts (1 pioneer + 3 retries) return invalid blocks
        worker_mock = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        worker_client = worker_mock.return_value
        worker_client.messages.create = AsyncMock(
            return_value=_make_tool_use_response([invalid_block])
        )

        mocker.patch("src.nodes.hierarchy_node.AsyncAnthropic")

        node_sequence, final_state = await _stream_graph(minimal_pdf_path)

        retry_count = node_sequence.count("retry_node")
        assert retry_count == VALIDATION_MAX_RETRIES

        assert "burst_dispatcher" in node_sequence
        burst_idx = node_sequence.index("burst_dispatcher")
        for retry_idx in [i for i, n in enumerate(node_sequence) if n == "retry_node"]:
            assert retry_idx < burst_idx

        warnings = final_state.get("extraction_warnings", []) if final_state else []
        assert any("page 1" in w.lower() for w in warnings)
