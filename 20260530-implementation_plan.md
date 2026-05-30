This document provides a deterministic, zero-discretion execution plan for building the **Agnostic Multi-Agent PDF Structure Extractor**. It is structured as an step-by-step engineering pipeline. An AI agent or software engineer can execute these steps sequentially to generate a fully functioning system.

---

## Step 1: Environment & Dependency Initialization

Execute the following commands in the terminal using `uv` to establish the isolated runtime and locked dependencies.

```bash
# Initialize project directory structure
uv init vlm-pdf-extractor
cd vlm-pdf-extractor
mkdir -p schemas src/extractors src/nodes

# Add strict version-controlled dependencies
uv add "langgraph>=0.2.0" "anthropic>=0.30.0" "pydantic>=2.7.0" "pdfplumber>=0.11.0"

```

Configure the generated `pyproject.toml` file to enforce Python 3.12:

```toml
[project]
name = "vlm-pdf-extractor"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langgraph>=0.2.0",
    "anthropic>=0.30.0",
    "pydantic>=2.7.0",
    "pdfplumber>=0.11.0",
]

```

---

## Step 2: Language-Agnostic Manifest Declarations

Create the static schema blueprint files. These files act as the source of truth for validation constraints.

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

---

## Step 3: State & Contract Modeling

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

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import List

class NativeWord(BaseModel):
    text: str
    bbox: List[float] = Field(..., min_items=4, max_items=4)  # Format: [ymin, xmin, ymax, xmax]

class NativePageMetadata(BaseModel):
    page_number: int
    raw_text: str
    words: List[NativeWord]
    dimensions: List[float]  # Format: [width, height]

class BaseNativeExtractor(ABC):
    @abstractmethod
    def extract_document(self, file_path: str) -> List[NativePageMetadata]:
        pass

```

---

## Step 4: Concrete Extractor Implementation (`pdfplumber`)

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
                words_list = page.extract_words() or []
                
                for word in words_list:
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

## Step 5: Runtime Validation Factory

### File: `src/schema_registry.py`

```python
import json
import os
from typing import Dict, Any, Tuple
from pydantic import TypeAdapter

class SchemaRegistry:
    def __init__(self, schema_dir: str = "schemas"):
        self.schema_dir = schema_dir

    def get_validator_and_tool(self, doc_type: str) -> Tuple[TypeAdapter, Dict[str, Any]]:
        file_path = os.path.join(self.schema_dir, f"{doc_type}.json")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Schema configuration blueprint not found for type: {doc_type}")
            
        with open(file_path, "r") as f:
            raw_schema = json.load(f)
            
        validator = TypeAdapter(raw_schema)
        
        claude_tool = {
            "name": f"extract_{doc_type}_structure",
            "description": f"Outputs the structured semantic and layout blocks for a given {doc_type} document.",
            "input_schema": raw_schema
        }
        return validator, claude_tool

```

---

## Step 6: LangGraph Node Implementations

### File: `src/nodes/extractor_node.py`

```python
import hashlib
from typing import Dict, Any
from src.extractors.plumber_engine import PlumberExtractor

def native_extractor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    file_path = state["file_path"]
    
    # Generate deterministic hash for checkpoint tracking verification
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

### File: `src/nodes/classifier_node.py`

```python
import os
from typing import Dict, Any
from anthropic import Anthropic

def classifier_node(state: Dict[str, Any]) -> Dict[str, Any]:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    first_page_text = state["native_text_metadata"][0]["raw_text"][:4000]
    
    prompt = f"Analyze the text snippet from the first page of a document and classify it. Only return one of these exact tokens: ['invoice']. Text:\n{first_page_text}"
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=10,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}]
    )
    
    doc_type = response.content[0].text.strip().lower()
    from src.schema_registry import SchemaRegistry
    registry = SchemaRegistry()
    _, target_schema = registry.get_validator_and_tool(doc_type)
    
    return {
        "document_type": doc_type,
        "target_json_schema": target_schema["input_schema"]
    }

```

### File: `src/nodes/worker_node.py`

