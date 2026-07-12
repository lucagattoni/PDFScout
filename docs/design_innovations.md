# Design Innovations — PDFScout vs Traditional Parsers

_Created: 2026-07-09 18:10_\
_Updated: 2026-07-12 19:23 · deduplicated against README.md; scoped to design rationale only_

The **why** behind PDFScout's design choices, compared feature-by-feature against
traditional document parsers (pdfplumber, PyPDF2, Tika, PDFMiner).

For the **what** — pipeline diagram, node-by-node reference, output format, and
configuration — see the [README](../README.md#architecture). This document
deliberately repeats none of it.

---

## 1. Vision-Based Extraction (Not Text-Based)

Traditional parsers extract text glyphs and positions from the PDF's internal
content stream. They fail on:

- Scanned documents (no text layer)
- Multi-column layouts (glyph reordering produces garbage)
- Tables with merged cells or irregular spacing
- Watermarks and background interference (text layer is still there)

PDFScout sends the PDF as an image to Claude's native PDF vision API. The model
"sees" the rendered page and extracts content with layout awareness — same
pipeline for scanned documents and born-digital PDFs. No OCR pipeline, no
heuristic re-ordering.

## 2. Self-Healing Validation Loop

Traditional parsers have no concept of correctness. If a table parser's regex
doesn't match, it either returns empty or silently corrupts data.

PDFScout's pioneer page runs a closed feedback cycle
(mechanics in [README → Self-Healing Loop](../README.md#self-healing-loop-pioneer-page)):

```text
LLM output → jsonschema validation → error path/message → prompt augmentation → LLM retry
```

The exact `ValidationError` (e.g., `"blocks[3].type: 'titel' is not one of
['title', 'heading', ...]"`) is fed back to the model as a structured prompt.
This turns schema violations into a learning signal rather than a terminal
failure. After 3 attempts, the pipeline degrades gracefully instead of
aborting. Burst pages (2–N) run the same loop inline and degrade independently.

## 3. Document-Type-Aware Schemas

Traditional parsers need per-document-variant heuristics. PDFScout uses a
**classifier → schema lookup → tool definition** pipeline:

1. Classifier identifies the document type (invoice, scientific paper,
   contract, or a generic fallback)
2. The corresponding JSON Schema is loaded at runtime
3. That schema becomes both the **validation contract** and the **Claude tool
   definition**

Adding a new document type is declarative — write a JSON Schema file, add the
type string to a config set. The classifier prompt updates automatically (it
enumerates `sorted(SUPPORTED_DOC_TYPES)`). No rule-engine changes, no layout
heuristics, no regex patterns. Step-by-step guide in
[schemas/README.md](../schemas/README.md).

## 4. Map-Reduce Parallel Extraction with Prompt Caching

Most PDF extractors process pages sequentially. PDFScout exploits Anthropic's
prompt cache (details in [README → Prompt Caching](../README.md#prompt-caching)):

- The **pioneer page** sends the PDF as a `document` block with
  `cache_control: {"type": "ephemeral"}` — this establishes Claude's cached
  representation of the PDF (image + text per page)
- All subsequent **burst pages** hit the warm cache at >90% cache-hit rate
- The pioneer's cost is amortized across N pages

Parallel fan-out uses LangGraph's `Send` API with an `asyncio.Semaphore` cap
(`CONCURRENCY_LIMIT`), avoiding TPM rate-limit issues while maximizing
throughput.

## 5. Checkpointed Resumption (Zero Custom Code)

Traditional parser pipelines need manual checkpointing (write intermediate
files, track progress state). PDFScout gets resumption for free from the graph
framework:

- LangGraph's `AsyncSqliteSaver` persists the full state after every node
- The thread ID is the PDF hash — deterministic, file-keyed checkpoint
  namespace
- `_resolve_input()` checks `snapshot.next` — if non-empty (graph was
  mid-execution), it sends `None` to `graph.stream()` and resumes from the
  last checkpoint; `force=True` ignores the checkpoint and starts fresh
- No custom resume logic, no manual state serialization

This is especially valuable for long-running extractions (the API background
task, large multi-page documents) where network interruptions or server
restarts would otherwise lose progress.

## 6. Geometry-Informed Hierarchy Agent

Traditional parsers use fixed reading-order heuristics: assume top-to-bottom,
left-to-right within a single column. These break on:

- Two-column academic papers (text flows left-column then right-column)
- Brochures with sidebar callouts
- Financial sheets with nested tables and margin annotations

PDFScout's hierarchy node:

1. Sorts blocks deterministically by `(page_number, xmin // 50, ymin)` — the
   bucket width groups nearby columns
2. Sends the pre-sorted block manifest to Claude via tool-calling
3. Lets the model assign `parent_id` relationships with full spatial awareness
4. Scales token budget dynamically (4k to 16k based on block count)

The result is reading-order and hierarchy that adapts to the document's actual
layout rather than hardcoded assumptions.

## 7. Unopinionated Output Format

Traditional parsers output page text, positional metadata, or format-specific
structures (like PDFMiner's `LTTextBox`). Downstream consumers must reinvent
reading-order logic and structural inference.

PDFScout normalizes every document to the same output shape — the
`hierarchical_document_tree` documented in
[README → Output Format](../README.md#output-format). All core block types nest
under `structured_payload`; domain-specific data lives in `metadata`;
`extraction_flags` signal uncertainty for downstream RAG pipelines. This
uniformity means a single ingestion path can consume invoices, scientific
papers, contracts, and arbitrary documents.
