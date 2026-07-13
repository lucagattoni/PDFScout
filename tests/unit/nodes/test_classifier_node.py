from unittest.mock import AsyncMock, MagicMock

from src.config import FALLBACK_DOC_TYPE
from src.nodes.classifier_node import classifier_node


def _make_text_response(text: str):
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    response.content = [content_block]
    response.stop_reason = "end_turn"
    response.usage.input_tokens = 40
    response.usage.output_tokens = 5
    response.usage.cache_read_input_tokens = 0
    response.usage.cache_creation_input_tokens = 10000
    return response


def _setup_mocks(mocker, response_text: str):
    mocker.patch(
        "src.nodes.classifier_node.encode_pdf_async",
        new=AsyncMock(return_value="ZmFrZXBkZg=="),
    )
    mock_class = mocker.patch("src.nodes.classifier_node.AsyncAnthropic")
    mock_client = mock_class.return_value
    mock_client.messages.create = AsyncMock(return_value=_make_text_response(response_text))
    return mock_client


class TestClassifierNode:
    async def test_invoice_classified(self, sample_state, mocker):
        _setup_mocks(mocker, "invoice")
        result = await classifier_node(sample_state)
        assert result["document_type"] == "invoice"
        assert isinstance(result["target_json_schema"], dict)

    async def test_scientific_paper_classified(self, sample_state, mocker):
        _setup_mocks(mocker, "scientific_paper")
        result = await classifier_node(sample_state)
        assert result["document_type"] == "scientific_paper"

    async def test_unknown_falls_back(self, sample_state, mocker):
        _setup_mocks(mocker, "unknown_garbage")
        result = await classifier_node(sample_state)
        assert result["document_type"] == FALLBACK_DOC_TYPE

    async def test_contract_classified(self, sample_state, mocker):
        _setup_mocks(mocker, "contract")
        result = await classifier_node(sample_state)
        assert result["document_type"] == "contract"
        assert result["target_json_schema"].get("title") == "AgnosticContractStructure"

    async def test_whitespace_stripped(self, sample_state, mocker):
        _setup_mocks(mocker, "  invoice  ")
        result = await classifier_node(sample_state)
        assert result["document_type"] == "invoice"

    async def test_thinking_explicitly_disabled(self, sample_state, mocker):
        # Adaptive thinking is on by default when the field is omitted, and
        # thinking tokens count against the tiny classifier budget — the call
        # must pin thinking off.
        mock_client = _setup_mocks(mocker, "invoice")
        await classifier_node(sample_state)
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "disabled"}

    async def test_usage_log_returned(self, sample_state, mocker):
        _setup_mocks(mocker, "invoice")
        result = await classifier_node(sample_state)
        assert len(result["usage_log"]) == 1
        entry = result["usage_log"][0]
        assert entry["context"] == "classifier"
        assert entry["cache_creation_input_tokens"] == 10000
