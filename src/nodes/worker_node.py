import asyncio
import json
import os
from typing import Any

import jsonschema
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import (
    CONCURRENCY_LIMIT,
    HTTP_MAX_RETRIES,
    MODEL,
    RETRY_BACKOFF_MAX_SECONDS,
    RETRY_BACKOFF_MIN_SECONDS,
    RETRY_BACKOFF_MULTIPLIER,
    VALIDATION_MAX_RETRIES,
    WORKER_MAX_TOKENS,
)
from src.schema_registry import SchemaRegistry
from src.utils.pdf_utils import encode_pdf_async

_semaphore: asyncio.Semaphore | None = None
_semaphore_loop_id: int = -1


def _get_semaphore() -> asyncio.Semaphore:
    """Return a semaphore bound to the current running event loop.

    asyncio.Semaphore is loop-bound in Python 3.10+. Calling asyncio.run()
    multiple times (e.g. in generate_real_ground_truth.py, once per slot)
    creates a fresh loop each time, so the module-level semaphore must be
    recreated when the loop changes."""
    global _semaphore, _semaphore_loop_id
    loop = asyncio.get_running_loop()
    if id(loop) != _semaphore_loop_id:
        _semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        _semaphore_loop_id = id(loop)
    return _semaphore


_SCIENTIFIC_PAPER_INSTRUCTIONS = (
    "\nFor scientific_paper documents, populate metadata subfields where present on the page:"
    "\n- title/paragraph blocks containing author names, abstract, or DOI → bibliographic (authors, title, abstract, doi)"
    "\n- heading blocks with a section number → section (section_number, section_title)"
    "\n- reference list items → reference (citation_key, authors, year, title, venue)"
    "\n- figure or table blocks → figure_table (label, caption, referenced_block_id)"
)

_CONTRACT_INSTRUCTIONS = (
    "\nFor contract documents, populate metadata subfields where present on the page:"
    "\n- title block for the document title → contract_meta (contract_type, effective_date, governing_law)"
    "\n- paragraph or heading blocks identifying a party → party (party_name, party_role, address)"
    "\n- heading blocks introducing a clause → clause (clause_number, clause_title)"
    "\n- signature area blocks → use type='signature_block' and metadata.signature (signatory_name, party_role, date_label)"
    "\n- schedule or exhibit tables → table_data (total_rows, total_cols, cells)"
)

_EXTRACTION_FLAGS_INSTRUCTION = (
    "\n\nFlags should be rare — omit extraction_flags (or use []) for clearly readable, "
    "unambiguous blocks. Set extraction_flags only when quality is genuinely uncertain: "
    "'partial_visibility' if the block is cut off at the page edge and text is missing; "
    "'low_legibility' if text is hard to read due to scan quality, low contrast, or overlap; "
    "'ambiguous_type' if you are uncertain which block type is most appropriate; "
    "'possible_encoding_error' if the text contains likely OCR or encoding artifacts "
    "(garbled characters, unexpected symbols, mixed scripts). "
    "When you set extraction_flags, also set extraction_note to one sentence naming what "
    "is specifically wrong — describe the observable symptom, not a generic label "
    "(e.g. 'Top third of text is obscured by a watermark' or "
    "'Characters alternate between Cyrillic and Latin with no language boundary'). "
    "Omit extraction_note when extraction_flags is absent or empty."
)


def _doc_type_instructions(doc_type: str) -> str:
    if doc_type == "scientific_paper":
        return _SCIENTIFIC_PAPER_INSTRUCTIONS
    if doc_type == "contract":
        return _CONTRACT_INSTRUCTIONS
    return ""


def _truncation_error(current_page: int) -> str:
    """Error text for a response cut off by max_tokens.

    A forced tool call truncated mid-JSON is discarded by the API (tool input
    arrives as an empty dict), so the failure must not be reported as 'no
    blocks extracted' — the corrective instruction is conciseness, not volume."""
    return (
        f"Model output for page {current_page} was truncated at {WORKER_MAX_TOKENS} "
        f"tokens (stop_reason=max_tokens) and the partial tool call was discarded. "
        f"Be more concise: shorten block text, summarise long table content, and omit "
        f"decorative text so the complete block list fits within the output limit."
    )


@retry(stop=stop_after_attempt(HTTP_MAX_RETRIES), wait=wait_exponential(multiplier=RETRY_BACKOFF_MULTIPLIER, min=RETRY_BACKOFF_MIN_SECONDS, max=RETRY_BACKOFF_MAX_SECONDS))
async def _call_api(client: AsyncAnthropic, messages: list, tool_definition: dict) -> Any:
    return await client.messages.create(
        model=MODEL,
        max_tokens=WORKER_MAX_TOKENS,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": tool_definition["name"]},
        messages=messages,
    )


