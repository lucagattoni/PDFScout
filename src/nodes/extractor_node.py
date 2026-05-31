from typing import Any

from src.extractors.page_counter import get_page_count
from src.utils.pdf_utils import hash_file


async def native_extractor_node(state: dict[str, Any]) -> dict[str, Any]:
    file_path = state["file_path"]
    pdf_hash = hash_file(file_path)
    total_pages = get_page_count(file_path)  # raises on encrypted PDFs

    if total_pages == 0:
        raise ValueError(
            f"PDF at '{file_path}' yielded zero pages. The file may be empty or corrupted."
        )

    return {
        "pdf_hash": pdf_hash,
        "total_pages": total_pages,
        "current_page": 1,
        "retry_count": 0,
        "last_validation_error": None,
        "extracted_flat_blocks": None,  # None sentinel resets the reducer buffer
        "extraction_warnings": [],
    }
