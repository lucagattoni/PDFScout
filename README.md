# PDFScout · [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md)

An agnostic, multi-agent PDF structure extractor that converts any PDF document into a validated, hierarchical JSON tree. Built on LangGraph with Claude's native PDF vision API, prompt caching for cost efficiency, and a self-healing validation loop. Works on text-based and scanned documents alike.

---

## The Problem

Traditional PDF parsers break on structurally complex documents — multi-column academic papers, corporate brochures, dense financial sheets. Regex and heuristic approaches are brittle: they hardcode assumptions about layout that collapse the moment a document deviates from the expected template.

PDFScout shifts the parsing burden to a language model. It treats every document as a collection of generic spatial structures, lets Claude extract and classify them, and enforces schema correctness through a closed-loop validation protocol.

---

## What It Does

Given a PDF file, PDFScout:

1. Counts pages and validates the file is not encrypted using `pypdf` (lightweight, zero-dependency)
2. Classifies the document type (invoice, scientific paper, contract, or a generic fallback) by sending the full PDF to Claude via the native PDF Chat API
3. Extracts structured content from every page in parallel via Claude tool-calling, with the PDF document block cached at the provider to minimize token costs — this works on scanned PDFs, complex multi-column layouts, and any document pdfplumber-style text extraction would fail on
4. Validates page 1's output against a JSON Schema blueprint and retries up to 3 times if the model produces malformed data
5. Assigns parent-child relationships across all extracted blocks using a geometry-informed hierarchy agent
6. Outputs a validated, hierarchical JSON document tree

State is persisted to SQLite after every node. If execution is interrupted, re-running the same PDF resumes from the last valid checkpoint.

---

## Architecture

The pipeline is a LangGraph state machine with two distinct execution phases — sequential for the pioneer page, concurrent for all remaining pages — joined by a map-reduce merge.

```text
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
| `pioneer_parser` | Sends page 1 as a `document` block to Claude via tool-calling; marks the document block with `cache_control: ephemeral` to establish the provider's prompt cache for all subsequent burst calls; appends doc-type-specific supplemental instructions (e.g. requests optional metadata subfields for `scientific_paper`) |
| `retry_node` | Re-runs `jsonschema` validation to capture the specific error, increments `retry_count`, and writes the error detail to state for the model's next attempt |
| `burst_dispatcher` | Emits one `Send("parser_worker", ...)` per remaining page using LangGraph's Send API; writes a degradation warning to state if pioneer validation exhausted its retries |
| `parser_worker` | Extracts pages 2–N concurrently under an `asyncio.Semaphore`; includes an inline validation-retry loop (up to 3 attempts) mirroring the pioneer's graph-level retry; degrades gracefully with a warning after 3 failed attempts |
| `hierarchy_node` | Deduplicates blocks by `block_id`, sorts by geometric reading order, then uses Claude tool-calling to assign `parent_id` relationships across the full flat block list |

### Self-Healing Loop (Pioneer Page)

Page 1 is special: it runs sequentially before the burst phase and its output is validated against the schema. If validation fails, the `retry_node` captures the exact `jsonschema.ValidationError` path and message and feeds it back to the model as a structured error prompt. This loop runs up to 3 times before the pipeline degrades gracefully — page 1's partial output is included as-is, a warning is appended to `extraction_warnings`, and the burst phase continues normally.

Pages 2–N use `burst_worker_node`, which retries inline up to 3 times on schema validation failure before degrading gracefully. Transient HTTP errors (429/529) are handled separately by `tenacity`'s `@retry` decorator at the API call site.

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

Every document normalizes to 8 base block types. Domain-specific schemas may extend this with additional types.

| Type | Description | Schemas |
|---|---|---|
| `title` | Document or section title | all |
| `heading` | Sub-section heading | all |
| `paragraph` | Body text | all |
| `list_item` | Bulleted or numbered list entry | all |
| `table` | Tabular data (with normalized cell matrix in `metadata.table_data`) | all |
| `figure` | Image, chart, or diagram reference | all |
| `footnote` | Footer annotation | all |
| `margin_element` | Sidebar, callout, or margin note | all |
| `signature_block` | Signature area with signatory name, role, and date lines | `contract` only |

Domain-specific data (invoice line items, bibliographic authors, contract parties) lives inside the `metadata` field.

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
| `schemas/scientific_paper.json` | Academic papers — adds `bibliographic`, `section`, `reference`, and `figure_table` metadata fields; the extraction prompt explicitly requests these subfields so they are actively populated on relevant blocks |
| `schemas/contract.json` | Legal contracts — adds `signature_block` block type and metadata subfields `contract_meta`, `party`, `clause`, and `signature`; the extraction prompt instructs the model to populate each subfield on the relevant block types |
| `schemas/baseline_core.json` | Generic fallback for any unrecognized document type |

When the classifier returns an unknown document type, the registry silently falls back to `baseline_core.json`. The tool definition passed to Claude strips `$schema` and `title` fields, which are rejected by Anthropic's `input_schema` spec.

See **[schemas/README.md](schemas/README.md)** for a full guide on adding new document types.

---

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
git clone https://github.com/lucagattoni/PDFScout.git
cd PDFScout
uv sync --group dev   # installs production deps + ruff, pytest, and other dev tools
cp .env.example .env  # then fill in your API key
```