async def window_parser_node(state: dict[str, Any]) -> dict[str, Any]:
    async with _get_semaphore():
        client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        current_page = state["current_page"]
        _, tool_definition = SchemaRegistry().get_schema_and_tool(state["document_type"])
        pdf_base64 = await encode_pdf_async(state["file_path"])

        doc_type = state["document_type"]
        extra_instructions = _doc_type_instructions(doc_type)
        content = [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64},
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": (
                    f"CRITICAL TASK: Extract structure elements EXCLUSIVELY located on physical "
                    f"Page {current_page}. Coordinates must follow [ymin, xmin, ymax, xmax] order. "
                    f"If a block's text is cut off at the bottom of the page and continues at the "
                    f"top of the next page, set is_continued=true. Leave is_continued=false (or "
                    f"omit it) for all complete blocks. "
                    f"Use the tool '{tool_definition['name']}' to return structured data matching "
                    f"the schema parameters.{extra_instructions}{_EXTRACTION_FLAGS_INSTRUCTION}"
                ),
            },
        ]

        if state.get("last_validation_error"):
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"PREVIOUS VALIDATION ERROR:\n{state['last_validation_error']}\n"
                        f"Fix the schema alignment issue in your response."
                    ),
                }
            )

        response = await _call_api(client, [{"role": "user", "content": content}], tool_definition)
        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_block is None:
            raise ValueError(
                f"API returned no tool_use block for page {current_page}. "
                f"Content types: {[b.type for b in response.content]}"
            )
        if response.stop_reason == "max_tokens":
            # Truncated tool JSON is discarded by the API — any blocks present are
            # unusable. Return empty so the graph-level retry fires, and pass the
            # truncation detail for retry_incrementor_node to surface.
            return {
                "extracted_flat_blocks": [],
                "truncation_error": _truncation_error(current_page),
            }
        blocks = tool_block.input.get("blocks", [])
        if isinstance(blocks, str):
            # Claude occasionally serialises the array as a JSON string inside the tool call.
            try:
                blocks = json.loads(blocks)
            except (json.JSONDecodeError, ValueError):
                blocks = []
        if not isinstance(blocks, list):
            blocks = []
        return {"extracted_flat_blocks": blocks, "truncation_error": None}


async def burst_worker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Like window_parser_node but with inline validation-retry (up to VALIDATION_MAX_RETRIES attempts).

    Burst pages have no graph-level retry loop, so validation failures are
    retried inline. After VALIDATION_MAX_RETRIES failed attempts the node degrades
    gracefully: it returns whatever blocks were last produced with an extraction warning."""
    async with _get_semaphore():
        client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        current_page = state["current_page"]
        doc_type = state["document_type"]
        _, tool_definition = SchemaRegistry().get_schema_and_tool(doc_type)
        pdf_base64 = await encode_pdf_async(state["file_path"])
        extra_instructions = _doc_type_instructions(doc_type)

        last_error: str | None = None

        for attempt in range(1, VALIDATION_MAX_RETRIES + 1):
            content: list = [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64},
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": (
                        f"CRITICAL TASK: Extract structure elements EXCLUSIVELY located on physical "
                        f"Page {current_page}. Coordinates must follow [ymin, xmin, ymax, xmax] order. "
                        f"If a block's text is cut off at the bottom of the page and continues at the "
                        f"top of the next page, set is_continued=true. Leave is_continued=false (or "
                        f"omit it) for all complete blocks. "
                        f"Use the tool '{tool_definition['name']}' to return structured data matching "
                        f"the schema parameters.{extra_instructions}{_EXTRACTION_FLAGS_INSTRUCTION}"
                    ),
                },
            ]
            if last_error:
                content.append({
                    "type": "text",
                    "text": f"PREVIOUS VALIDATION ERROR:\n{last_error}\nFix the schema alignment issue in your response.",
                })

            response = await _call_api(client, [{"role": "user", "content": content}], tool_definition)
            tool_block = next((b for b in response.content if b.type == "tool_use"), None)
            if tool_block is None:
                raise ValueError(
                    f"API returned no tool_use block for page {current_page}. "
                    f"Content types: {[b.type for b in response.content]}"
                )

            blocks = tool_block.input.get("blocks", [])
            if isinstance(blocks, str):
                try:
                    blocks = json.loads(blocks)
                except (json.JSONDecodeError, ValueError):
                    blocks = []
            if not isinstance(blocks, list):
                blocks = []

            if response.stop_reason == "max_tokens":
                # Truncated tool JSON is discarded by the API — any blocks present
                # are unusable. Retry with a conciseness instruction, not a
                # 'return more blocks' nudge.
                blocks = []
                last_error = _truncation_error(current_page)
            elif not blocks:
                last_error = (
                    f"No blocks were extracted for page {current_page}. "
                    "Return at least one block covering this page's content."
                )
            else:
                try:
                    SchemaRegistry().validate(doc_type, {"document_type": doc_type, "blocks": blocks})
                    return {"extracted_flat_blocks": blocks}
                except jsonschema.ValidationError as e:
                    path = " → ".join(str(p) for p in e.absolute_path) or "root"
                    last_error = f"Field '{path}': {e.message}"

            if attempt == VALIDATION_MAX_RETRIES:
                return {
                    "extracted_flat_blocks": blocks,
                    "extraction_warnings": [
                        f"Page {current_page}: schema validation failed after {VALIDATION_MAX_RETRIES} attempts. "
                        f"Last error: {last_error}"
                    ],
                }

        return {"extracted_flat_blocks": []}  # unreachable; satisfies type checker
