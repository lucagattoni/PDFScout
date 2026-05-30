import os
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import MODEL, SUPPORTED_DOC_TYPES, FALLBACK_DOC_TYPE
from src.schema_registry import SchemaRegistry


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _classify(client: AsyncAnthropic, first_page_text: str) -> str:
    response = await client.messages.create(
        model=MODEL,
        max_tokens=10,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": (
                f"Classify this document. Return ONLY one token from {sorted(SUPPORTED_DOC_TYPES)}. "
                f"Text:\n{first_page_text}"
            )
        }]
    )
    return response.content[0].text.strip().lower()


async def classifier_node(state: dict) -> dict:
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    first_page_text = state["native_text_metadata"][0]["raw_text"][:4000]
    doc_type = await _classify(client, first_page_text)

    if doc_type not in SUPPORTED_DOC_TYPES:
        doc_type = FALLBACK_DOC_TYPE

    schema, _ = SchemaRegistry().get_schema_and_tool(doc_type)
    return {"document_type": doc_type, "target_json_schema": schema}
