from src.edges import pioneer_validation_route


def _make_block(page: int = 1, block_type: str = "paragraph") -> dict:
    return {
        "block_id": "blk-001",
        "type": block_type,
        "text": "Hello.",
        "bbox": {"page_number": page, "coordinates": [0, 0, 100, 50]},
        "is_continued": False,
        "metadata": {},
    }


def _state(retry_count: int, blocks: list) -> dict:
    return {
        "document_type": "baseline_core",
        "retry_count": retry_count,
        "extracted_flat_blocks": blocks,
        "current_page": 1,
    }


class TestPioneerValidationRoute:
    def test_no_blocks_routes_retry(self):
        assert pioneer_validation_route(_state(0, [])) == "retry_node"

    def test_no_blocks_max_retries_routes_burst(self):
        assert pioneer_validation_route(_state(3, [])) == "burst_dispatcher"

    def test_blocks_wrong_page_routes_retry(self):
        assert pioneer_validation_route(_state(0, [_make_block(page=2)])) == "retry_node"

    def test_blocks_wrong_page_max_retries_routes_burst(self):
        assert pioneer_validation_route(_state(3, [_make_block(page=2)])) == "burst_dispatcher"

    def test_valid_blocks_routes_burst(self):
        assert pioneer_validation_route(_state(0, [_make_block(page=1)])) == "burst_dispatcher"

    def test_invalid_blocks_routes_retry(self):
        bad_block = {
            "block_id": "b1",
            "type": "invalid_type_xyz",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [0, 0, 10, 10]},
        }
        assert pioneer_validation_route(_state(1, [bad_block])) == "retry_node"

    def test_invalid_blocks_max_retries_routes_burst(self):
        bad_block = {
            "block_id": "b1",
            "type": "invalid_type_xyz",
            "text": "x",
            "bbox": {"page_number": 1, "coordinates": [0, 0, 10, 10]},
        }
        assert pioneer_validation_route(_state(3, [bad_block])) == "burst_dispatcher"
