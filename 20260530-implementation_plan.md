This document provides a deterministic, zero-discretion execution plan for building the **Agnostic Multi-Agent PDF Structure Extractor**. It is structured as a step-by-step engineering pipeline. An AI agent or software engineer can execute these steps sequentially to generate a fully functioning system.

---

## Step 1: Environment & Dependency Initialization

Execute the following commands in the terminal using `uv` to establish the isolated runtime and locked dependencies.

```bash
# Initialize project directory structure
uv init pdfscout
cd pdfscout
mkdir -p schemas src/extractors src/nodes

# Add strict version-controlled dependencies
uv add "langgraph>=0.2.0" "anthropic>=0.30.0" "pydantic>=2.7.0" "pdfplumber>=0.11.0" "jsonschema>=4.22.0" "tenacity>=8.3.0"
```

Configure the generated `pyproject.toml` file to enforce Python 3.13:

```toml
[project]
name = "pdfscout"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "langgraph>=0.2.0",
    "anthropic>=0.30.0",
    "pydantic>=2.7.0",
    "pdfplumber>=0.11.0",
    "jsonschema>=4.22.0",
    "tenacity>=8.3.0",
]
```

---

## Step 2: Language-Agnostic Manifest Declarations

Create the static schema blueprint files. These files act as the source of truth for validation constraints and are also used verbatim as the `input_schema` in Claude tool definitions.

### File: `schemas/invoice.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgnosticInvoiceStructure",
  "type": "object",
  "properties": {
    "document_type": { "type": "string", "enum": ["invoice"] },
    "blocks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "block_id": { "type": "string" },
          "type": {
            "type": "string",
            "enum": ["title", "heading", "paragraph", "list_item", "table", "figure", "footnote", "margin_element"]
          },
          "bbox": {
            "type": "object",
            "properties": {
              "page_number": { "type": "integer" },
              "coordinates": { "type": "array", "items": { "type": "integer" }, "minItems": 4, "maxItems": 4 }
            },
            "required": ["page_number", "coordinates"]
          },
          "text": { "type": "string" },
          "is_continued": { "type": "boolean", "default": false },
          "metadata": {
            "type": "object",
            "properties": {
              "table_data": {
                "type": "object",
                "properties": {
                  "total_rows": { "type": "integer" },
                  "total_cols": { "type": "integer" },
                  "cells": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "r": { "type": "integer" },
                        "c": { "type": "integer" },
                        "rs": { "type": "integer" },
                        "cs": { "type": "integer" },
                        "value": { "type": "string" },
                        "is_header": { "type": "boolean", "default": false }
                      },
                      "required": ["r", "c", "rs", "cs", "value"]
                    }
                  }
                },
                "required": ["total_rows", "total_cols", "cells"]
              }
            }
          }
        },
        "required": ["block_id", "type", "bbox", "text"]
      }
    }
  },
  "required": ["document_type", "blocks"]
}
```

### File: `schemas/baseline_core.json`

Generic fallback schema used when the classifier returns an unknown document type. Contains only the shared 8-type block enum with no domain-specific metadata constraints.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "BaselineCoreStructure",
  "type": "object",
  "properties": {
    "document_type": { "type": "string" },
    "blocks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "block_id": { "type": "string" },
          "type": {
            "type": "string",
            "enum": ["title", "heading", "paragraph", "list_item", "table", "figure", "footnote", "margin_element"]
          },
          "bbox": {
            "type": "object",
            "properties": {
              "page_number": { "type": "integer" },
              "coordinates": { "type": "array", "items": { "type": "integer" }, "minItems": 4, "maxItems": 4 }
            },
            "required": ["page_number", "coordinates"]
          },
          "text": { "type": "string" },
          "is_continued": { "type": "boolean", "default": false },
          "metadata": { "type": "object" }
        },
        "required": ["block_id", "type", "bbox", "text"]
      }
    }
  },
  "required": ["document_type", "blocks"]
}
```

---

## Step 3: Central Configuration

### File: `src/config.py`

