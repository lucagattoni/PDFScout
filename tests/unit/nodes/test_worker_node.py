from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from anthropic import BadRequestError

import src.nodes.worker_node as wn
from src.config import VALIDATION_MAX_RETRIES
from src.nodes.worker_node import burst_worker_node, window_parser_node


def _bad_request(message: str) -> BadRequestError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(400, request=req)
    return BadRequestError(message, response=resp, body={"error": {"message": message}})


def _make_tool_use_response(blocks: list):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"blocks": blocks}
    response = MagicMock()
    response.content = [tool_block]
    response.stop_reason = "tool_use"
    response.usage.input_tokens = 500
    response.usage.output_tokens = 4000
    response.usage.cache_read_input_tokens = 11000
    response.usage.cache_creation_input_tokens = 0
    return response


def _make_truncated_response():
    """Response cut off by max_tokens: the API discards the partial tool JSON,
    so the tool_use block arrives with an empty input dict."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {}
    response = MagicMock()
    response.content = [tool_block]
    response.stop_reason = "max_tokens"
    response.usage.input_tokens = 500
    response.usage.output_tokens = 16000
    response.usage.cache_read_input_tokens = 11000
    response.usage.cache_creation_input_tokens = 0
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

    async def test_extraction_flags_passed_through(self, sample_state, sample_block, mocker):
        block_with_flags = {**sample_block, "extraction_flags": ["low_legibility"]}
        response = _make_tool_use_response([block_with_flags])
        _setup_mocks(mocker, response)
        result = await window_parser_node(sample_state)
        assert result["extracted_flat_blocks"][0].get("extraction_flags") == ["low_legibility"]

    async def test_extraction_note_passed_through(self, sample_state, sample_block, mocker):
        block_with_note = {
            **sample_block,
            "extraction_flags": ["low_legibility"],
            "extraction_note": "Text is faint.",
        }
        response = _make_tool_use_response([block_with_note])
        _setup_mocks(mocker, response)
        result = await window_parser_node(sample_state)
        assert result["extracted_flat_blocks"][0].get("extraction_note") == "Text is faint."

    async def test_max_tokens_truncation_returns_truncation_error(self, sample_state, mocker):
        _setup_mocks(mocker, _make_truncated_response())
        result = await window_parser_node(sample_state)
        assert result["extracted_flat_blocks"] == []
        assert "truncated" in result["truncation_error"]
        assert "max_tokens" in result["truncation_error"]

    async def test_success_resets_truncation_error(self, sample_state, sample_block, mocker):
        response = _make_tool_use_response([sample_block])
        _setup_mocks(mocker, response)
        result = await window_parser_node(sample_state)
        assert result["truncation_error"] is None


class TestBurstWorkerNode:
    async def test_valid_blocks_pass_on_first_attempt(self, sample_state, sample_block, mocker):
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]
        assert mock_client.messages.create.call_count == 1
        assert "extraction_warnings" not in result

    async def test_extraction_flags_passed_through(self, sample_state, sample_block, mocker):
        block_with_flags = {**sample_block, "extraction_flags": ["low_legibility"]}
        response = _make_tool_use_response([block_with_flags])
        _setup_mocks(mocker, response)
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"][0].get("extraction_flags") == ["low_legibility"]

    async def test_extraction_note_passed_through(self, sample_state, sample_block, mocker):
        block_with_note = {
            **sample_block,
            "extraction_flags": ["low_legibility"],
            "extraction_note": "Text is faint.",
        }
        response = _make_tool_use_response([block_with_note])
        _setup_mocks(mocker, response)
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"][0].get("extraction_note") == "Text is faint."

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
        assert mock_client.messages.create.call_count == VALIDATION_MAX_RETRIES
        warnings = result.get("extraction_warnings", [])
        assert len(warnings) == 1
        assert f"schema validation failed after {VALIDATION_MAX_RETRIES} attempts" in warnings[0]

    async def test_error_injected_into_retry_content(self, sample_state, sample_block, mocker):
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
        second_call_content = mock_client.messages.create.call_args_list[1].kwargs["messages"][0][
            "content"
        ]
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

    async def test_truncation_triggers_retry_with_conciseness_error(
        self, sample_state, sample_block, mocker
    ):
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZXBkZg=="),
        )
        mock_class = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_truncated_response(),
                _make_tool_use_response([sample_block]),
            ]
        )
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]
        assert mock_client.messages.create.call_count == 2
        second_call_content = mock_client.messages.create.call_args_list[1].kwargs["messages"][0][
            "content"
        ]
        assert "truncated" in second_call_content[2]["text"]
        assert "concise" in second_call_content[2]["text"]

    async def test_persistent_truncation_warns_with_truncation_detail(self, sample_state, mocker):
        mock_client = _setup_mocks(mocker, _make_truncated_response())
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == []
        assert mock_client.messages.create.call_count == VALIDATION_MAX_RETRIES
        warnings = result.get("extraction_warnings", [])
        assert len(warnings) == 1
        assert "truncated" in warnings[0]
        assert "No blocks were extracted" not in warnings[0]

    async def test_retry_cause_printed_to_stderr(self, sample_state, sample_block, mocker, capsys):
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
        err = capsys.readouterr().err
        assert "[RETRY]" in err
        assert "attempt 1/" in err
        assert "invalid_type" in err or "Field" in err

    async def test_usage_log_accumulates_across_attempts(self, sample_state, sample_block, mocker):
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
        assert len(result["usage_log"]) == 2
        assert result["usage_log"][0]["context"].endswith("attempt 1")
        assert result["usage_log"][1]["context"].endswith("attempt 2")

    async def test_window_parser_returns_usage_log(self, sample_state, sample_block, mocker):
        response = _make_tool_use_response([sample_block])
        _setup_mocks(mocker, response)
        result = await window_parser_node(sample_state)
        assert len(result["usage_log"]) == 1
        assert result["usage_log"][0]["context"].startswith("pioneer page")

    async def test_anchor_instruction_included_when_native_layer_usable(
        self, sample_state, sample_block, mocker
    ):
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        native = (
            "Opening heading of the page\n"
            "The quarterly statement summarises electricity consumption across the "
            "billing period including standing charges and applicable taxation.\n"
            "Closing footer line of the page"
        )
        fake_page = MagicMock()
        fake_page.extract_text.return_value = native
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page, fake_page, fake_page]
        mocker.patch("src.nodes.worker_node.PdfReader", return_value=fake_reader)
        await burst_worker_node(sample_state)
        text = mock_client.messages.create.call_args.kwargs["messages"][0]["content"][1]["text"]
        assert "anchors from the PDF text layer" in text
        assert "Opening heading of the page" in text
        assert "Closing footer line of the page" in text

    async def test_no_anchor_when_native_layer_unreadable(self, sample_state, sample_block, mocker):
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        mocker.patch("src.nodes.worker_node.PdfReader", side_effect=OSError("no such file"))
        await burst_worker_node(sample_state)
        text = mock_client.messages.create.call_args.kwargs["messages"][0]["content"][1]["text"]
        assert "anchors from the PDF text layer" not in text


class TestStrictSchemaFallback:
    """When the API rejects a doc type's strict tool schema as too complex
    (scientific_paper, contract exceed strict's grammar-complexity ceiling),
    the worker retries with a non-strict tool and memoizes the doc type so
    later pages skip strict. Local jsonschema validation still applies."""

    @pytest.fixture(autouse=True)
    def _clear_memo(self):
        wn._STRICT_INCOMPATIBLE.discard("scientific_paper")
        yield
        wn._STRICT_INCOMPATIBLE.discard("scientific_paper")

    async def test_too_complex_falls_back_to_non_strict(self, sample_state, sample_block, mocker):
        state = {**sample_state, "document_type": "scientific_paper"}
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async", new=AsyncMock(return_value="ZmFrZQ==")
        )
        mock_client = mocker.patch("src.nodes.worker_node.AsyncAnthropic").return_value
        ok = _make_tool_use_response([sample_block])

        async def side_effect(*_, **kwargs):
            if kwargs["tools"][0].get("strict"):
                raise _bad_request("Schema is too complex.")
            return ok

        mock_client.messages.create = AsyncMock(side_effect=side_effect)
        result = await window_parser_node(state)
        assert result["extracted_flat_blocks"] == [sample_block]
        # doc type memoized so later pages skip the strict probe
        assert "scientific_paper" in wn._STRICT_INCOMPATIBLE

    async def test_memoized_doc_type_never_sends_strict(self, sample_state, sample_block, mocker):
        wn._STRICT_INCOMPATIBLE.add("scientific_paper")
        state = {**sample_state, "document_type": "scientific_paper"}
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async", new=AsyncMock(return_value="ZmFrZQ==")
        )
        mock_client = mocker.patch("src.nodes.worker_node.AsyncAnthropic").return_value
        mock_client.messages.create = AsyncMock(
            return_value=_make_tool_use_response([sample_block])
        )
        await window_parser_node(state)
        # the only call used a non-strict tool — no wasted strict probe
        assert "strict" not in mock_client.messages.create.call_args.kwargs["tools"][0]

    async def test_non_too_complex_bad_request_propagates(self, sample_state, mocker):
        state = {**sample_state, "document_type": "scientific_paper"}
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async", new=AsyncMock(return_value="ZmFrZQ==")
        )
        mock_client = mocker.patch("src.nodes.worker_node.AsyncAnthropic").return_value
        mock_client.messages.create = AsyncMock(
            side_effect=_bad_request("messages.0: at least one message is required")
        )
        mocker.patch("tenacity.nap.sleep")
        with pytest.raises(BadRequestError):
            await window_parser_node(state)
        # a deterministic 400 is not retried and not turned into a strict fallback
        assert mock_client.messages.create.call_count == 1
        assert "scientific_paper" not in wn._STRICT_INCOMPATIBLE
