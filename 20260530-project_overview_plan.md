# Project Handover Specification: Agnostic Multi-Agent PDF Structure Extractor

This document establishes the architectural blueprint, structural goals, and execution roadmap for an open-source, layout-agnostic PDF structure-to-JSON extractor. It utilizes a stateful multi-agent system powered by LangGraph, optimized for token consumption using Claude's prompt caching primitives, and managed via `uv`.

---

## 1. Project Overview & Execution Goals

Traditional PDF layout extractors break when exposed to structurally complex, multi-column, or non-deterministic layouts (e.g., corporate brochures, academic whitepapers, complex financial sheets). This project shifts the parsing burden from brittle regex/heuristic parsers to an optimized visual-textual multi-agent loop.

### Core Strategic Goals

* **Layout Agnosticism:** The parser treats every document as a collection of generic spatial structures (headers, paragraphs, lists, tables). Specialized business definitions (e.g., invoice numbers, total amounts, abstract contents) are loaded dynamically as polymorphic data extensions.
* **Aggressive Cost Optimization:** The engine leverages Claude's **Prompt Caching** natively. The pioneer page (page 1) runs first to establish the global context in the provider's cache. All subsequent concurrent page requests then hit that cache, achieving a >90% cache-hit rate on input tokens.
* **Deterministic Output Execution:** The engine guarantees structure validation at the node boundary. If the pioneer page agent outputs schema-violating data, a closed-loop self-healing protocol routes through a dedicated `retry_incrementor_node` before re-running, up to 3 times, without breaking the execution flow.
* **Resilient State Management:** The pipeline maintains complete transactional integrity. If a network drop, API rate-limit, or crash occurs mid-document, the orchestrator resumes from the exact page checkpoint via SQLite thread tracking.

---

## 2. Technical Stack Specification

All development must rigidly adhere to this foundational modern Python stack:

* **Package & Runtime Manager:** `uv` (Fast Python packaging, script execution, and project lock management).
* **Agentic State Machine:** `LangGraph` (v0.2+ structured state-graph management with persistent checkpointers and the Send API for parallel dispatch).
* **State Persistence Engine:** `SQLite3` via LangGraph's native `AsyncSqliteSaver` (Write-Ahead Logging enabled).
* **Inference Engine Model:** Anthropic `claude-sonnet-4-6` — centralized in `src/config.py` so all nodes reference a single constant.
* **Data Validation Layer:** `jsonschema` (v4.22+) for runtime validation of LLM output against the JSON Schema Draft-07 blueprint files. Pydantic v2 is used only for the native extractor's internal data models (`NativeWord`, `NativePageMetadata`), not for schema registry validation. `TypeAdapter` is explicitly **not** used for JSON Schema dict validation — it does not accept raw schema dicts.
* **API Resilience:** `tenacity` (v8.3+) — all Anthropic API call sites are decorated with `@retry(stop=stop_after_attempt(3), wait=wait_exponential(...))` to handle transient 429/529 errors without manual intervention.
* **Native Extractor Engine:** `pdfplumber` (De-coupled via the Strategy Design Pattern to support seamless future migration to `pypdfium2`).

---

## 3. Architecture & Multi-Agent Component Layout

The extraction pipeline is split into distinct sequential and parallel execution phases:

