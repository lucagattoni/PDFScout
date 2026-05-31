from typing import Any, Literal

import jsonschema

from src.schema_registry import SchemaRegistry


def pioneer_validation_route(state: dict[str, Any]) -> Literal["retry_node", "burst_dispatcher"]:
    """Routes after pioneer_parser completes. Validates page 1 blocks only."""
    active_blocks = [b for b in state["extracted_flat_blocks"] if b["bbox"]["page_number"] == 1]

    # Empty list means the model returned no blocks for page 1 or used the wrong page number
    if not active_blocks:
        return "retry_node" if state["retry_count"] < 3 else "burst_dispatcher"

    payload = {"document_type": state["document_type"], "blocks": active_blocks}

    try:
        SchemaRegistry().validate(state["document_type"], payload)
        return "burst_dispatcher"
    except jsonschema.ValidationError:
        if state["retry_count"] < 3:
            return "retry_node"
        return "burst_dispatcher"  # degrade gracefully after 3 failed retries
