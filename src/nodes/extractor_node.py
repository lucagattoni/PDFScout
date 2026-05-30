import hashlib
from typing import Any
from src.extractors.plumber_engine import PlumberExtractor


def _hash_file(file_path: str) -> str:
    """Chunked SHA-256 — avoids loading the entire file into memory."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def native_extractor_node(state: dict[str, Any]) -> dict[str, Any]:
    file_path = state["file_path"]
    pdf_hash = _hash_file(file_path)

    extractor = PlumberExtractor()
    metadata_objects = extractor.extract_document(file_path)

    if not metadata_objects:
        raise ValueError(
            f"PDF at '{file_path}' yielded zero pages. "
            "The file may be empty, image-only, or password-protected."
        )

    return {
        "pdf_hash": pdf_hash,
        "total_pages": len(metadata_objects),
        "native_text_metadata": [p.model_dump() for p in metadata_objects],
        "current_page": 1,
        "retry_count": 0,
        "last_validation_error": None,
        "extracted_flat_blocks": [],
        "extraction_warnings": []
    }
