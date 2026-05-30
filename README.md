# PDFScout · [Changelog](CHANGELOG.md)

An agnostic, multi-agent PDF structure extractor that converts any PDF document into a validated, hierarchical JSON tree. Built on LangGraph with Claude's native PDF vision API, prompt caching for cost efficiency, and a self-healing validation loop. Works on text-based and scanned documents alike.

---

## The Problem

Traditional PDF parsers break on structurally complex documents — multi-column academic papers, corporate brochures, dense financial sheets. Regex and heuristic approaches are brittle: they hardcode assumptions about layout that collapse the moment a document deviates from the expected template.

PDFScout shifts the parsing burden to a language model. It treats every document as a collection of generic spatial structures, lets Claude extract and classify them, and enforces schema correctness through a closed-loop validation protocol.

---

## What It Does

Given a PDF file, PDFScout:

1. Counts pages and validates the file is not encrypted using `pypdf` (lightweight, zero-dependency)
2. Classifies the document type (invoice, scientific paper, or a generic fallback) by sending the full PDF to Claude via the native PDF Chat API
3. Extracts structured content from every page in parallel via Claude tool-calling, with the PDF document block cached at the provider to minimize token costs — this works on scanned PDFs, complex multi-column layouts, and any document pdfplumber-style text extraction would fail on
4. Validates page 1's output against a JSON Schema blueprint and retries up to 3 times if the model produces malformed data
5. Assigns parent-child relationships across all extracted blocks using a geometry-informed hierarchy agent
6. Outputs a validated, hierarchical JSON document tree

State is persisted to SQLite after every node. If execution is interrupted, re-running the same PDF resumes from the last valid checkpoint.

---

## Architecture

The pipeline is a LangGraph state machine with two distinct execution phases — sequential for the pioneer page, concurrent for all remaining pages — joined by a map-reduce merge.

```
START
  └─► native_extractor          (local: pypdf page count + SHA-256 hash)
        └─► classifier           (Claude: returns document type token)
              └─► pioneer_parser (Claude: page 1, sequential — primes prompt cache)
                    ├─► [validation failure, retry_count < 3]
                    │     └─► retry_node ──► pioneer_parser
                    └─► [validation pass OR retry_count >= 3]
                          └─► burst_dispatcher
                                ├─► [single-page doc] ──► hierarchy_node
                                └─► [multi-page doc]
                                      Send("parser_worker", page=2)
                                      Send("parser_worker", page=3)
                                      ...
                                      Send("parser_worker", page=N)
                                        └─► (merge via merge_flat_blocks)
                                              └─► hierarchy_node
                                                    └─► END
```

### Nodes

| Node | Responsibility |
|---|---|
| `native_extractor` | Counts pages with `pypdf`, guards against encrypted PDFs, and computes a chunked SHA-256 hash used as the LangGraph thread ID |
| `classifier` | Sends the full PDF to Claude via the native PDF Chat API and returns one of the supported document type tokens; falls back to `baseline_core` for unknown values |
| `pioneer_parser` | Sends page 1 as a `document` block to Claude via tool-calling; marks the document block with `cache_control: ephemeral` to establish the provider's prompt cache for all subsequent burst calls |
| `retry_node` | Re-runs `jsonschema` validation to capture the specific error, increments `retry_count`, and writes the error detail to state for the model's next attempt |
| `burst_dispatcher` | Emits one `Send("parser_worker", ...)` per remaining page using LangGraph's Send API; writes a degradation warning to state if pioneer validation exhausted its retries |
| `parser_worker` | Same extraction logic as `pioneer_parser`, runs concurrently for pages 2–N under an `asyncio.Semaphore` to cap concurrent API calls |
| `hierarchy_node` | Deduplicates blocks by `block_id`, sorts by geometric reading order, then uses Claude tool-calling to assign `parent_id` relationships across the full flat block list |

### Self-Healing Loop (Pioneer Page)

Page 1 is special: it runs sequentially before the burst phase and its output is validated against the schema. If validation fails, the `retry_node` captures the exact `jsonschema.ValidationError` path and message and feeds it back to the model as a structured error prompt. This loop runs up to 3 times before the pipeline degrades gracefully — page 1's partial output is included as-is, a warning is appended to `extraction_warnings`, and the burst phase continues normally.

Pages 2–N are not subject to graph-level retries. They rely on `tenacity`'s `@retry` decorator at the API call site to handle transient 429/529 errors.

### Prompt Caching