```python
import os
import json
from typing import Dict, Any
from anthropic import Anthropic

def window_parser_node(state: Dict[str, Any]) -> Dict[str, Any]:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    current_page = state["current_page"]
    doc_type = state["document_type"]
    
    from src.schema_registry import SchemaRegistry
    _, tool_definition = SchemaRegistry().get_validator_and_tool(doc_type)
    
    # Enforce strict prompt caching by placing the heavy global payload first
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"GLOBAL NATIVE TEXT METADATA FOR ALL PAGES:\n{json.dumps(state['native_text_metadata'])}",
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": f"CRITICAL TASK: Extract structure elements EXCLUSIVELY located on physical Page {current_page}. You must use the tool '{tool_definition['name']}' to return structured data matching the schema parameters."
                }
            ]
        }
    ]
    
    if state.get("last_validation_error"):
        messages[0]["content"].append({
            "type": "text",
            "text": f"PREVIOUS ERROR DETECTED: Your last attempt failed validation constraints with error:\n{state['last_validation_error']}\nModify your extraction behavior to correct this schema alignment issue."
        })

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4000,
        temperature=0.0,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": tool_definition["name"]},
        messages=messages
    )
    
    tool_use_block = next(b for b in response.content if b.type == "tool_use")
    extracted_blocks = tool_use_block.input.get("blocks", [])
    
    return {
        "extracted_flat_blocks": extracted_blocks
    }

```

### File: `src/nodes/hierarchy_node.py`

```python
import os
import json
from typing import Dict, Any, List

def geometric_pre_sorter(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sorts structural chunks deterministically: Page ASC -> xmin ASC -> ymin ASC."""
    def sort_key(b):
        page = b["bbox"]["page_number"]
        ymin, xmin, _, _ = b["bbox"]["coordinates"]
        return (page, xmin // 50, ymin)  # Intersects multi-columns within 50px zones
    return sorted(blocks, key=sort_key)

def layout_hierarchy_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    
    sorted_flat_blocks = geometric_pre_sorter(state["extracted_flat_blocks"])
    
    # Minimize processing tokens by passing spatial structure tracking instead of strings
    manifest = [
        {
            "block_id": b["block_id"],
            "type": b["type"],
            "bbox": b["bbox"],
            "text_preview": b["text"][:50]
        } for b in sorted_flat_blocks
    ]
    
    prompt = (
        "You are an expert Document Layout Tree Architect. You are given a flat list of structural layout elements ordered spatially.\n"
        "Your task is to calculate relational parenting mappings based on standard document reading orders.\n"
        "RULES:\n"
        "1. Nested content blocks (paragraphs, tables, list_items) directly following a 'heading' block must have their parent_id set to that heading's block_id.\n"
        "2. If an element has its 'is_continued' field flag marked True, map the first structural element of the next page to it.\n\n"
        f"Flat manifest:\n{json.dumps(manifest, indent=2)}\n\n"
        "Output a JSON map strictly matching this scheme: {'relations': [{'block_id': 'string', 'parent_id': 'string'}]}"
    )
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4000,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw_text = response.content[0].text
    relations = json.loads(raw_text).get("relations", [])
    relation_map = {r["block_id"]: r["parent_id"] for r in relations}
    
    for block in sorted_flat_blocks:
        block["parent_id"] = relation_map.get(block["block_id"], None)
        
    return {
        "hierarchical_document_tree": {
            "document_type": state["document_type"],
            "pdf_hash": state["pdf_hash"],
            "structured_payload": sorted_flat_blocks
        }
    }

```

---

## Step 7: Routing Edges & Graph Construction

### File: `src/edges.py`

```python
import json
from typing import Dict, Any, Literal
from pydantic import ValidationError
from src.schema_registry import SchemaRegistry

def validate_and_route(state: Dict[str, Any]) -> Literal["continue", "retry", "degrade"]:
    current_page = state["current_page"]
    doc_type = state["document_type"]
    
    # Isolate blocks extracted for the active processing window
    active_page_blocks = [
        b for b in state["extracted_flat_blocks"] 
        if b["bbox"]["page_number"] == current_page
    ]
    
    mock_payload = {
        "document_type": doc_type,
        "blocks": active_page_blocks
    }
    
    try:
        validator, _ = SchemaRegistry().get_validator_and_tool(doc_type)
        validator.validate_python(mock_payload)
        return "continue"
    except ValidationError as e:
        if state["retry_count"] < 3:
            return "retry"
        return "degrade"

```

### File: `src/graph.py`

