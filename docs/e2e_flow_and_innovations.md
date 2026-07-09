# E2E Extraction Flow & Innovative Features

_2026-07-09 18:10_

---

## End-to-End Pipeline

PDFScout is a LangGraph state machine with 6 nodes across two execution phases: sequential (pioneer page) followed by concurrent burst (remaining pages), joined by a map-reduce merge.

```text
START
  │
  ▼
native_extractor        ── pypdf page count + SHA-256 hash
  │
  ▼
classifier              ── Claude: returns document type token
  │
  ▼
pioneer_parser          ── Claude: page 1 extraction (primes prompt cache)
  │
  ├──► retry_node ──► pioneer_parser     ◄── validation retry loop (×3 max)
  │
  └──► burst_dispatcher
        │
        ├──► Send("parser_worker", page=2)   ──┐
        │     Send("parser_worker", page=3)     │ concurrent under Semaphore(3)
        │     ...                              │
        │     Send("parser_worker", page=N)   ──┘
        │         └──► merge_flat_blocks (reduce)
        │
        ├──► hierarchy_node ──► END  (single-page doc)
        └──► hierarchy_node ──► END  (multi-page doc)
```

### Node-by-Node

| Node | What it does |
|---|---|
| **native_extractor** | Hashes the PDF (chunked SHA-256, 64 KB), counts pages via `pypdf`, rejects encrypted/empty PDFs. Resets all pipeline state. |
| **classifier** | Sends the full PDF to Claude (vision, `cache_control: ephemeral`) with a single-token prompt. Returns one of `{invoice, scientific_paper, contract}` or falls back to `baseline_core`. |
| **pioneer_parser** | Extracts page 1 via forced Claude tool-calling. The PDF `document` block is marked with `cache_control: ephemeral` — this **warms Anthropic's prompt cache** so all subsequent pages pay reduced token cost. Appends doc-type-specific instructions (e.g., metadata subfields for scientific papers). |
| **retry_node** | Captures the precise `jsonschema.ValidationError` path and message, increments `retry_count`, resets the block buffer (`extracted_flat_blocks=None`), and feeds the error back to the model. |
| **burst_dispatcher** | For multi-page docs: emits `Send("parser_worker", page=N)` for each page 2–N via LangGraph's `Send` API (parallel fan-out). For single-page docs: routes directly to hierarchy. Emits a degradation warning if the pioneer exhausted its retries. |
| **parser_worker** | Runs pages 2–N concurrently under `asyncio.Semaphore(3)`. Each worker has an inline validation-retry loop (×3) with graceful degradation on exhaustion. |
| **hierarchy_node** | Deduplicates by `block_id`, geometrically pre-sorts by `(page, x_bucket, y)`, then sends a block manifest to Claude to assign `parent_id` relationships. Token budget scales dynamically (4k–16k based on block count). |

### Self-Healing Retry Loop

The pioneer page has a **graph-level** retry loop:

1. `pioneer_parser` runs page 1 extraction
2. `pioneer_validation_route` edge checks output against the document type's JSON Schema
3. On failure: routes to `retry_node` (if retries remain)
4. `retry_node` captures the exact error path and message, resets the buffer, increments count
5. Back to `pioneer_parser` — the prompt now includes the error text, instructing the LLM to fix the specific validation issue
6. After 3 failures: **degrades gracefully** — proceeds to the burst phase with a warning

Burst pages use **inline** retry with the same 3-attempt cap but no buffer reset, and degrade independently.

### Checkpointing & Resumption

State is persisted to SQLite after every node via LangGraph's `AsyncSqliteSaver`. The `thread_id` is the PDF's SHA-256 hash. If execution is interrupted:

- Re-running the same PDF checks `snapshot.next` — if non-empty (graph was mid-execution), it sends `None` to `graph.stream()` and **resumes from the last checkpoint**
- If `force=True`, it ignores the checkpoint and starts fresh
- Server restart marks in-flight API jobs as `failed`

---

## Innovative Features vs Traditional Document Parsers

### 1. Vision-Based Extraction (Not Text-Based)

Traditional parsers (pdfplumber, PyPDF2, Tika) extract text glyphs and positions from the PDF's internal content stream. They fail on:

- Scanned documents (no text layer)
- Multi-column layouts (glyph reordering produces garbage)
- Tables with merged cells or irregular spacing
- Watermarks and background interference (text layer is still there)

