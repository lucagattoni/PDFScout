"""Group A — Native extraction (no LLM, no API key required).

Tests call native_extractor_node directly as a function.
"""

from pathlib import Path

import pytest

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"


@pytest.mark.e2e
@pytest.mark.grp_a
class TestGroupA:
    async def test_a1_valid_1page(self):
        from src.nodes.extractor_node import native_extractor_node

        result = await native_extractor_node({"file_path": str(_PDFS / "grp_a_valid_1page.pdf")})
        assert result["total_pages"] == 1
        assert len(result["pdf_hash"]) == 64
        assert result["current_page"] == 1
        assert result["retry_count"] == 0

    async def test_a2_valid_10page(self):
        from src.nodes.extractor_node import native_extractor_node

        result = await native_extractor_node({"file_path": str(_PDFS / "grp_a_valid_10page.pdf")})
        assert result["total_pages"] == 10

    async def test_a3_encrypted_raises(self):
        from src.nodes.extractor_node import native_extractor_node

        with pytest.raises(ValueError, match="encrypted"):
            await native_extractor_node({"file_path": str(_PDFS / "grp_a_encrypted.pdf")})
