import os

from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import FALLBACK_DOC_TYPE, MODEL, SUPPORTED_DOC_TYPES
from src.schema_registry import SchemaRegistry
from src.utils.pdf_utils import encode_pdf_async


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _classify(client: AsyncAnthropic, pdf_base64: str) -> str:
    response = await client.messages.create(
        model=MODEL,
        max_tokens=10,
        temperature=0.0,
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