Every page extraction call sends the PDF as a `document` block with `cache_control: {"type": "ephemeral"}`. The pioneer call establishes this block in Anthropic's prompt cache — caching Claude's fully-processed representation of the PDF (image + text per page). All subsequent burst calls hit the warm cache, achieving a >90% cache-hit rate on input tokens across multi-page documents.

> **Note:** Anthropic's prompt cache TTL is 5 minutes. Burst pages dispatched after this window pay full input token cost.

---

## Output Format

The final `hierarchical_document_tree` has this shape:

```json
{
  "document_type": "invoice",
  "pdf_hash": "a3f1c9...",
  "extraction_warnings": [],
  "structured_payload": [
    {
      "block_id": "p1-b1",
      "type": "title",
      "bbox": {
        "page_number": 1,
        "coordinates": [72, 50, 120, 540]
      },
      "text": "INVOICE #1042",
      "is_continued": false,
      "metadata": {},
      "parent_id": null
    },
    {
      "block_id": "p1-b2",
      "type": "table",
      "bbox": {
        "page_number": 1,
        "coordinates": [150, 50, 420, 540]
      },
      "text": "Item | Qty | Price",
      "is_continued": false,
      "metadata": {
        "table_data": {
          "total_rows": 3,
          "total_cols": 3,
          "cells": [
            {"r": 0, "c": 0, "rs": 1, "cs": 1, "value": "Item", "is_header": true},
            {"r": 0, "c": 1, "rs": 1, "cs": 1, "value": "Qty",  "is_header": true}
          ]
        }
      },
      "parent_id": "p1-b1"
    }
  ]
}
```

### Block Types

Every document normalizes to exactly 8 block types:

| Type | Description |
|---|---|
| `title` | Document or section title |
| `heading` | Sub-section heading |
| `paragraph` | Body text |
| `list_item` | Bulleted or numbered list entry |
| `table` | Tabular data (with normalized cell matrix in `metadata.table_data`) |
| `figure` | Image, chart, or diagram reference |
| `footnote` | Footer annotation |
| `margin_element` | Sidebar, callout, or margin note |

Domain-specific data (invoice line items, bibliographic authors, reference entries) lives inside the `metadata` field and does not break the 8-type contract.

### Table Cell Matrix

Tables are stored as a compressed coordinate matrix that handles row/column spans:

| Field | Type | Description |
|---|---|---|
| `r` | integer | Row index |
| `c` | integer | Column index |
| `rs` | integer | Row span |
| `cs` | integer | Column span |
| `value` | string | Cell text |
| `is_header` | boolean | Whether the cell is a header |

---

## Document Types & Schemas

Schemas live in `schemas/` as JSON Schema Draft-07 files. The `SchemaRegistry` loads them at runtime for both validation and Claude tool definition generation.

| File | Used for |
|---|---|
| `schemas/invoice.json` | Invoice documents — extends baseline with `metadata.table_data` |
| `schemas/scientific_paper.json` | Academic papers — adds `bibliographic`, `section`, `reference`, and `figure_table` metadata fields |
| `schemas/baseline_core.json` | Generic fallback for any unrecognized document type |

When the classifier returns an unknown document type, the registry silently falls back to `baseline_core.json`. The tool definition passed to Claude strips `$schema` and `title` fields, which are rejected by Anthropic's `input_schema` spec.

See **[schemas/README.md](schemas/README.md)** for a full guide on adding new document types.

---

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
git clone https://github.com/lucagattoni/PDFScout.git
cd PDFScout
uv sync
cp .env.example .env   # then fill in your API key
```

Edit `.env` and set your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is gitignored and never committed. `.env.example` documents the required variables.

---

## Observability

PDFScout ships with optional [Langfuse](https://langfuse.com/) tracing. When enabled, every pipeline run produces a single trace showing node execution, Claude API calls, token usage (including prompt-cache hits), and extraction metadata. All runs for the same PDF are grouped in the Langfuse Sessions view via a shared `session_id`.

To enable, add to your `.env`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Get keys from your [Langfuse project settings](https://cloud.langfuse.com). If the keys are absent the pipeline runs normally with no tracing.

---

## Usage

```bash
uv run main.py path/to/document.pdf
```

The output is printed as formatted JSON to stdout. Progress is logged per node:

```
Initializing extraction pipeline for: document.pdf (thread: a3f1c9d2...)
[GRAPH] Node 'native_extractor' completed.
[GRAPH] Node 'classifier' completed.
[GRAPH] Node 'pioneer_parser' completed.
[GRAPH] Node 'burst_dispatcher' completed.
[GRAPH] Node 'parser_worker' completed.
[GRAPH] Node 'hierarchy_node' completed.