---

## Development

| Command | Description |
|---|---|
| `make install` | Install all dependencies (production + dev, including Node) |
| `make lint` | Check Python for linting violations and formatting drift (read-only) |
| `make lint-md` | Check Markdown files with markdownlint-cli2 (read-only) |
| `make fix` | Auto-fix Python violations and reformat all files |
| `make test` | Run the full test suite (113 tests, no API key required) |
| `make test-e2e` | Run all synthetic e2e tests (requires `ANTHROPIC_API_KEY`) |
| `make test-e2e GRP=c` | Run one group of e2e tests (a–h) |
| `make fixtures` | Regenerate all synthetic PDF fixtures and golden files |
| `make fixtures GRP=c` | Regenerate one group of fixtures |
| `make coverage` | Run tests and print per-module coverage report |
| `make ci` | Run `lint`, `lint-md`, then `test` — use before pushing |
| `make clean` | Remove `__pycache__`, `.coverage`, `htmlcov`, `.pytest_cache`, `node_modules` |

Python linting and formatting use [ruff](https://github.com/astral-sh/ruff) (configured in `pyproject.toml` under `[tool.ruff]`). Markdown linting uses [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2) (configured in `.markdownlint.json`).

---

## Testing

The suite has 120 tests across two layers (run with `make test`, coverage with `make coverage`):

| Layer | Location | What it covers |
|---|---|---|
| Unit | `tests/unit/` | State reducers, schema registry, routing edges, PDF utilities, page counter, tracing, Pydantic models, graph topology, and all five node functions — all external I/O mocked |
| Integration | `tests/integration/` | All FastAPI endpoints (health, extract, jobs) via an ASGI test client; `run_extraction` background task; end-to-end LangGraph pipeline (happy path, pioneer retry-then-success, max-retry degradation) |

No `ANTHROPIC_API_KEY` is required — the suite runs entirely in isolation with mocked Anthropic clients.

### Synthetic e2e tests

A separate tier of tests exercises the real pipeline against synthetic PDF fixtures. These require a real `ANTHROPIC_API_KEY` and are excluded from `make test` (they carry `@pytest.mark.e2e`).

| Group | Concern | API calls |
|---|---|---|
| A | Native extraction (pypdf only) | 0 |
| B | Classifier accuracy | 1 per test |
| C | Block-type extraction | 1–2 per test |
| D | Schema-specific metadata | 1–2 per test |
| E | Multi-page burst + merge (hierarchy mocked) | N (one per page) |
| F | Hierarchy assignment (narrow, direct function call) | 1 per test |
| G | Two- and three-column reading order | 1–2 |
| H | Graceful degradation (blank page, tiny text) | 1 |
| I | Full-chain integration (no LLM tier mocked except classifier) | N + 1 |

```bash
# Run all e2e tests
make test-e2e

# Run one group
make test-e2e GRP=c

# Regenerate fixtures after a generator or prompt change
make fixtures
make fixtures GRP=b
```

PDF fixtures are not committed — they are generated at session start by a hash-check that compares each generator script's SHA-256 against `tests/fixtures/manifest.json`. Golden files (expected outputs, design-intent) are committed to `tests/fixtures/golden/`.

### Real-document corpus tests (Group R)

A third tier runs the full pipeline against real PDFs sourced from public repositories and
government/institutional open-access publications. Unlike Groups A–I (which use synthetic
PDFs), Group R tests the pipeline against documents it will encounter in production.

```bash
# Download PDFs (first time, or when URLs change)
python scripts/download_real_fixtures.py

# Run Group R tests (requires ANTHROPIC_API_KEY)
pytest tests/integration/test_real_docs.py -m grp_r
```

Real PDFs are never committed — they land in `tests/fixtures/pdfs/real/` (gitignored) and
are fetched on demand by `download_real_fixtures.py`. Golden assertion files are committed
to `tests/fixtures/real_golden/`. The corpus manifest (`tests/fixtures/real_manifest.json`)
records URLs, checksums, and licenses for all 15 slots.

**Managing the corpus** (adding slots, updating golden files, replacing stale URLs) — see
[`docs/real_doc_workflow.md`](docs/real_doc_workflow.md).

**Coverage targets:**

| Module | Coverage |
|---|---|
| `src/state.py`, `src/edges.py`, `src/schema_registry.py` | 100% |
| `src/utils/`, `src/extractors/`, `src/api/jobs.py`, `src/api/models.py` | 100% |
| `src/graph.py`, `src/nodes/*.py` | 100% |
| `src/api/runner.py` | ≥ 90% |
| `api.py` | ≥ 75% (lifespan I/O not exercised) |

Edit `.env` and set your Anthropic API key:

```text
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is gitignored and never committed. `.env.example` documents the required variables.

---

## Observability

PDFScout ships with optional [Langfuse](https://langfuse.com/) tracing. When enabled, every pipeline run produces a single trace showing node execution, Claude API calls, token usage (including prompt-cache hits), and extraction metadata. All runs for the same PDF are grouped in the Langfuse Sessions view via a shared `session_id`.

To enable, add to your `.env`:

```text
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Get keys from your [Langfuse project settings](https://cloud.langfuse.com). If the keys are absent the pipeline runs normally with no tracing.

---

## Usage

### CLI

```bash
uv run main.py path/to/document.pdf
```

The output is printed as formatted JSON to stdout. Progress is logged per node:

```text
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

```text
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

### API Server

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000
```

See **[API_README.md](API_README.md)** for the full endpoint reference, job
lifecycle, and operational notes.

---

## Project Structure

```text
PDFScout/
├── .python-version             # Pins Python 3.13
├── .env.example                # Required environment variables template
├── Makefile                    # Developer shortcuts: install, lint, fix, test, coverage, ci, clean
├── pyproject.toml              # uv-managed dependencies + ruff and pytest configuration
├── uv.lock                     # Locked dependency graph
├── main.py                     # Entry point (loads .env via python-dotenv)
│
├── schemas/                    # JSON Schema Draft-07 blueprints
│   ├── baseline_core.json      # Generic fallback: 8-type enum, no domain metadata
│   ├── contract.json           # Contract-specific: signature_block type + party/clause/signature metadata
│   ├── invoice.json            # Invoice-specific metadata extensions
│   └── scientific_paper.json   # Academic paper metadata additions
│
├── tests/
│   ├── conftest.py             # Shared fixtures (env setup, mock graph, ASGI client, PDF helpers)
│   ├── unit/
│   │   ├── test_state.py       # merge_flat_blocks / merge_warnings reducers
│   │   ├── test_schema_registry.py
│   │   ├── test_edges.py       # pioneer_validation_route all branches
│   │   ├── test_pdf_utils.py   # hash_file, encode_pdf_async
│   │   ├── test_page_counter.py
│   │   ├── test_tracing.py     # tracing_span (langfuse=None + active paths)
│   │   ├── test_models.py      # JobResponse.from_record, HealthResponse
│   │   ├── test_graph.py       # burst_dispatcher_node, dispatch_pages, build_app topology
│   │   └── nodes/
│   │       ├── test_extractor_node.py
│   │       ├── test_classifier_node.py
│   │       ├── test_worker_node.py
│   │       ├── test_retry_node.py
│   │       └── test_hierarchy_node.py
│   └── integration/
│       ├── test_api_health.py  # GET / redirect, GET /health
│       ├── test_api_extract.py # POST /extract (idempotency, force, size limit, conflict)
│       ├── test_api_jobs.py    # GET /jobs/{id}, DELETE /jobs/{id}
│       ├── test_api_runner.py  # _resolve_input branches, run_extraction happy/fail paths
│       └── test_graph_pipeline.py  # End-to-end graph (happy path, retry, max-retry degradation)
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
        ├── worker_node.py      # window_parser_node (pioneer) + burst_worker_node (pages 2-N, inline retry)
        ├── retry_node.py       # Validation error capture + retry_count increment
        └── hierarchy_node.py   # Geometric pre-sorter + hierarchy assignment agent
```

---

## Configuration

All tunable constants live in `src/config.py`:

```python
MODEL = "claude-sonnet-4-6"
CONCURRENCY_LIMIT = 3       # Max concurrent Anthropic API calls during burst phase
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper", "contract"}
FALLBACK_DOC_TYPE = "baseline_core"
COLUMN_BUCKET_PX = 50       # Column grouping width (px) for geometric pre-sorter
```

`CONCURRENCY_LIMIT` controls the `asyncio.Semaphore` cap on parallel `parser_worker` calls. Increase it for faster processing on large documents; decrease it if hitting TPM rate limits. `COLUMN_BUCKET_PX` controls how the geometric pre-sorter groups blocks into columns before sorting by vertical position — increase it to merge narrow columns, decrease it to preserve fine-grained column boundaries.

---

## Extending with New Document Types

1. Add a new JSON Schema file to `schemas/<type>.json` following the Draft-07 structure with the 8-type block enum and any domain-specific `metadata` extensions. The filename without `.json` is the exact token the classifier will return.
2. Add the new type string to `SUPPORTED_DOC_TYPES` in `src/config.py` — the classifier prompt updates automatically via `sorted(SUPPORTED_DOC_TYPES)`.
3. *(Optional but recommended)* Add a branch in `_doc_type_instructions()` in `src/nodes/worker_node.py` with domain-specific extraction instructions. These are appended to the prompt for every page, guiding the model to populate domain metadata subfields on the relevant block types.

The classifier, schema registry, and validation loop pick it up after steps 1–2. Step 3 improves metadata extraction quality but is not required for the pipeline to function.

See **[schemas/README.md](schemas/README.md)** for the full guide.

---

## Limitations

- **Encrypted PDFs:** Password-protected PDFs are not supported by Claude PDF Chat. `pypdf` detects encryption at startup and raises a `ValueError` before any API call is made.
- **Max request size:** The Anthropic API limit is 32 MB per request. PDFs approaching this size should use the Files API (upload once, reference by `file_id`) rather than per-call base64 encoding.
- **Max pages:** 600 pages per request (100 for 200k-context models). Very large documents should be split before processing.
- **Cache TTL:** Anthropic's prompt cache TTL is 5 minutes. Burst pages dispatched after this window pay full input token cost.
- **Hierarchy accuracy:** The hierarchy agent uses spatial heuristics and model judgment. Cross-page `is_continued` linkages and complex multi-column layouts may produce imperfect parent-child assignments.
