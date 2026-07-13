from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from anthropic import BadRequestError

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


def _stream_cm(response=None, *, exc=None):
    """Mimic ``client.messages.stream(...)``: an async context manager whose
    ``get_final_message()`` returns the final Message (or raises)."""
    inner = MagicMock()
    inner.get_final_message = (
        AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=response)
    )
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _set_stream(mock_client, *, response=None, responses=None, side_effect=None):
    """Wire ``mock_client.messages.stream`` to yield stream context managers.

    - response: single final Message for every call
    - responses: one Message per successive call (retry sequences)
    - side_effect: a callable(*args, **kwargs) returning a stream cm (for
      tool-dependent behaviour, e.g. the strict-fallback tests)
    """
    if side_effect is not None:
        mock_client.messages.stream = MagicMock(side_effect=side_effect)
    elif responses is not None:
        mock_client.messages.stream = MagicMock(side_effect=[_stream_cm(r) for r in responses])
    else:
        mock_client.messages.stream = MagicMock(return_value=_stream_cm(response))
    return mock_client


def _setup_mocks(mocker, response):
    mocker.patch(
        "src.nodes.worker_node.encode_pdf_async",
        new=AsyncMock(return_value="ZmFrZXBkZg=="),
    )
    mock_class = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
    mock_client = mock_class.return_value
    return _set_stream(mock_client, response=response)


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
        _set_stream(mock_client, response=_make_text_only_response())
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
        call_args = mock_client.messages.stream.call_args
        content = call_args.kwargs["messages"][0]["content"]
        assert len(content) == 3
        assert "Field 'type': invalid value" in content[2]["text"]

    async def test_no_validation_error_two_content_items(self, sample_state, sample_block, mocker):
        state = {**sample_state, "last_validation_error": None}
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        await window_parser_node(state)
        call_args = mock_client.messages.stream.call_args
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
        assert mock_client.messages.stream.call_count == 1
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
        _set_stream(
            mock_client,
            responses=[
                _make_tool_use_response([invalid_block]),
                _make_tool_use_response([sample_block]),
            ],
        )
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]
        assert mock_client.messages.stream.call_count == 2
        assert "extraction_warnings" not in result

    async def test_max_retries_exceeded_returns_blocks_with_warning(
        self, sample_state, sample_block, mocker
    ):
        invalid_block = {**sample_block, "type": "invalid_type"}
        mock_client = _setup_mocks(mocker, _make_tool_use_response([invalid_block]))
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [invalid_block]
        assert mock_client.messages.stream.call_count == VALIDATION_MAX_RETRIES
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
        _set_stream(
            mock_client,
            responses=[
                _make_tool_use_response([invalid_block]),
                _make_tool_use_response([sample_block]),
            ],
        )
        await burst_worker_node(sample_state)
        second_call_content = mock_client.messages.stream.call_args_list[1].kwargs["messages"][0][
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
        _set_stream(
            mock_client,
            responses=[
                _make_tool_use_response([]),
                _make_tool_use_response([sample_block]),
            ],
        )
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]
        assert mock_client.messages.stream.call_count == 2

    async def test_truncation_triggers_retry_with_conciseness_error(
        self, sample_state, sample_block, mocker
    ):
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async",
            new=AsyncMock(return_value="ZmFrZXBkZg=="),
        )
        mock_class = mocker.patch("src.nodes.worker_node.AsyncAnthropic")
        mock_client = mock_class.return_value
        _set_stream(
            mock_client,
            responses=[
                _make_truncated_response(),
                _make_tool_use_response([sample_block]),
            ],
        )
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == [sample_block]
        assert mock_client.messages.stream.call_count == 2
        second_call_content = mock_client.messages.stream.call_args_list[1].kwargs["messages"][0][
            "content"
        ]
        assert "truncated" in second_call_content[2]["text"]
        assert "concise" in second_call_content[2]["text"]

    async def test_persistent_truncation_warns_with_truncation_detail(self, sample_state, mocker):
        mock_client = _setup_mocks(mocker, _make_truncated_response())
        result = await burst_worker_node(sample_state)
        assert result["extracted_flat_blocks"] == []
        assert mock_client.messages.stream.call_count == VALIDATION_MAX_RETRIES
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
        _set_stream(
            mock_client,
            responses=[
                _make_tool_use_response([invalid_block]),
                _make_tool_use_response([sample_block]),
            ],
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
        _set_stream(
            mock_client,
            responses=[
                _make_tool_use_response([invalid_block]),
                _make_tool_use_response([sample_block]),
            ],
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
        text = mock_client.messages.stream.call_args.kwargs["messages"][0]["content"][1]["text"]
        assert "anchors from the PDF text layer" in text
        assert "Opening heading of the page" in text
        assert "Closing footer line of the page" in text

    async def test_no_anchor_when_native_layer_unreadable(self, sample_state, sample_block, mocker):
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        mocker.patch("src.nodes.worker_node.PdfReader", side_effect=OSError("no such file"))
        await burst_worker_node(sample_state)
        text = mock_client.messages.stream.call_args.kwargs["messages"][0]["content"][1]["text"]
        assert "anchors from the PDF text layer" not in text


class TestExtractionToolAndErrors:
    """The extraction tool is deliberately non-strict for every doc type
    (strict's grammar-complexity ceiling hangs the stream on the richest
    schemas); correctness is guarded by local jsonschema validation. A
    deterministic 4xx still propagates immediately (no retry)."""

    async def test_extraction_tool_is_non_strict_for_complex_doc(
        self, sample_state, sample_block, mocker
    ):
        state = {**sample_state, "document_type": "scientific_paper"}
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async", new=AsyncMock(return_value="ZmFrZQ==")
        )
        mock_client = mocker.patch("src.nodes.worker_node.AsyncAnthropic").return_value
        _set_stream(mock_client, response=_make_tool_use_response([sample_block]))
        await window_parser_node(state)
        assert "strict" not in mock_client.messages.stream.call_args.kwargs["tools"][0]

    async def test_deterministic_4xx_propagates_without_retry(self, sample_state, mocker):
        mocker.patch(
            "src.nodes.worker_node.encode_pdf_async", new=AsyncMock(return_value="ZmFrZQ==")
        )
        mock_client = mocker.patch("src.nodes.worker_node.AsyncAnthropic").return_value
        _set_stream(
            mock_client,
            side_effect=lambda *_, **__: _stream_cm(
                exc=_bad_request("messages.0: at least one message is required")
            ),
        )
        mocker.patch("tenacity.nap.sleep")
        with pytest.raises(BadRequestError):
            await window_parser_node(sample_state)
        # a deterministic 400 is not retried (retry predicate covers only transients)
        assert mock_client.messages.stream.call_count == 1


class TestEffortKnob:
    async def test_effort_env_passed_to_api(self, sample_state, sample_block, mocker, monkeypatch):
        monkeypatch.setenv("PDFSCOUT_EFFORT", "low")
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        await burst_worker_node(sample_state)
        kwargs = mock_client.messages.stream.call_args.kwargs
        assert kwargs["output_config"] == {"effort": "low"}

    async def test_no_effort_env_no_output_config(
        self, sample_state, sample_block, mocker, monkeypatch
    ):
        monkeypatch.delenv("PDFSCOUT_EFFORT", raising=False)
        response = _make_tool_use_response([sample_block])
        mock_client = _setup_mocks(mocker, response)
        await burst_worker_node(sample_state)
        assert "output_config" not in mock_client.messages.stream.call_args.kwargs