Extraction complete. Output tree:
{ ... }
```

If the pioneer page failed validation after 3 retries, a warning is printed before the tree:

```
WARNINGS:
  ! Pioneer page (page 1) failed schema validation after 3 retries. Page 1 data may be incomplete or structurally invalid.
```

### Checkpoint Resumption

The thread ID is the PDF's SHA-256 hash. Re-running the same file resumes from the last valid checkpoint rather than restarting from scratch:

```bash
# First run — interrupted mid-way
uv run main.py large_document.pdf

# Second run — resumes automatically from last checkpoint
uv run main.py large_document.pdf
```

Checkpoint state is stored in `state_checkpoint.db` (SQLite, created automatically).

---

## Project Structure

```
PDFScout/
├── .python-version             # Pins Python 3.13
├── .env.example                # Required environment variables template
├── pyproject.toml              # uv-managed dependencies
├── uv.lock                     # Locked dependency graph
├── main.py                     # Entry point (loads .env via python-dotenv)
│
├── schemas/                    # JSON Schema Draft-07 blueprints
│   ├── baseline_core.json      # Generic fallback: 8-type enum, no domain metadata
│   ├── invoice.json            # Invoice-specific metadata extensions
│   └── scientific_paper.json   # Academic paper metadata additions
│
└── src/
    ├── config.py               # Centralized constants (MODEL, CONCURRENCY_LIMIT, etc.)
    ├── state.py                # PDFParserState TypedDict and merge reducers
    ├── schema_registry.py      # jsonschema loader, validator, and tool builder
    ├── edges.py                # pioneer_validation_route routing function
    ├── graph.py                # LangGraph graph, Send API dispatch, build_app() factory
    │
    ├── extractors/
    │   └── page_counter.py     # pypdf page count + encrypted PDF guard
    │
    ├── utils/
    │   └── pdf_utils.py        # Shared hash_file and encode_pdf_async helpers
    │
    └── nodes/                  # Graph node implementations
        ├── extractor_node.py   # PDF hashing + page count
        ├── classifier_node.py  # Document type classification with fallback
        ├── worker_node.py      # Page extraction (pioneer + burst, shared function)
        ├── retry_node.py       # Validation error capture + retry_count increment
        └── hierarchy_node.py   # Geometric pre-sorter + hierarchy assignment agent
```

---

## Configuration

All tunable constants live in `src/config.py`:

```python
MODEL = "claude-sonnet-4-6"
CONCURRENCY_LIMIT = 3       # Max concurrent Anthropic API calls during burst phase
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper"}
FALLBACK_DOC_TYPE = "baseline_core"
COLUMN_BUCKET_PX = 50       # Column grouping width (px) for geometric pre-sorter
```

`CONCURRENCY_LIMIT` controls the `asyncio.Semaphore` cap on parallel `parser_worker` calls. Increase it for faster processing on large documents; decrease it if hitting TPM rate limits. `COLUMN_BUCKET_PX` controls how the geometric pre-sorter groups blocks into columns before sorting by vertical position — increase it to merge narrow columns, decrease it to preserve fine-grained column boundaries.

---

## Extending with New Document Types

1. Add a new JSON Schema file to `schemas/` (e.g., `schemas/contract.json`) following the Draft-07 structure with the 8-type block enum and any domain-specific `metadata` extensions.
2. Add the new type string to `SUPPORTED_DOC_TYPES` in `src/config.py`.

The classifier, schema registry, and validation loop pick it up automatically — no other code changes required.

---

## Limitations

- **Encrypted PDFs:** Password-protected PDFs are not supported by Claude PDF Chat. `pypdf` detects encryption at startup and raises a `ValueError` before any API call is made.
- **Max request size:** The Anthropic API limit is 32 MB per request. PDFs approaching this size should use the Files API (upload once, reference by `file_id`) rather than per-call base64 encoding.
- **Max pages:** 600 pages per request (100 for 200k-context models). Very large documents should be split before processing.
- **Cache TTL:** Anthropic's prompt cache TTL is 5 minutes. Burst pages dispatched after this window pay full input token cost.
- **Hierarchy accuracy:** The hierarchy agent uses spatial heuristics and model judgment. Cross-page `is_continued` linkages and complex multi-column layouts may produce imperfect parent-child assignments.
