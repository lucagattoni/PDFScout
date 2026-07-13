import json
import os
from typing import Any

from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import (
    BAND_FULL_WIDTH_FRAC,
    BAND_PULLDOWN_GAP_FRAC,
    COLUMN_BUCKET_FRAC,
    HIERARCHY_MAX_TOKENS_BASE,
    HIERARCHY_MAX_TOKENS_CEIL,
    HIERARCHY_TOKENS_PER_BLOCK,
    HTTP_MAX_RETRIES,
    MODEL,
    RETRY_BACKOFF_MAX_SECONDS,
    RETRY_BACKOFF_MIN_SECONDS,
    RETRY_BACKOFF_MULTIPLIER,
)
from src.utils.usage import usage_entry

RELATION_TOOL = {
    "name": "set_block_relations",
    "description": "Maps each block_id to its parent_id based on spatial reading order and document hierarchy.",
    # strict: relation tuples are guaranteed schema-exact at generation time
    # (no missing parent_id fields, no stray keys) — removes a whole class of
    # structural variance from the hierarchy call.
    "strict": True,
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
                    "additionalProperties": False,
                },
            }
        },
        "required": ["relations"],
        "additionalProperties": False,
    },
}


def geometric_pre_sorter(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sorts blocks into natural reading order, page ASC.

    Each page is split into horizontal *bands* at every full-width block (one
    whose width is >= BAND_FULL_WIDTH_FRAC of the page's x-span). Within a band
    ALL blocks — full-width ones included — are ordered column-major
    (xmin bucket ASC → ymin ASC), so a narrow label to the left of a full-width
    block reads before it. A heading/title block that sits fully above a
    full-width block, vertically within BAND_PULLDOWN_GAP_FRAC x span of it, and
    x-overlapping it (a section heading directly above its table) is pulled
    down into the full-width block's band so the pair stays adjacent — other
    block types are never pulled, so ordinary column content stays with its
    column. With no full-width blocks every block lands in band 0 and the
    result is plain column-major.

    All three tuning knobs are fractions of the page x-span, so ordering is
    invariant to the model's coordinate scale (the same A4 page has been
    observed with x-spans from 855 to 1125 units): COLUMN_BUCKET_FRAC,
    BAND_FULL_WIDTH_FRAC, BAND_PULLDOWN_GAP_FRAC; see src/config.py."""

    ordered: list[dict[str, Any]] = []
    for page in sorted({b["bbox"]["page_number"] for b in blocks}):
        page_blocks = [b for b in blocks if b["bbox"]["page_number"] == page]

        span = max(b["bbox"]["coordinates"][3] for b in page_blocks) - min(
            b["bbox"]["coordinates"][1] for b in page_blocks
        )
        bucket_w = max(span * COLUMN_BUCKET_FRAC, 1)
        pulldown_gap = span * BAND_PULLDOWN_GAP_FRAC
        fulls: list[dict[str, Any]] = []
        cuts: list[int] = []
        for b in page_blocks:
            ymin, xmin, _, xmax = b["bbox"]["coordinates"]
            if span > 0 and (xmax - xmin) >= BAND_FULL_WIDTH_FRAC * span:
                fulls.append(b)
                cuts.append(ymin)
        cuts.sort()

        def band_of(ymin: float, cuts=cuts) -> int:
            return sum(1 for c in cuts if ymin >= c)

        band: dict[str, int] = {
            b["block_id"]: band_of(b["bbox"]["coordinates"][0]) for b in page_blocks
        }

        # Pull-down: keep a heading (or title) adjacent to the full-width block
        # it introduces instead of stranding it in the band above. A block
        # qualifies when it starts above the cut and its bottom edge lies within
        # pulldown_gap of the cut — on either side, tolerating bbox jitter.
        # Each block joins the band of the NEAREST qualifying full-width block
        # (y ascending), never a later one.
        full_ids = {f["block_id"] for f in fulls}
        fulls_by_y = sorted(fulls, key=lambda f: f["bbox"]["coordinates"][0])
        for b in page_blocks:
            if b["block_id"] in full_ids or b["type"] not in ("heading", "title"):
                continue
            b_ymin, b_xmin, b_ymax, b_xmax = b["bbox"]["coordinates"]
            for f in fulls_by_y:
                f_ymin, f_xmin, _, f_xmax = f["bbox"]["coordinates"]
                starts_above = b_ymin < f_ymin
                bottom_near_cut = abs(f_ymin - b_ymax) <= pulldown_gap
                x_overlaps = b_xmin < f_xmax and b_xmax > f_xmin
                if starts_above and bottom_near_cut and x_overlaps:
                    band[b["block_id"]] = band_of(f_ymin)
                    break

        def sort_key(b, band=band, bucket_w=bucket_w):
            ymin, xmin, _, _ = b["bbox"]["coordinates"]
            return (band[b["block_id"]], xmin // bucket_w, ymin, b["block_id"])

        ordered.extend(sorted(page_blocks, key=sort_key))
    return ordered


@retry(
    stop=stop_after_attempt(HTTP_MAX_RETRIES),
    wait=wait_exponential(
        multiplier=RETRY_BACKOFF_MULTIPLIER,
        min=RETRY_BACKOFF_MIN_SECONDS,
        max=RETRY_BACKOFF_MAX_SECONDS,
    ),
)
async def _call_api(
    client: AsyncAnthropic, manifest: list, max_tokens: int = HIERARCHY_MAX_TOKENS_BASE
) -> Any:
    return await client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
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
        max_tokens = min(
            HIERARCHY_MAX_TOKENS_CEIL,
            max(HIERARCHY_MAX_TOKENS_BASE, len(sorted_blocks) * HIERARCHY_TOKENS_PER_BLOCK),
        )
        response = await _call_api(client, manifest, max_tokens)
        usage_log = [usage_entry("hierarchy", response)]
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
        usage_log = []
        orphan_warnings = []
        for block in sorted_blocks:
            block["parent_id"] = None

    all_warnings = field_warnings + orphan_warnings
    return {
        "extraction_warnings": all_warnings,
        "usage_log": usage_log,
        "hierarchical_document_tree": {
            "document_type": state["document_type"],
            "pdf_hash": state["pdf_hash"],
            "extraction_warnings": state.get("extraction_warnings", []) + all_warnings,
            "structured_payload": sorted_blocks,
        },
    }
