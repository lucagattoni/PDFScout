import json
import os
from typing import Any

from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import (
    BAND_FULL_WIDTH_FRAC,
    COLUMN_BUCKET_PX,
    EXTRACTION_TEMPERATURE,
    HIERARCHY_MAX_TOKENS_BASE,
    HIERARCHY_MAX_TOKENS_CEIL,
    HIERARCHY_TOKENS_PER_BLOCK,
    HTTP_MAX_RETRIES,
    MODEL,
    RETRY_BACKOFF_MAX_SECONDS,
    RETRY_BACKOFF_MIN_SECONDS,
    RETRY_BACKOFF_MULTIPLIER,
)

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
                        "parent_id": {"type": ["string", "null"]},
                    },
                    "required": ["block_id", "parent_id"],
                },
            }
        },
        "required": ["relations"],
    },
}


def geometric_pre_sorter(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sorts blocks into natural reading order, page ASC.

    Each page is split into horizontal *bands* at every full-width block (one
    whose width is >= BAND_FULL_WIDTH_FRAC of the page's x-span). Within a band
    the full-width block leads, then remaining blocks are ordered column-major
    (xmin bucket ASC → ymin ASC). This gives top-to-bottom reading order while
    keeping multi-column regions (two-column papers, side-by-side form fields)
    grouped by column. With no full-width blocks every block lands in band 0, so
    the result is plain column-major — identical to the previous behavior.

    COLUMN_BUCKET_PX and BAND_FULL_WIDTH_FRAC tune the grouping; see src/config.py."""

    ordered: list[dict[str, Any]] = []
    for page in sorted({b["bbox"]["page_number"] for b in blocks}):
        page_blocks = [b for b in blocks if b["bbox"]["page_number"] == page]

        span = max(b["bbox"]["coordinates"][3] for b in page_blocks) - min(
            b["bbox"]["coordinates"][1] for b in page_blocks
        )
        full_ids = set()
        cuts: list[int] = []
        for b in page_blocks:
            ymin, xmin, _, xmax = b["bbox"]["coordinates"]
            if span > 0 and (xmax - xmin) >= BAND_FULL_WIDTH_FRAC * span:
                full_ids.add(b["block_id"])
                cuts.append(ymin)
        cuts.sort()

        def sort_key(b, full_ids=full_ids, cuts=cuts):
            ymin, xmin, _, _ = b["bbox"]["coordinates"]
            is_full = b["block_id"] in full_ids
            band = sum(1 for c in cuts if ymin >= c)
            return (band, 0 if is_full else 1, 0 if is_full else xmin // COLUMN_BUCKET_PX, ymin, b["block_id"])

        ordered.extend(sorted(page_blocks, key=sort_key))
    return ordered


@retry(stop=stop_after_attempt(HTTP_MAX_RETRIES), wait=wait_exponential(multiplier=RETRY_BACKOFF_MULTIPLIER, min=RETRY_BACKOFF_MIN_SECONDS, max=RETRY_BACKOFF_MAX_SECONDS))
async def _call_api(client: AsyncAnthropic, manifest: list, max_tokens: int = HIERARCHY_MAX_TOKENS_BASE) -> Any:
    return await client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=EXTRACTION_TEMPERATURE,
        tools=[RELATION_TOOL],
        tool_choice={"type": "tool", "name": "set_block_relations"},
        messages=[
            {
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
                ),
            }
        ],
    )


async def layout_hierarchy_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Drop blocks missing required fields — burst pages have no validation loop
    _REQUIRED = {"block_id", "type", "bbox", "text"}
    field_warnings: list[str] = []
    well_formed: list[dict] = []
    for block in state["extracted_flat_blocks"]:
        missing = _REQUIRED - block.keys()
        if missing:
            field_warnings.append(
                f"Block dropped: missing required fields {sorted(missing)}. "
                f"Preview: {str(block)[:80]}"
            )
        else:
            well_formed.append(block)

    # Deduplicate by block_id before sorting — guards against pioneer retry duplicates
    seen_ids: set = set()
    unique_blocks = []
    for block in well_formed:
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
                "text_preview": b["text"][:50],
            }
            for b in sorted_blocks
        ]
        max_tokens = min(HIERARCHY_MAX_TOKENS_CEIL, max(HIERARCHY_MAX_TOKENS_BASE, len(sorted_blocks) * HIERARCHY_TOKENS_PER_BLOCK))
        response = await _call_api(client, manifest, max_tokens)
        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_block is None:
            raise ValueError(
                f"API returned no tool_use block for hierarchy agent. "
                f"Content types: {[b.type for b in response.content]}"
            )
        relations = tool_block.input.get("relations", [])
        relation_map = {r["block_id"]: r["parent_id"] for r in relations}
        block_ids = {b["block_id"] for b in sorted_blocks}
        orphan_warnings: list[str] = []
        for bid, pid in list(relation_map.items()):
            if pid is not None and pid not in block_ids:
                orphan_warnings.append(
                    f"block '{bid}' has unknown parent_id '{pid}'; edge dropped to root."
                )
                relation_map[bid] = None
            elif pid == bid:
                orphan_warnings.append(
                    f"block '{bid}' references itself as parent; edge dropped to root."
                )
                relation_map[bid] = None
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

    all_warnings = field_warnings + orphan_warnings
    return {
        "extraction_warnings": all_warnings,
        "hierarchical_document_tree": {
            "document_type": state["document_type"],
            "pdf_hash": state["pdf_hash"],
            "extraction_warnings": state.get("extraction_warnings", []) + all_warnings,
            "structured_payload": sorted_blocks,
        },
    }
