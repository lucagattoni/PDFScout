import os

from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import (
    CLASSIFIER_MAX_TOKENS,
    FALLBACK_DOC_TYPE,
    HTTP_MAX_RETRIES,
    MODEL,
    RETRY_BACKOFF_MAX_SECONDS,
    RETRY_BACKOFF_MIN_SECONDS,
    RETRY_BACKOFF_MULTIPLIER,
    SUPPORTED_DOC_TYPES,
)
from src.schema_registry import SchemaRegistry
from src.utils.pdf_utils import encode_pdf_async


@retry(stop=stop_after_attempt(HTTP_MAX_RETRIES), wait=wait_exponential(multiplier=RETRY_BACKOFF_MULTIPLIER, min=RETRY_BACKOFF_MIN_SECONDS, max=RETRY_BACKOFF_MAX_SECONDS))
async def _classify(client: AsyncAnthropic, pdf_base64: str) -> str:
    response = await client.messages.create(
        model=MODEL,
        max_tokens=CLASSIFIER_MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64,
                        },
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Classify this document. Return ONLY one token from "
                            f"{sorted(SUPPORTED_DOC_TYPES)}."
                        ),
                    },
                ],
            }
        ],
    )
    return response.content[0].text.strip().lower()


async def classifier_node(state: dict) -> dict:
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    pdf_base64 = await encode_pdf_async(state["file_path"])
    doc_type = await _classify(client, pdf_base64)

    if doc_type not in SUPPORTED_DOC_TYPES:
        doc_type = FALLBACK_DOC_TYPE

    schema, _ = SchemaRegistry().get_schema_and_tool(doc_type)
    return {"document_type": doc_type, "target_json_schema": schema}
