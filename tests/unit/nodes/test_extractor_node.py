import pytest

from src.nodes.extractor_node import native_extractor_node


class TestNativeExtractorNode:
    async def test_normal_pdf(self, minimal_pdf_path, mocker):
        mocker.patch("src.nodes.extractor_node.get_page_count", return_value=2)
        result = await native_extractor_node({"file_path": minimal_pdf_path})
        assert len(result["pdf_hash"]) == 64
        assert result["total_pages"] == 2
        assert result["current_page"] == 1
        assert result["retry_count"] == 0
        assert result["last_validation_error"] is None
        assert result["extracted_flat_blocks"] is None

    async def test_zero_pages_raises(self, minimal_pdf_path, mocker):
        mocker.patch("src.nodes.extractor_node.get_page_count", return_value=0)
        with pytest.raises(ValueError, match="zero pages"):
            await native_extractor_node({"file_path": minimal_pdf_path})

    async def test_missing_file_raises(self, mocker):
        mocker.patch(
            "src.nodes.extractor_node.hash_file",
            side_effect=FileNotFoundError("no such file"),
        )
        with pytest.raises(FileNotFoundError):
            await native_extractor_node({"file_path": "/nonexistent/file.pdf"})