PDFScout sends the PDF as an image to Claude's native PDF vision API. The model "sees" the rendered page and extracts content with layout awareness — same pipeline for scanned documents and born-digital PDFs. No OCR pipeline, no heuristic re-ordering.

### 2. Self-Healing Validation Loop

Traditional parsers have no concept of correctness. If a table parser's regex doesn't match, it either returns empty or silently corrupts data.

PDFScout's pioneer page runs a closed feedback cycle:

```
LLM output → jsonschema validation → error path/message → prompt augmentation → LLM retry
```

The exact `ValidationError` (e.g., `"blocks[3].type: 'titel' is not one of ['title', 'heading', ...]"`) is fed back to the model as a structured prompt. This turns schema violations into a learning signal rather than a terminal failure. After 3 attempts, the pipeline degrades gracefully instead of aborting.

### 3. Document-Type-Aware Schemas

Traditional parsers need per-document-variant heuristics. PDFScout uses a **classifier → schema lookup → tool definition** pipeline:

1. Classifier identifies the document type (invoice, scientific paper, contract, or generic)
2. The corresponding JSON Schema is loaded at runtime
3. That schema becomes both the **validation contract** and the **Claude tool definition**

Adding a new document type is declarative — write a JSON Schema file, add the type string to a config set. The classifier prompt updates automatically (it enumerates `sorted(SUPPORTED_DOC_TYPES)`). No rule-engine changes, no layout heuristics, no regex patterns.

### 4. Map-Reduce Parallel Extraction with Prompt Caching

Most PDF extractors process pages sequentially. PDFScout exploits Anthropic's prompt cache:

- The **pioneer page** sends the PDF as a `document` block with `cache_control: {"type": "ephemeral"}` — this establishes Claude's cached representation of the PDF (image + text per page)
- All subsequent **burst pages** hit the warm cache at >90% cache-hit rate
- The pioneer's cost is amortized across N pages

Parallel fan-out uses LangGraph's `Send` API with an `asyncio.Semaphore(3)` cap, avoiding TPM rate-limit issues while maximizing throughput.

### 5. Checkpointed Resumption (Zero Custom Code)

Traditional parser pipelines need manual checkpointing (write intermediate files, track progress state). PDFScout gets resumption for free from the graph framework:

- LangGraph's `AsyncSqliteSaver` persists the full state after every node
- The thread ID is the PDF hash — deterministic, file-keyed checkpoint namespace
- `_resolve_input()` checks `snapshot.next` to decide fresh-start vs resume
- No custom resume logic, no manual state serialization

This is especially valuable for long-running extractions (the API background task, large multi-page documents) where network interruptions or server restarts would otherwise lose progress.

### 5. Geometry-Informed Hierarchy Agent

Traditional parsers use fixed reading-order heuristics: assume top-to-bottom, left-to-right within a single column. These break on:

- Two-column academic papers (text flows left-column then right-column)
- Brochures with sidebar callouts
- Financial sheets with nested tables and margin annotations

PDFScout's hierarchy node:

1. Sorts blocks deterministically by `(page_number, xmin // 50, ymin)` — the bucket width groups nearby columns
2. Sends the pre-sorted block manifest to Claude via tool-calling
3. Lets the model assign `parent_id` relationships with full spatial awareness
4. Scales token budget dynamically (4k to 16k based on block count)

The result is reading-order and hierarchy that adapts to the document's actual layout rather than hardcoded assumptions.

### 6. Unopinionated Output Format

Traditional parsers output page text, positional metadata, or format-specific structures (like PDFMiner's `LTTextBox`). Downstream consumers must reinvent reading-order logic and structural inference.

PDFScout normalizes every document to the same output shape:

```json
{
  "document_type": "invoice",
  "pdf_hash": "a3f1c9...",
  "extraction_warnings": [],
  "structured_payload": [
    {
      "block_id": "p1-b1",
      "type": "title",
      "bbox": {"page_number": 1, "coordinates": [72, 50, 120, 540]},
      "text": "INVOICE #1042",
      "extraction_flags": [],
      "parent_id": null
    }
  ]
}
```

All 8 core block types nest under `structured_payload`. Domain-specific data lives in `metadata`. Extraction flags signal uncertainty for downstream RAG pipelines. This uniformity means a single ingestion path can consume invoices, scientific papers, contracts, and arbitrary documents.