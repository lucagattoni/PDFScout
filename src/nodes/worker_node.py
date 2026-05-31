import asyncio
import os
from typing import Any

from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import CONCURRENCY_LIMIT, MODEL
from src.schema_registry import SchemaRegistry
from src.utils.pdf_utils import encode_pdf_async

_semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _call_api(client: AsyncAnthropic, messages: list, tool_definition: dict) -> Any:
    return await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        temperature=0.0,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": tool_definition["name"]},
        messages=messages,
    )


async def window_parser_node(state: dict[str, Any]) -> dict[str, Any]:
    async with _semaphore:
        client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        current_page = state["current_page"]
        _, tool_definition = SchemaRegistry().get_schema_and_tool(state["document_type"])
        pdf_base64 = await encode_pdf_async(state["file_path"])

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
                    f"Use the tool '{tool_definition['name']}' to return structured data matching "
                    f"the schema parameters."
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
        return {"extracted_flat_blocks": tool_block.input.get("blocks", [])}