Single source of truth for all tuneable constants. Every node imports from here — a value change propagates everywhere. Running `grep -r "claude-" src/` after setup should return zero results.

```python
MODEL = "claude-sonnet-4-6"
CONCURRENCY_LIMIT = 3       # asyncio.Semaphore cap across parallel burst page invocations
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper"}
FALLBACK_DOC_TYPE = "baseline_core"
COLUMN_BUCKET_PX = 50       # xmin bucket width for geometric pre-sorter column grouping
```

---

## Step 4: State & Contract Modeling

### File: `src/state.py`

```python
from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated

def merge_flat_blocks(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Appends sub-agent page payloads into a unified global accumulation array."""
    if not existing:
        return new
    if not new:
        return existing
    return existing + new

class PDFParserState(TypedDict):
    file_path: str
    pdf_hash: str
    total_pages: int
    native_text_metadata: List[Dict[str, Any]]
    document_type: str
    target_json_schema: Dict[str, Any]
    current_page: int
    retry_count: int
    last_validation_error: Optional[str]
    extracted_flat_blocks: Annotated[List[Dict[str, Any]], merge_flat_blocks]
    hierarchical_document_tree: Optional[Dict[str, Any]]
```

### File: `src/extractors/base.py`

Note: `min_items`/`max_items` are Pydantic v1 kwargs silently ignored in v2. Use `Annotated` with `Field(min_length=..., max_length=...)` instead.

```python
from abc import ABC, abstractmethod
from typing import List, Annotated
from pydantic import BaseModel, Field

class NativeWord(BaseModel):
    text: str
    bbox: Annotated[List[float], Field(min_length=4, max_length=4)]  # [ymin, xmin, ymax, xmax]

class NativePageMetadata(BaseModel):
    page_number: int
    raw_text: str
    words: List[NativeWord]
    dimensions: List[float]  # [width, height]

class BaseNativeExtractor(ABC):
    @abstractmethod
    def extract_document(self, file_path: str) -> List[NativePageMetadata]:
        pass
```

---

## Step 5: Concrete Extractor Implementation (`pdfplumber`)

### File: `src/extractors/plumber_engine.py`

```python
import pdfplumber
from src.extractors.base import BaseNativeExtractor, NativePageMetadata, NativeWord
from typing import List

class PlumberExtractor(BaseNativeExtractor):
    def extract_document(self, file_path: str) -> List[NativePageMetadata]:
        document_metadata = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                native_words = []
                for word in (page.extract_words() or []):
                    # Map pdfplumber coordinates (x0, top, x1, bottom) to [ymin, xmin, ymax, xmax]
                    bbox = [float(word["top"]), float(word["x0"]), float(word["bottom"]), float(word["x1"])]
                    native_words.append(NativeWord(text=word["text"], bbox=bbox))
                document_metadata.append(NativePageMetadata(
                    page_number=page_num,
                    raw_text=raw_text,
                    words=native_words,
                    dimensions=[float(page.width), float(page.height)]
                ))
        return document_metadata
```

---

## Step 6: Runtime Validation Factory

### File: `src/schema_registry.py`

Uses `jsonschema` for runtime validation against the JSON Schema Draft-07 files. `TypeAdapter` is explicitly not used here — Pydantic's `TypeAdapter` accepts Python type annotations, not raw JSON Schema dicts, and would silently treat a schema dict as `Dict[Any, Any]`.

```python
import json
import os
import jsonschema
from typing import Dict, Any, Tuple
from src.config import FALLBACK_DOC_TYPE

class SchemaRegistry:
    def __init__(self, schema_dir: str = "schemas"):
        self.schema_dir = schema_dir

    def _load_schema(self, doc_type: str) -> Dict[str, Any]:
        path = os.path.join(self.schema_dir, f"{doc_type}.json")
        if not os.path.exists(path):
            path = os.path.join(self.schema_dir, f"{FALLBACK_DOC_TYPE}.json")
        with open(path) as f:
            return json.load(f)

    def get_schema_and_tool(self, doc_type: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        schema = self._load_schema(doc_type)
        tool = {
            "name": f"extract_{doc_type}_structure",
            "description": f"Outputs structured semantic and layout blocks for a {doc_type} document.",
            "input_schema": schema
        }
        return schema, tool

    def validate(self, doc_type: str, payload: Dict[str, Any]) -> None:
        """Raises jsonschema.ValidationError if payload violates the schema."""
        schema = self._load_schema(doc_type)
        jsonschema.validate(instance=payload, schema=schema)
```