```python
import asyncio
from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from src.state import PDFParserState
from src.nodes.extractor_node import native_extractor_node
from src.nodes.classifier_node import classifier_node
from src.nodes.worker_node import window_parser_node
from src.nodes.hierarchy_node import layout_hierarchy_agent_node
from src.edges import validate_and_route

# Semaphore boundary to prevent API gateway TPM saturation during burst execution
CONCURRENCY_SEMAPHORE = asyncio.Semaphore(3)

async def throttled_parallel_router(state: PDFParserState) -> Dict[str, Any]:
    total_pages = state["total_pages"]
    current_page = state["current_page"]
    
    # Phase 1: Pioneer Page (Page 1) Execution Loop
    if current_page == 1:
        route = validate_and_route(state)
        if route == "retry":
            return {"retry_count": state["retry_count"] + 1, "last_validation_error": "Schema violation on execution path."}
        elif route == "degrade":
            return {"current_page": 2, "retry_count": 0, "last_validation_error": None}
        else:
            return {"current_page": 2, "retry_count": 0, "last_validation_error": None}
            
    # Phase 2: Throttled Burst Processing Routing (Pages 2 through N)
    if current_page <= total_pages:
        async with CONCURRENCY_SEMAPHORE:
            # Executes the page execution task concurrently inside the restricted thread semaphore
            return {"current_page": state["current_page"] + 1}
            
    return {"current_page": total_pages + 1}

def routing_decision_edge(state: PDFParserState):
    if state["current_page"] == 1:
        route = validate_and_route(state)
        if route == "retry":
            return "parser_worker"
        return "router_node"
    if state["current_page"] <= state["total_pages"]:
        return "parser_worker"
    return "hierarchy_node"

workflow = StateGraph(PDFParserState)

# Node Registry
workflow.add_node("native_extractor", native_extractor_node)
workflow.add_node("classifier", classifier_node)
workflow.add_node("parser_worker", window_parser_node)
workflow.add_node("router_node", throttled_parallel_router)
workflow.add_node("hierarchy_node", layout_hierarchy_agent_node)

# Graph Topography Assembly
workflow.add_edge(START, "native_extractor")
workflow.add_edge("native_extractor", "classifier")
workflow.add_edge("classifier", "parser_worker")

workflow.add_conditional_edges(
    "parser_worker",
    routing_decision_edge,
    {
        "parser_worker": "parser_worker",
        "router_node": "router_node",
        "hierarchy_node": "hierarchy_node"
    }
)
workflow.add_edge("router_node", "parser_worker")
workflow.add_edge("hierarchy_node", END)

# Package with persistence tracking engine
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
memory_checkpointer = AsyncSqliteSaver.from_conn_string("state_checkpoint.db")
compiled_extractor_app = workflow.compile(checkpointer=memory_checkpointer)

```

---

## Step 8: Execution Entry Point

### File: `main.py`

```python
import os
import sys
import asyncio
import json
from src.graph import compiled_extractor_app

async def main():
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("CRITICAL ENVIRONMENT ERROR: ANTHROPIC_API_KEY environment variable missing.")
        sys.exit(1)
        
    if len(sys.argv) < 2:
        print("EXECUTION ERROR: Missing targeted file path input payload. Usage: uv run main.py <path_to_pdf>")
        sys.exit(1)
        
    target_pdf = sys.argv[1]
    
    # Establish transaction thread identification block for SQLite checkpoint restoration maps
    config = {"configurable": {"thread_id": "session_execution_001"}}
    initial_inputs = {"file_path": target_pdf}
    
    print(f"Initializing Multi-Agent Extraction Pipeline for document: {target_pdf}")
    
    async for event in compiled_extractor_app.stream(initial_inputs, config):
        for node_name, data in event.items():
            print(f"[GRAPH TRANSITION] Step Complete: Node '{node_name}' finished execution step context.")
            
    # Retrieve ultimate finalized execution state
    final_state = await compiled_extractor_app.get_state(config)
    tree_result = final_state.values.get("hierarchical_document_tree")
    
    print("\nExtraction Task Process Finalized. Output Tree Result Structure:\n")
    print(json.dumps(tree_result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())

```

To run the completed architecture, execute the following command:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
uv run main.py path/to/target_document.pdf

```
