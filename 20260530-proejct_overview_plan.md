# Project Handover Specification: Agnostic Multi-Agent PDF Structure Extractor

This document establishes the architectural blueprint, structural goals, and execution roadmap for an open-source, layout-agnostic PDF structure-to-JSON extractor. It utilizes a stateful multi-agent system powered by LangGraph, optimized for token consumption using Claude’s prompt caching primitives, and managed via `uv`.

---

## 1. Project Overview & Execution Goals

Traditional PDF layout extractors break when exposed to structurally complex, multi-column, or non-deterministic layouts (e.g., corporate brochures, academic whitepapers, complex financial sheets). This project shifts the parsing burden from brittle regex/heuristic parsers to an optimized visual-textual multi-agent loop.

### Core Strategic Goals

* **Layout Agnosticism:** The parser treats every document as a collection of generic spatial structures (headers, paragraphs, lists, tables). Specialized business definitions (e.g., invoice numbers, total amounts, abstract contents) are loaded dynamically as polymorphic data extensions.
* **Aggressive Cost Optimization:** The engine leverages Claude’s **Prompt Caching** natively. By caching massive global document data arrays upfront, downstream concurrent queries achieve a >90% cache hit rate on input tokens.
* **Deterministic Output Execution:** The engine guarantees structure validation at the database edge. If an agent outputs schema-violating data, a closed-loop self-healing protocol triggers localized rewrites without breaking the execution flow.
* **Resilient State Management:** The pipeline maintains complete transactional integrity. If a network drop, API rate-limit, or crash occurs mid-document, the orchestrator instantly resumes execution from the exact page checkpoint.

---

## 2. Technical Stack Specification

All development must rigidly adhere to this foundational modern Python stack:

* **Package & Runtime Manager:** `uv` (Fast Python packaging, script execution, and project lock management).
* **Agentic State Machine:** `LangGraph` (v0.2+ structured state-graph management with persistent checkpointers).
* **State Persistence Engine:** `SQLite3` via LangGraph's native `AsyncSqliteSaver` (Write-Ahead Logging enabled).
* **Inference Engine Model:** Anthropic `Claude 3.5 Sonnet` (Targeting native Prompt Caching and structured tool-calling endpoints).
* **Data Validation Layer:** `Pydantic v2` (Specifically using `TypeAdapter` for runtime dynamic JSON Schema evaluation).
* **Native Extractor Engine:** `pdfplumber` (De-coupled via the Strategy Design Pattern to support seamless future migration to `pypdfium2`).

---

## 3. Architecture & Multi-Agent Component Layout

The extraction pipeline is split into distinct sequential and parallel execution phases:

1. **Native Abstraction Layer:** Runs locally. Uses `pdfplumber` to extract text strings alongside raw coordinate vectors.
2. **Classifier Agent Node:** Looks at the raw text of the initial page. Predicts the overall document type and fetches the corresponding dynamic validation blueprint schema from the registry.
3. **Pioneer Page Node:** Passes Page 1 text and visual tokens to Claude. This single sequential call forces the LLM provider's edge servers to tokenize and commit the heavy global context block to their ephemeral cache.
4. **Throttled Burst Map (Send API):** Spawns concurrent page parsing threads for Pages 2 through $N$. To prevent hitting provider Tokens Per Minute (TPM) ceilings, execution concurrency is gated locally using an `asyncio.Semaphore`.
5. **Geometric Pre-Sorter:** A programmatic Python step that aggregates the returned flat JSON blocks, sorting them sequentially by page, parsing vertical reading lines via `ymin`, and grouping split columns via `xmin`.
6. **Hierarchy Agent Node:** Receives the sorted flat block sequence. Evaluates parent-child layout bonds, links items to header IDs, and bridges text blocks containing `is_continued: true` flags across page breaks.
7. **SQLite Checkpointer:** Resolves the validated, fully nested document tree and flushes the completed session to disk.

### Detailed Component Specifications

#### A. The Agnostic Core Schema Manifesto

All parsed structures must normalize down to a strict **8-type enum layout block**: `title`, `heading`, `paragraph`, `list_item`, `table`, `figure`, `footnote`, `margin_element`.
Polymorphic sub-structures (like detailed financial invoice totals or academic metadata) are injected exclusively inside a catch-all `metadata` field.

#### B. The Normalized Cell Map Table Protocol

Tables must be extracted into a compressed, structural coordinate matrix format inside the `metadata.table_data` layout to handle multi-row or multi-column cell spans flawlessly:

* `r`: Row index (Integer)
* `c`: Column index (Integer)
* `rs`: Row span (Integer)
* `cs`: Column span (Integer)
* `value`: Underlying text slice string
* `is_header`: Boolean flag

#### C. Language-Agnostic Schema Blueprint Registry (Strategy 1)

Document configurations are stored strictly as language-agnostic `.json` schema definition documents (Draft-07 specification standard). The validation runtime loads these blueprints into Pydantic `TypeAdapter` objects on the fly, eliminating any hard dependency on dynamic runtime class compilation (`create_model`).

#### D. Localized Self-Healing Logic (The Pragmatic Tracker)

If a sub-agent's layout payload fails validation against the active JSON Schema template, the graph routes the context state to a repair loop up to $N$ times. The engine captures the exact Pydantic `ValidationError` exception string, appends it as a dynamic system prompt modifier, and forces an autonomous remediation pass.

---

## 4. Target Project Layout

The repository setup should be initialized using `uv init` according to this directory blueprint:

```text
vlm-pdf-extractor/
│
├── .python-version             # Targeted python environment (e.g., 3.12)
├── pyproject.toml              # Project dependencies managed via uv
│
├── schemas/                    # Agnostic JSON validation blueprints
│   ├── baseline_core.json      # Shared fallback baseline schema
│   ├── invoice.json            # Invoice dynamic metadata structures
│   └── scientific_paper.json   # Structural paper metadata additions
│
└── src/
    ├── __init__.py
    ├── state.py                # Graph state definitions and type constraints
    ├── schema_registry.py      # Schema dictionary loader & Pydantic TypeAdapters
    │
    ├── extractors/             # Spatial coordination layer
    │   ├── base.py             # Abstract base extraction strategy contract
    │   └── plumber_engine.py   # Concrete implementation via pdfplumber
    │
    ├── nodes/                  # Discrete execution graph nodes
    │   ├── extractor_node.py   # Handles initial coordinates processing
    │   ├── classifier_node.py  # Predicts document types
    │   ├── worker_node.py      # Core page extraction and prompt caching logic
    │   └── hierarchy_node.py   # Code pre-sorter + tree mapping agent
    │
    ├── edges.py                # Validation routing and state retry logic
    └── graph.py                # LangGraph construction and SQLite compilation

```

---

## 5. Implementation Core Data Templates

### State Definition (`src/state.py`)

```python
from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated

def merge_flat_blocks(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Appends newly discovered flat blocks into a single global array channel."""
    return existing + new

class PDFParserState(TypedDict):
    # Static Data Input
    file_path: str
    pdf_hash: str
    total_pages: int
    native_text_metadata: List[Dict[str, Any]]
    
    # Polymorphic Blueprint Configuration
    document_type: str
    target_json_schema: Dict[str, Any]
    
    # State Iteration Engine
    current_page: int
    retry_count: int
    last_validation_error: Optional[str]
    
    # Aggregate Buffers
    extracted_flat_blocks: Annotated[List[Dict[str, Any]], merge_flat_blocks]
    hierarchical_document_tree: Optional[Dict[str, Any]]

```

### Extractor Strategy Contract (`src/extractors/base.py`)

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import List

class NativeWord(BaseModel):
    text: str
    bbox: List[float] = Field(..., min_items=4, max_items=4) # Standardized to: [ymin, xmin, ymax, xmax]

class NativePageMetadata(BaseModel):
    page_number: int
    raw_text: str
    words: List[NativeWord]
    dimensions: List[float] # [width, height] of canvas context

class BaseNativeExtractor(ABC):
    @abstractmethod
    def extract_document(self, file_path: str) -> List[NativePageMetadata]:
        """Reads document and normalizes structural spatial dimensions."""
        pass

```

---

## 6. Guidelines for Subsequent Agents

When picking up this project workflow, execute development tasks in this specific sequence:

1. **Environment Initialization:** Install the environment using `uv sync`. Add key project packages using `uv add langgraph anthropic pydantic pdfplumber`.
2. **Schema Baseline Verification:** Implement `src/schema_registry.py` first. Ensure that validation loops cleanly flag irregular table test inputs using a mock Pydantic `TypeAdapter` call before constructing the graph loops.
3. **Cache Validation Check:** Implement `src/nodes/worker_node.py`. Run a quick test script to visually inspect the Anthropic API response metadata, validating that the `cache_read_tokens` count matches the footprint of your global context data payload.
4. **Stitching Edge Validation:** When testing the `hierarchy_node.py`, pass a mock edge case document where a paragraph intentionally clips at the page boundary to confirm that the `is_continued` state flag safely reconciles and merges the nodes.