---

## Step 7: LangGraph Node Implementations

### File: `src/__init__.py`

```python
```

Empty file — marks `src/` as a Python package so that `from src.xxx import yyy` imports resolve correctly.

---

### File: `src/nodes/extractor_node.py`

```python
import hashlib
from typing import Dict, Any
from src.extractors.plumber_engine import PlumberExtractor

def native_extractor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    file_path = state["file_path"]

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        hasher.update(f.read())
    pdf_hash = hasher.hexdigest()

    extractor = PlumberExtractor()
    metadata_objects = extractor.extract_document(file_path)

    return {
        "pdf_hash": pdf_hash,
        "total_pages": len(metadata_objects),
        "native_text_metadata": [p.model_dump() for p in metadata_objects],
        "current_page": 1,
        "retry_count": 0,
        "last_validation_error": None,
        "extracted_flat_blocks": []
    }
```

---

### File: `src/nodes/classifier_node.py`

Validates the returned token against `SUPPORTED_DOC_TYPES`. Falls back to `FALLBACK_DOC_TYPE` for unknown values rather than crashing with a `FileNotFoundError`. Uses `tenacity` for API resilience.

```python
import os
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import MODEL, SUPPORTED_DOC_TYPES, FALLBACK_DOC_TYPE
from src.schema_registry import SchemaRegistry

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _classify(client: Anthropic, first_page_text: str) -> str:
    response = client.messages.create(
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

def classifier_node(state: dict) -> dict:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    first_page_text = state["native_text_metadata"][0]["raw_text"][:4000]
    doc_type = _classify(client, first_page_text)

    if doc_type not in SUPPORTED_DOC_TYPES:
        doc_type = FALLBACK_DOC_TYPE

    schema, _ = SchemaRegistry().get_schema_and_tool(doc_type)
    return {"document_type": doc_type, "target_json_schema": schema}
```

---

### File: `src/nodes/worker_node.py`

Shared implementation for both the pioneer page (page 1, sequential) and all burst pages (2–N, concurrent via Send). The `cache_control: ephemeral` block on the global metadata payload establishes the cache on the pioneer call; all burst invocations then hit that warm cache.

Uses `asyncio.Semaphore` (via `AsyncAnthropic`) to cap concurrent API calls and prevent TPM saturation.

```python
import asyncio
import os
import json
from typing import Dict, Any
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import MODEL, CONCURRENCY_LIMIT
from src.schema_registry import SchemaRegistry

_semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _call_api(client: AsyncAnthropic, messages: list, tool_definition: dict):
    return await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        temperature=0.0,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": tool_definition["name"]},
        messages=messages
    )

async def window_parser_node(state: Dict[str, Any]) -> Dict[str, Any]:
    async with _semaphore:
        client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        current_page = state["current_page"]
        _, tool_definition = SchemaRegistry().get_schema_and_tool(state["document_type"])

        content = [
            {
                "type": "text",
                "text": f"GLOBAL NATIVE TEXT METADATA FOR ALL PAGES:\n{json.dumps(state['native_text_metadata'])}",
                "cache_control": {"type": "ephemeral"}
            },
            {
                "type": "text",
                "text": (
                    f"CRITICAL TASK: Extract structure elements EXCLUSIVELY located on physical "
                    f"Page {current_page}. Use the tool '{tool_definition['name']}' to return "
                    f"structured data matching the schema parameters."
                )
            }
        ]

        if state.get("last_validation_error"):
            content.append({
                "type": "text",
                "text": (
                    f"PREVIOUS VALIDATION ERROR:\n{state['last_validation_error']}\n"
                    f"Fix the schema alignment issue in your response."
                )
            })

        response = await _call_api(client, [{"role": "user", "content": content}], tool_definition)
        tool_block = next(b for b in response.content if b.type == "tool_use")
        return {"extracted_flat_blocks": tool_block.input.get("blocks", [])}
```

