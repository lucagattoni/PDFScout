# Output Format

[Documentation index](../index.md) · [Project overview](https://github.com/lucagattoni/PDFScout)

## The shape, and the logic behind it

The pipeline's result is a single `hierarchical_document_tree`. Its payload is
deliberately a **flat list of blocks with `parent_id` references**, not a
nested tree: extraction workers run per page and in parallel, so no single
model call ever sees the whole document — blocks are emitted flat and the
hierarchy agent links them afterwards. A flat list is also what downstream
consumers (RAG chunkers, indexers) want: filter, group, or reassemble without
recursive traversal.

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
      "extraction_flags": [],
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

## Block Types

Every document normalizes to 8 base block types — the model must choose one,
which forces consistent downstream handling regardless of document domain.
Domain-specific schemas may extend this set.

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

Domain-specific data (invoice line items, bibliographic authors, contract
parties) lives inside the `metadata` field.

## Extraction Flags — uncertainty as data

Every block may carry an optional `extraction_flags` array naming specific
reasons why the extraction may be uncertain. Absent or empty means high
confidence. The logic: an extraction pipeline that can't say *"I'm not sure
about this one"* forces downstream consumers to either trust everything or
trust nothing.

| Flag | Meaning | Suggested RAG action |
|---|---|---|
| `partial_visibility` | Block is cut off at a page edge — text appears to continue beyond the visible area | Exclude or mark incomplete |
| `low_legibility` | Text is hard to read due to scan quality, low contrast, overlapping content, or background interference | Exclude or lower weight |
| `ambiguous_type` | Block type assignment is uncertain — content could reasonably be classified as two different types | Flag for review; rely on text content, not type |
| `possible_encoding_error` | Extracted text contains likely OCR or encoding artifacts — garbled characters, unusual punctuation, mixed scripts | Exclude or flag for re-extraction |

RAG pipelines can filter on flags:

```python
high_quality = [b for b in blocks if not b.get("extraction_flags")]
uncertain    = [b for b in blocks if b.get("extraction_flags")]
```

When `extraction_flags` is non-empty, `extraction_note` is also set — a
one-sentence description of the specific observable symptom on that block
(e.g. `"Top third of text is obscured by a watermark"`). It is intended for a
downstream remediation agent that can inspect flagged blocks and attempt
targeted correction. Absent when no flags are set. Maximum length is
controlled by `EXTRACTION_NOTE_MAX_LENGTH` in `src/config.py` (default 200).

## Table Cell Matrix

Tables are stored as a compressed coordinate matrix rather than nested arrays
because real tables have row and column spans — a merged header cell can't be
represented in a plain 2-D array without either duplicating values or losing
the span information:

| Field | Type | Description |
|---|---|---|
| `r` | integer | Row index |
| `c` | integer | Column index |
| `rs` | integer | Row span |
| `cs` | integer | Column span |
| `value` | string | Cell text |
| `is_header` | boolean | Whether the cell is a header |

## Document Types & Schemas

Schemas live in `schemas/` as JSON Schema Draft-07 files. The `SchemaRegistry`
loads them at runtime for **both** validation and Claude tool definition
generation — one source of truth, two consumers.

| File | Used for |
|---|---|
| `schemas/invoice.json` | Invoice documents — extends baseline with `metadata.table_data` |
| `schemas/scientific_paper.json` | Academic papers — adds `bibliographic`, `section`, `reference`, and `figure_table` metadata fields; the extraction prompt explicitly requests these subfields so they are actively populated on relevant blocks |
| `schemas/contract.json` | Legal contracts — adds `signature_block` block type and metadata subfields `contract_meta`, `party`, `clause`, and `signature` |
| `schemas/baseline_core.json` | Generic fallback for any unrecognized document type |

When the classifier returns an unknown document type, the registry silently
falls back to `baseline_core.json`.

**Validation — local, two-layer.** The extraction tool is **not** declared
`strict`. Strict tool use compiles the tool schema into a constrained-decoding
grammar with a complexity ceiling that the richest per-doc-type schemas
(`scientific_paper`, `contract`) exceed — and combined with streaming (required
to avoid the API's long-request timeout) the oversized grammar makes the
response **stall indefinitely** instead of erroring. So structural correctness
is enforced the robust way: every tool response is validated locally against
the **full** JSON Schema via `jsonschema`, and malformed output is re-prompted
through the validation-retry loop. The hierarchy tool (a tiny, fixed
`block_id`/`parent_id` schema, far under the ceiling) does keep `strict: true`
safely.

To add a new document type, see the [schema authoring guide](https://github.com/lucagattoni/PDFScout/blob/main/schemas/README.md)
and [development](../04-contributing/01-development.md#extending-with-new-document-types).