1. **Native Abstraction Layer:** Runs locally. Uses `pdfplumber` to extract text strings alongside raw coordinate vectors. Also computes a SHA-256 hash of the PDF file, used as the LangGraph `thread_id` for checkpoint resumption.
2. **Classifier Agent Node:** Reads the raw text of the first page. Returns one of the supported document type tokens (e.g., `"invoice"`, `"scientific_paper"`). If the returned value is not in `SUPPORTED_DOC_TYPES`, it falls back gracefully to `"baseline_core"` instead of crashing.
3. **Pioneer Parser Node (`pioneer_parser`):** Passes page 1 text and coordinates to Claude via tool-calling. The global metadata payload is sent with `cache_control: ephemeral` to commit it to the provider's cache. This is a dedicated graph node (separate from the burst `parser_worker` node) with its own routing edge for validation and retry.
4. **Pioneer Validation & Self-Healing Loop:** After `pioneer_parser` completes, a routing function validates page 1's extracted blocks using `jsonschema.validate()`. On failure, it routes to `retry_incrementor_node` (which increments `retry_count` and writes the error message to state) before re-entering `pioneer_parser`. After 3 failed retries, the route degrades gracefully to `burst_dispatcher`.
5. **Burst Dispatcher Node:** After page 1 is validated (or degraded), `burst_dispatcher` emits one `Send("parser_worker", ...)` object per remaining page via LangGraph's native Send API. LangGraph executes these concurrently. Each `parser_worker` invocation runs under a module-level `asyncio.Semaphore(CONCURRENCY_LIMIT)` to prevent TPM saturation. Single-page documents skip this phase and route directly to the hierarchy node.
6. **Geometric Pre-Sorter:** A local Python step inside the hierarchy node that aggregates all returned flat JSON blocks and sorts them by: page ASC → column bucket (xmin // `COLUMN_BUCKET_PX`) ASC → ymin ASC. The bucket width is a tunable constant in `src/config.py`.
7. **Hierarchy Agent Node:** Receives the sorted flat block sequence. Uses Claude tool-calling (with a structured `set_block_relations` schema) to assign `parent_id` mappings — eliminating the JSON fence stripping fragility of plain text output. Handles cross-page `is_continued` linkages and deduplicates blocks by `block_id` to guard against retry-accumulated duplicates.
8. **SQLite Checkpointer:** Flushes the completed session to disk. Thread ID is the PDF's SHA-256 hash, so re-running the same file resumes from its last valid checkpoint rather than creating a new session.

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

#### C. Language-Agnostic Schema Blueprint Registry

Document configurations are stored strictly as language-agnostic `.json` schema definition documents (Draft-07 specification standard). The registry resolves schemas at runtime using `jsonschema.validate()`. If no schema file is found for the classified document type, the registry silently falls back to `schemas/baseline_core.json`. `TypeAdapter` is not used here.

#### D. Localized Self-Healing Logic (Pioneer Page Only)

Self-healing applies exclusively to the pioneer page (page 1). The graph routes the context state through a dedicated `retry_incrementor_node` (which writes `retry_count + 1` and the validation error string to state) before re-entering `pioneer_parser`. After 3 retries, the engine degrades gracefully — page 1's partial output is included as-is and the burst phase continues. Pages 2–N are resilient via tenacity's API-level retry at the call site rather than graph-level routing.

---

## 4. Target Project Layout

```text
pdfscout/
│
├── .python-version             # 3.13
├── pyproject.toml              # uv-managed dependencies
│
├── schemas/                    # Agnostic JSON validation blueprints (Draft-07)
│   ├── baseline_core.json      # Generic fallback: 8-type enum, no domain metadata
│   ├── invoice.json            # Invoice-specific metadata extensions
│   └── scientific_paper.json   # Academic paper metadata additions
│
└── src/
    ├── __init__.py             # Marks src/ as a Python package
    ├── config.py               # Centralized constants: MODEL, CONCURRENCY_LIMIT, etc.
    ├── state.py                # Graph state definitions and merge reducers
    ├── schema_registry.py      # jsonschema loader and validation wrapper
    │
    ├── extractors/             # Spatial coordination layer (Strategy Pattern)
    │   ├── base.py             # Abstract base extraction contract
    │   └── plumber_engine.py   # Concrete implementation via pdfplumber
    │
    ├── nodes/                  # Discrete execution graph nodes
    │   ├── extractor_node.py   # PDF hashing + pdfplumber coordinate extraction
    │   ├── classifier_node.py  # Document type prediction with fallback
    │   ├── worker_node.py      # Core page extraction (pioneer + burst, shared function)
    │   ├── retry_node.py       # Increments retry_count and writes validation error to state
    │   └── hierarchy_node.py   # Geometric pre-sorter + tool-calling tree mapping agent
    │
    ├── edges.py                # pioneer_validation_route routing function
    └── graph.py                # LangGraph construction, Send API dispatch, SQLite compilation
```

---

## 5. Implementation Core Data Templates

### Central Configuration (`src/config.py`)

```python
MODEL = "claude-sonnet-4-6"
CONCURRENCY_LIMIT = 3       # asyncio.Semaphore cap across parallel burst pages
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper"}
FALLBACK_DOC_TYPE = "baseline_core"
COLUMN_BUCKET_PX = 50       # xmin bucket width for geometric pre-sorter column grouping
```

### State Definition (`src/state.py`)

```python
from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated

def merge_flat_blocks(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Appends newly extracted page blocks into the global accumulation array."""
    if not existing:
        return new
    if not new:
        return existing
    return existing + new

class PDFParserState(TypedDict):
    # Static Input
    file_path: str
    pdf_hash: str
    total_pages: int
    native_text_metadata: List[Dict[str, Any]]

    # Polymorphic Blueprint Configuration
    document_type: str
    target_json_schema: Dict[str, Any]

    # State Iteration Engine (pioneer page only)
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
from typing import List, Annotated
from pydantic import BaseModel, Field

class NativeWord(BaseModel):
    text: str
    # Pydantic v2: use min_length/max_length via Annotated, not min_items/max_items
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

## 6. Graph Topology

```
START
  └─► native_extractor
        └─► classifier
              └─► pioneer_parser (page 1, sequential — primes cache)
                    ├─► [validation failure, retry_count < 3] retry_node ──► pioneer_parser
                    └─► [validation pass OR retry_count >= 3] burst_dispatcher
                          ├─► [total_pages == 1] hierarchy_node
                          └─► [total_pages > 1]  Send("parser_worker", page=2)
                                                  Send("parser_worker", page=3)
                                                  ...
                                                  Send("parser_worker", page=N)
                                                    └─► (all merge via merge_flat_blocks)
                                                          └─► hierarchy_node
                                                                └─► END
```

---

## 7. Guidelines for Subsequent Agents

When picking up this project workflow, execute development tasks in this specific sequence:

1. **Environment Initialization:** Run `uv sync`. Install packages with `uv add langgraph anthropic pydantic pdfplumber jsonschema tenacity`.
2. **Schema Baseline First:** Implement `src/schema_registry.py` first. Write a quick test that calls `SchemaRegistry().validate("invoice", mock_payload)` with a deliberately malformed payload and confirms that `jsonschema.ValidationError` is raised.
3. **Config Centralization Check:** Confirm that all nodes import `MODEL` from `src/config.py` and never hardcode a model string. Running `grep -r "claude-" src/` should return zero results after setup.
4. **Cache Validation Check:** After implementing `src/nodes/worker_node.py`, run a test invocation against a real PDF and inspect `response.usage` — confirm that `cache_read_input_tokens` increases on the second (burst) page invocations.
5. **Send API Integration Test:** Run a 3-page PDF end-to-end and verify in logs that pages 2 and 3 are dispatched concurrently (timestamps should overlap). Check that `extracted_flat_blocks` after all pages contains blocks from all three pages.
6. **is_continued Edge Case:** Test with a mock document where a paragraph clips at a page boundary (`is_continued: true`) to confirm the hierarchy agent correctly links the first block of the next page as a child.
7. **Retry Loop Test:** Temporarily corrupt the schema to force validation failures and confirm that `retry_count` increments correctly (via `retry_incrementor_node`) and the pipeline degrades gracefully after 3 attempts.