---

### File: `src/nodes/retry_node.py`

Single-responsibility node that sits between a failed pioneer validation and the re-entry to `pioneer_parser`. Writes the incremented retry count and the error description to state before the parser re-runs.

```python
from typing import Dict, Any

def retry_incrementor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "retry_count": state["retry_count"] + 1,
        "last_validation_error": (
            "Schema violation detected on pioneer page extraction. "
            "Adjust block structure to match the target schema constraints."
        )
    }
```

---

### File: `src/nodes/hierarchy_node.py`

Uses tool-calling with a structured `set_block_relations` schema instead of text parsing. This eliminates the JSON markdown fence fragility of plain-text output. Deduplicates blocks by `block_id` before hierarchy assignment to guard against duplicates introduced by the pioneer retry loop (which appends via `merge_flat_blocks`).

```python
import asyncio
import os
import json
from typing import Dict, Any, List
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

def geometric_pre_sorter(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sorts blocks deterministically: page ASC → column bucket ASC → ymin ASC.
    COLUMN_BUCKET_PX controls how finely columns are grouped; tune in src/config.py."""
    def sort_key(b):
        page = b["bbox"]["page_number"]
        ymin, xmin, _, _ = b["bbox"]["coordinates"]
        return (page, xmin // COLUMN_BUCKET_PX, ymin)
    return sorted(blocks, key=sort_key)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _call_api(client: AsyncAnthropic, manifest: list):
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

async def layout_hierarchy_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Deduplicate by block_id before sorting — guards against pioneer retry duplicates
    seen_ids: set = set()
    unique_blocks = []
    for block in state["extracted_flat_blocks"]:
        if block["block_id"] not in seen_ids:
            seen_ids.add(block["block_id"])
            unique_blocks.append(block)

    sorted_blocks = geometric_pre_sorter(unique_blocks)

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
    tool_block = next(b for b in response.content if b.type == "tool_use")
    relations = tool_block.input.get("relations", [])
    relation_map = {r["block_id"]: r["parent_id"] for r in relations}

    for block in sorted_blocks:
        block["parent_id"] = relation_map.get(block["block_id"])

    return {
        "hierarchical_document_tree": {
            "document_type": state["document_type"],
            "pdf_hash": state["pdf_hash"],
            "structured_payload": sorted_blocks
        }
    }
```

---

## Step 8: Routing Edges & Graph Construction

### File: `src/edges.py`

Uses `jsonschema.ValidationError` (not `pydantic.ValidationError`). Applies only to the pioneer page. Burst pages are resilient via tenacity at the API call site.

```python
import jsonschema
from typing import Dict, Any, Literal
from src.schema_registry import SchemaRegistry

def pioneer_validation_route(state: Dict[str, Any]) -> Literal["retry_node", "burst_dispatcher"]:
    """Routes after pioneer_parser completes. Validates page 1 blocks only."""
    active_blocks = [
        b for b in state["extracted_flat_blocks"]
        if b["bbox"]["page_number"] == 1
    ]
    payload = {"document_type": state["document_type"], "blocks": active_blocks}

    try:
        SchemaRegistry().validate(state["document_type"], payload)
        return "burst_dispatcher"
    except jsonschema.ValidationError:
        if state["retry_count"] < 3:
            return "retry_node"
        return "burst_dispatcher"  # degrade gracefully after 3 failed retries
```

---

### File: `src/graph.py`

Implements the full Send API map-reduce topology. `pioneer_parser` and `parser_worker` are separate graph nodes backed by the same `window_parser_node` function. This is required because LangGraph applies conditional edges per node name — using the same node for both sequential and parallel phases would cause all burst completions to re-trigger the pioneer validation route.

