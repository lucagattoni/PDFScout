import os
import json
from typing import Any
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import MODEL, COLUMN_BUCKET_PX

RELATION_TOOL = {
    "name": "set_block_relations",
    "description": "Maps each block_id to its parent_id based on spatial reading order and document hierarchy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "block_id": {"type": "string"},
                        "parent_id": {"type": ["string", "null"]}
                    },
                    "required": ["block_id", "parent_id"]
                }
            }
        },
        "required": ["relations"]
    }
}


def geometric_pre_sorter(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sorts blocks deterministically: page ASC → column bucket ASC → ymin ASC.
    COLUMN_BUCKET_PX controls how finely columns are grouped; tune in src/config.py."""
    def sort_key(b):
        page = b["bbox"]["page_number"]
        ymin, xmin, _, _ = b["bbox"]["coordinates"]
        return (page, xmin // COLUMN_BUCKET_PX, ymin)
    return sorted(blocks, key=sort_key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _call_api(client: AsyncAnthropic, manifest: list) -> Any:
    return await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        temperature=0.0,
        tools=[RELATION_TOOL],
        tool_choice={"type": "tool", "name": "set_block_relations"},
        messages=[{
            "role": "user",
            "content": (
                "You are a Document Layout Tree Architect. Given a spatially ordered flat list of "
                "structural blocks, assign parent-child relationships.\n"
                "RULES:\n"
                "1. Blocks (paragraphs, tables, list_items) directly following a 'heading' block "
                "get parent_id = that heading's block_id.\n"
                "2. If a block has is_continued=true, the first block of the next page is its child.\n"
                "3. Top-level blocks (title, unpaired headings) get parent_id = null.\n\n"
                f"Flat manifest:\n{json.dumps(manifest, indent=2)}"
            )
        }]
    )


async def layout_hierarchy_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Deduplicate by block_id before sorting — guards against pioneer retry duplicates
    seen_ids: set = set()
    unique_blocks = []
    for block in state["extracted_flat_blocks"]:
        if block["block_id"] not in seen_ids:
            seen_ids.add(block["block_id"])
            unique_blocks.append(block)

    sorted_blocks = geometric_pre_sorter(unique_blocks)

    # Skip the hierarchy API call when there is at most one block — no relations to assign
    if len(sorted_blocks) > 1:
        manifest = [
            {
                "block_id": b["block_id"],
                "type": b["type"],
                "bbox": b["bbox"],
                "is_continued": b.get("is_continued", False),
                "text_preview": b["text"][:50]
            }
            for b in sorted_blocks
        ]
        response = await _call_api(client, manifest)
        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_block is None:
            raise ValueError(
                f"API returned no tool_use block for hierarchy agent. "
                f"Content types: {[b.type for b in response.content]}"
            )
        relations = tool_block.input.get("relations", [])
        relation_map = {r["block_id"]: r["parent_id"] for r in relations}
        orphan_warnings: list[str] = []
        for block in sorted_blocks:
            if block["block_id"] not in relation_map:
                orphan_warnings.append(
                    f"block_id '{block['block_id']}' missing from relation_map; promoted to root."
                )
                block["parent_id"] = None
            else:
                block["parent_id"] = relation_map[block["block_id"]]
    else:
        orphan_warnings = []
        for block in sorted_blocks:
            block["parent_id"] = None

    return {
        "extraction_warnings": orphan_warnings,
        "hierarchical_document_tree": {
            "document_type": state["document_type"],
            "pdf_hash": state["pdf_hash"],
            "extraction_warnings": state.get("extraction_warnings", []) + orphan_warnings,
            "structured_payload": sorted_blocks
        }
    }
