from typing import Annotated, Any, TypedDict


def merge_flat_blocks(existing: list[dict[str, Any]], new: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Appends sub-agent page payloads into a unified global accumulation array.
    Passing None as new resets the buffer (used by extractor/retry nodes on fresh runs)."""
    if new is None:
        return []
    if not existing:
        return new
    return existing + new


def merge_warnings(existing: list[str], new: list[str]) -> list[str]:
    if not existing:
        return new if new is not None else []
    if not new:
        return existing
    return existing + new


class PDFParserState(TypedDict):
    # Static Input
    file_path: str
    pdf_hash: str
    total_pages: int

    # Polymorphic Blueprint Configuration
    document_type: str
    target_json_schema: dict[str, Any]

    # State Iteration Engine (pioneer page only)
    current_page: int
    retry_count: int
    last_validation_error: str | None

    # Aggregate Buffers
    extracted_flat_blocks: Annotated[list[dict[str, Any]], merge_flat_blocks]
    extraction_warnings: Annotated[list[str], merge_warnings]
    hierarchical_document_tree: dict[str, Any] | None