```python
from typing import List, Union
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from src.state import PDFParserState
from src.nodes.extractor_node import native_extractor_node
from src.nodes.classifier_node import classifier_node
from src.nodes.worker_node import window_parser_node
from src.nodes.retry_node import retry_incrementor_node
from src.nodes.hierarchy_node import layout_hierarchy_agent_node
from src.edges import pioneer_validation_route

def dispatch_pages(state: PDFParserState) -> Union[List[Send], str]:
    """Dispatches pages 2-N as concurrent Send tasks. Single-page docs skip to hierarchy."""
    if state["total_pages"] < 2:
        return "hierarchy_node"
    return [
        Send("parser_worker", {**state, "current_page": page, "last_validation_error": None})
        for page in range(2, state["total_pages"] + 1)
    ]

workflow = StateGraph(PDFParserState)

# Node Registry
workflow.add_node("native_extractor", native_extractor_node)
workflow.add_node("classifier", classifier_node)
workflow.add_node("pioneer_parser", window_parser_node)   # page 1 — has pioneer routing
workflow.add_node("retry_node", retry_incrementor_node)
workflow.add_node("burst_dispatcher", lambda state: {})   # passthrough; routing via conditional edge
workflow.add_node("parser_worker", window_parser_node)    # pages 2-N — dispatched via Send
workflow.add_node("hierarchy_node", layout_hierarchy_agent_node)

# Graph Topology
workflow.add_edge(START, "native_extractor")
workflow.add_edge("native_extractor", "classifier")
workflow.add_edge("classifier", "pioneer_parser")

workflow.add_conditional_edges(
    "pioneer_parser",
    pioneer_validation_route,
    {
        "retry_node": "retry_node",
        "burst_dispatcher": "burst_dispatcher"
    }
)
workflow.add_edge("retry_node", "pioneer_parser")

# burst_dispatcher uses conditional edges to return Send objects for concurrent dispatch
workflow.add_conditional_edges(
    "burst_dispatcher",
    dispatch_pages,
    ["parser_worker", "hierarchy_node"]
)
workflow.add_edge("parser_worker", "hierarchy_node")
workflow.add_edge("hierarchy_node", END)

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
memory_checkpointer = AsyncSqliteSaver.from_conn_string("state_checkpoint.db")
compiled_extractor_app = workflow.compile(checkpointer=memory_checkpointer)
```

---

## Step 9: Execution Entry Point

### File: `main.py`

Thread ID is derived from the PDF's SHA-256 hash. Re-running the same file resumes from its last valid checkpoint rather than creating a new session. Hash computation is duplicated here from `native_extractor_node` to establish the thread ID before the graph starts streaming.

```python
import os
import sys
import asyncio
import json
import hashlib
from src.graph import compiled_extractor_app

def _compute_hash(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        hasher.update(f.read())
    return hasher.hexdigest()

async def main():
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("CRITICAL ENVIRONMENT ERROR: ANTHROPIC_API_KEY environment variable missing.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("EXECUTION ERROR: Missing file path. Usage: uv run main.py <path_to_pdf>")
        sys.exit(1)

    target_pdf = sys.argv[1]
    pdf_hash = _compute_hash(target_pdf)
    config = {"configurable": {"thread_id": pdf_hash}}
    initial_inputs = {"file_path": target_pdf}

    print(f"Initializing extraction pipeline for: {target_pdf} (thread: {pdf_hash[:8]}...)")

    async for event in compiled_extractor_app.stream(initial_inputs, config):
        for node_name in event:
            print(f"[GRAPH] Node '{node_name}' completed.")

    final_state = await compiled_extractor_app.get_state(config)
    tree_result = final_state.values.get("hierarchical_document_tree")

    print("\nExtraction complete. Output tree:\n")
    print(json.dumps(tree_result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
```

To run the completed architecture:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
uv run main.py path/to/target_document.pdf
```
