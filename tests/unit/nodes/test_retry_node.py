from src.config import VALIDATION_MAX_RETRIES
from src.nodes.retry_node import retry_incrementor_node


class TestRetryIncrementorNode:
    async def test_none_blocks_no_blocks_error(self, sample_state):
        state = {**sample_state, "extracted_flat_blocks": None, "retry_count": 0}
        result = await retry_incrementor_node(state)
        assert "No blocks" in result["last_validation_error"]

    async def test_empty_list_no_blocks_error(self, sample_state):
        state = {**sample_state, "extracted_flat_blocks": [], "retry_count": 0}
        result = await retry_incrementor_node(state)
        assert "No blocks" in result["last_validation_error"]

    async def test_retry_count_increments(self, sample_state):
        state = {**sample_state, "extracted_flat_blocks": [], "retry_count": 1}
        result = await retry_incrementor_node(state)
        assert result["retry_count"] == 2

    async def test_flat_blocks_reset_to_none(self, sample_state, sample_block):
        state = {**sample_state, "extracted_flat_blocks": [sample_block], "retry_count": 0}
        result = await retry_incrementor_node(state)
        assert result["extracted_flat_blocks"] is None

    async def test_error_contains_attempt_count(self, sample_state):
        state = {**sample_state, "extracted_flat_blocks": [], "retry_count": 0}
        result = await retry_incrementor_node(state)
        assert f"(attempt 1/{VALIDATION_MAX_RETRIES})" in result["last_validation_error"]

    async def test_schema_failing_blocks_error_detail(self, sample_state):
        bad_block = {
            "block_id": "b1",
            "type": "invalid_type",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [0, 0, 10, 10]},
        }
        state = {**sample_state, "extracted_flat_blocks": [bad_block], "retry_count": 0}
        result = await retry_incrementor_node(state)
        assert result["last_validation_error"] is not None
        assert len(result["last_validation_error"]) > 0
