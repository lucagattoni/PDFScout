from typing import Any
import jsonschema
from src.schema_registry import SchemaRegistry


async def retry_incrementor_node(state: dict[str, Any]) -> dict[str, Any]:
    # Re-run validation to capture the actual error detail for the LLM's next attempt
    active_blocks = [b for b in state["extracted_flat_blocks"] if b["bbox"]["page_number"] == 1]
    payload = {"document_type": state["document_type"], "blocks": active_blocks}
    error_detail = "Unknown schema violation."
    try:
        SchemaRegistry().validate(state["document_type"], payload)
    except jsonschema.ValidationError as e:
        path = " → ".join(str(p) for p in e.absolute_path) or "root"
        error_detail = f"Field '{path}': {e.message}"

    attempt = state["retry_count"] + 1
    return {
        "retry_count": attempt,
        "last_validation_error": (
            f"Schema violation on pioneer page extraction (attempt {attempt}/3).\n"
            f"Error: {error_detail}\n"
            f"Fix the block structure to match the target schema."
        )
    }
