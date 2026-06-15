from unittest.mock import AsyncMock, MagicMock

import pytest

from src.nodes.worker_node import burst_worker_node, window_parser_node


def _make_tool_use_response(blocks: list):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"blocks": blocks}
    response = MagicMock()
    response.content = [tool_block]
    return response


def _make_text_only_response():
    text_block = MagicMock()
    text_block.type = "text"
    response = MagicMock()
    response.content = [text_block]
    return response


def _setup_mocks(mocker, response):
    mocker.patch(
        "src.nodes.worker_node.encode_pdf_async",
        new=AsyncMock(return_value="ZmFrZXBkZg=="),
    )
    mock_class = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
    mock_client = mock_class.return_value
    mock_client.messages.create = AsyncMock(return_value=response)
    return mock_client


class TestWindowParserNode:
    async def test_tool_use_returns_blocks(self, sample_state, sample_block, mocker):
        response = _make_tool_use_response([sample_block])
        _setup_mocks(mocker, response)
        result = await window_parser_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]

    async def test_no_tool_use_raises(self, sample_state, mocker):
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZXBkZg=="),
        )
        mock_class = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        mock_client.messages.create = AsyncMock(return_value=_make_text_only_response())
        # Bypass tenacity retries
        mocker.patch("tenacity.nap.sleep")
        with pytest.raises(ValueError):
            await window_parser_node(sample_state)

    async def test_validation_error_adds_third_content_item(
        self, sample_state, sample_block, mocker
    ):
        state = {**sample_state, "last_validation_error": "Field 'type': invalid value"}
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        await window_parser_node(state)
        call_args = mock_client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]
        assert len(content) == 3
        assert "Field 'type': invalid value" in content[2]["text"]

    async def test_no_validation_error_two_content_items(self, sample_state, sample_block, mocker):
        state = {**sample_state, "last_validation_error": None}
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        await window_parser_node(state)
        call_args = mock_client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]
        assert len(content) == 2


class TestBurstWorkerNode:
    async def test_valid_blocks_pass_on_first_attempt(self, sample_state, sample_block, mocker):
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]
        assert mock_client.messages.create.call_count == 1
        assert "extraction_warnings" not in result

    async def test_invalid_blocks_trigger_retry_until_valid(
        self, sample_state, sample_block, mocker
    ):
        invalid_block = {**sample_block, "type": "invalid_type"}
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZXBkZg=="),
        )
        mock_class = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response([invalid_block]),
                _make_tool_use_response([sample_block]),
            ]
        )
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]
        assert mock_client.messages.create.call_count == 2
        assert "extraction_warnings" not in result

    async def test_max_retries_exceeded_returns_blocks_with_warning(
        self, sample_state, sample_block, mocker
    ):
        invalid_block = {**sample_block, "type": "invalid_type"}
        mock_client = _setup_mocks(mocker, _make_tool_use_response([invalid_block]))
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [invalid_block]
        assert mock_client.messages.create.call_count == 3
        warnings = result.get("extraction_warnings", [])
        assert len(warnings) == 1
        assert "schema validation failed after 3 attempts" in warnings[0]

    async def test_error_injected_into_retry_content(
        self, sample_state, sample_block, mocker
    ):
        invalid_block = {**sample_block, "type": "invalid_type"}
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZXBkZg=="),
        )
        mock_class = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response([invalid_block]),
                _make_tool_use_response([sample_block]),
            ]
        )
        await burst_worker_node(sample_state)
        second_call_content = mock_client.messages.create.call_args_list[1].kwargs[
            "messages"
        ][0]["content"]
        assert len(second_call_content) == 3
        assert "PREVIOUS VALIDATION ERROR" in second_call_content[2]["text"]

    async def test_empty_blocks_trigger_retry(self, sample_state, sample_block, mocker):
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZXBkZg=="),
        )
        mock_class = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response([]),
                _make_tool_use_response([sample_block]),
            ]
        )
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]
        assert mock_client.messages.create.call_count == 2
