# Plan: Merge Classifier into Pioneer (Option B — Single Cache Miss)

_Created: 2026-06-08 11:30_
_Updated: 2026-06-08 12:15 · devil's advocate pass — three real bugs fixed in test update plan_

---

## Goal

Reduce API calls from **2 cache misses per document** (classifier + pioneer) to
**1 cache miss ever** (merged pioneer). All burst workers and all subsequent
pipeline runs hit the same cache entry.

---

## Background: Why Two Misses Today

Claude's KV-cache key is `hash(tools_tokens + message_tokens_up_to_breakpoint)`.
The `cache_control: {type: ephemeral}` marker on the PDF document block defines
the breakpoint.

| Call | Tool tokens | Cache key |
|------|-------------|-----------|
| `_classify()` | none | `hash(∅ + pdf_block)` |
| `window_parser_node()` (pioneer, invoice) | `extract_invoice_structure` | `hash(invoice_tool + pdf_block)` |
| `window_parser_node()` (burst, invoice) | `extract_invoice_structure` | same → **HIT** |

`classifier ≠ pioneer` cache key → separate miss. Burst workers already share
pioneer's entry because they use the same tool. The fix: collapse the two
separate calls into one, using a **single universal tool** that every call
(pioneer + all burst workers) shares identically.

---

## Approach

Replace the two-step `classifier → pioneer_parser` with a single
**`pioneer_classifier`** node that:

1. Sends the PDF with the universal tool.
2. Gets back both `document_type` and page-1 `blocks` in one tool-call response.
3. Populates `state["document_type"]` and `state["extracted_flat_blocks"]`.

Burst workers switch from per-type tools to the same universal tool → their
cache key matches the pioneer call → **cache hit on pages 2-N**.

Subsequent full pipeline runs (e.g. ground-truth generator run 2-5) also hit,
because the tool definition is identical.

Result: **1 miss (run-1 pioneer), 0 misses thereafter** for the same document
within the 5-minute ephemeral TTL.

---

## Key Insight: Tool Output Already Has `document_type`

All three existing schemas (`invoice.json`, `scientific_paper.json`,
`baseline_core.json`) already require a top-level `document_type` field in the
tool call output. The model already returns it. We only need:

- A universal schema whose `document_type` field accepts all three values
  (instead of an enum locked to one type).
- Pioneer to read `tool_block.input["document_type"]` instead of a separate
  `_classify()` call.

---

## Changes

### 1. `schemas/universal.json` (NEW)

Union of all three schemas. `document_type` is an enum of all supported values.
`metadata` includes all subfields from all three schema families.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "UniversalDocumentStructure",
  "type": "object",
  "properties": {
    "document_type": {
      "type": "string",
      "enum": ["invoice", "scientific_paper", "baseline_core"]
    },
    "blocks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "block_id": { "type": "string" },
          "type": {
            "type": "string",
            "enum": ["title", "heading", "paragraph", "list_item",
                     "table", "figure", "footnote", "margin_element"]
          },
          "bbox": {
            "type": "object",
            "properties": {
              "page_number": { "type": "integer" },
              "coordinates": {
                "type": "array",
                "items": { "type": "integer" },
                "minItems": 4, "maxItems": 4
              }
            },
            "required": ["page_number", "coordinates"]
          },
          "text": { "type": "string" },
          "is_continued": { "type": "boolean", "default": false },
          "metadata": {
            "type": "object",
            "properties": {
              "table_data": { "$ref": "#/$defs/table_data" },
              "bibliographic": { "$ref": "#/$defs/bibliographic" },
              "section": { "$ref": "#/$defs/section" },
              "reference": { "$ref": "#/$defs/reference" },
              "figure_table": { "$ref": "#/$defs/figure_table" }
            }
          }
        },
        "required": ["block_id", "type", "bbox", "text"]
      }
    }
  },
  "required": ["document_type", "blocks"],
  "$defs": {
    "table_data": { ... },       // copied from invoice.json
    "bibliographic": { ... },    // copied from scientific_paper.json
    "section": { ... },
    "reference": { ... },
    "figure_table": { ... }
  }
}
```

Token overhead vs current per-type schemas: universal ≈ scientific_paper size
(largest existing schema). Invoices and baseline_core calls pay a one-time
extra ~200-400 tokens for unused metadata defs. Acceptable given elimination
of a full cache-miss API call per run.

### 2. `src/schema_registry.py`

Add one method:

```python
def get_universal_schema_and_tool(self) -> tuple[dict, dict]:
    schema = self._load_schema("universal")
    tool_schema = {k: v for k, v in schema.items()
                   if k not in ("$schema", "title")}
    tool = {
        "name": "extract_document_structure",
        "description": "Classifies the document and outputs structured layout blocks.",
        "input_schema": tool_schema,
    }
    return schema, tool
```

Existing `get_schema_and_tool(doc_type)` is **kept unchanged** — still used by
`SchemaRegistry().validate()` in `pioneer_validation_route` and the real-doc
test suite.

### 3. `src/nodes/pioneer_node.py` (NEW, replaces `classifier_node.py`)

```python
async def pioneer_classifier_node(state: dict) -> dict:
    """Single API call: classify doc type + extract page-1 blocks.
    Universal tool ensures cache key identity with burst workers."""
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    pdf_base64 = await encode_pdf_async(state["file_path"])
    _, tool_definition = SchemaRegistry().get_universal_schema_and_tool()

    content = [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": pdf_base64},
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                "Classify this document and extract ALL structural blocks on "
                "physical page 1 only.\n"
                "Set `document_type` to exactly one of: "
                "invoice, scientific_paper, baseline_core.\n"
                "Coordinates must follow [ymin, xmin, ymax, xmax] order.\n"
                "If a block is cut off at the bottom of page 1, set "
                "is_continued=true.\n"
                "For scientific_paper: populate bibliographic (authors, title, "
                "abstract, doi), section, reference, and figure_table metadata "
                "where present.\n"
                "For invoice: populate table_data metadata for table blocks."
            ),
        },
    ]

    if state.get("last_validation_error"):
        content.append({
            "type": "text",
            "text": (
                f"PREVIOUS VALIDATION ERROR:\n{state['last_validation_error']}\n"
                "Fix the schema alignment issue in your response."
            ),
        })

    response = await _call_api(client,
                               [{"role": "user", "content": content}],
                               tool_definition)
    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise ValueError("pioneer_classifier: API returned no tool_use block.")

    doc_type = tool_block.input.get("document_type", "").strip().lower()
    all_types = SUPPORTED_DOC_TYPES | {FALLBACK_DOC_TYPE}
    if doc_type not in all_types:
        doc_type = FALLBACK_DOC_TYPE

    blocks = tool_block.input.get("blocks", [])
    if isinstance(blocks, str):
        try:
            blocks = json.loads(blocks)
        except (json.JSONDecodeError, ValueError):
            blocks = []
    if not isinstance(blocks, list):
        blocks = []

    schema, _ = SchemaRegistry().get_schema_and_tool(doc_type)
    return {
        "document_type": doc_type,
        "target_json_schema": schema,
        "extracted_flat_blocks": blocks,
    }
```

`_call_api` is the same `@retry` wrapper from `worker_node.py` (extracted to a
shared utility, or duplicated — see Step 4).

### 4. `src/nodes/worker_node.py`

**Single change**: replace the per-type tool lookup with the universal tool.

Before:
```python
_, tool_definition = SchemaRegistry().get_schema_and_tool(state["document_type"])
```

After:
```python
_, tool_definition = SchemaRegistry().get_universal_schema_and_tool()
```

Doc-type-specific instructions remain useful: burst workers still know
`state["document_type"]` (set by pioneer). Keep `_doc_type_instructions()` and
pass doc_type as before — it only affects the **text** portion of the message,
which is AFTER the cache breakpoint and therefore not part of the cache key.

### 5. `src/graph.py`

```python
# Remove:
from src.nodes.classifier_node import classifier_node

# Add:
from src.nodes.pioneer_node import pioneer_classifier_node

# In build_app():
# Remove:
workflow.add_node("classifier", classifier_node)
workflow.add_edge("native_extractor", "classifier")
workflow.add_edge("classifier", "pioneer_parser")

# Replace pioneer_parser with pioneer_classifier:
workflow.add_node("pioneer_parser", pioneer_classifier_node)
workflow.add_edge("native_extractor", "pioneer_parser")
```

All downstream edges (`pioneer_parser → retry_node / burst_dispatcher`) are
unchanged.

### 6. `src/nodes/classifier_node.py`

**Delete** the file. All its logic moves to `pioneer_node.py`.

### 7. Tests

| File | Action |
|------|--------|
| `tests/unit/nodes/test_classifier_node.py` | **Delete** — node is gone |
| `tests/unit/nodes/test_worker_node.py` | Replace `get_schema_and_tool` mock with `get_universal_schema_and_tool` |
| `tests/unit/test_graph.py` | Line 56: remove `"classifier"` from expected set. Do **not** add `"pioneer_classifier"` — the graph reuses the node name `"pioneer_parser"`, which stays in the set. |
| `tests/integration/test_graph_pipeline.py` | **Full rewrite of all three test classes** (see below) |
| `tests/integration/test_synthetic_grp_b.py` | Remove `src.nodes.worker_node._call_api` patch from `_run_b_test`; pioneer now makes a real API call (e2e intent preserved); hierarchy mock stays |
| `tests/fixtures/generators/grp_b_classifier.py` | No change — PDFs unchanged |

#### `test_graph_pipeline.py` rewrite (critical detail)

Currently all three test classes patch `src.nodes.classifier_node.encode_pdf_async` and
`src.nodes.classifier_node.AsyncAnthropic`, which will cause `ModuleNotFoundError` once
`classifier_node.py` is deleted.

After Option B, the merged pioneer lives in `src.nodes.pioneer_node`. Required changes:

1. Add a helper at the top of the file alongside the existing `_make_tool_use_response`:

   ```python
   def _make_pioneer_response(doc_type: str, blocks: list):
       """Returns a tool_use response with both document_type and blocks."""
       tool_block = MagicMock()
       tool_block.type = "tool_use"
       tool_block.input = {"document_type": doc_type, "blocks": blocks}
       response = MagicMock()
       response.content = [tool_block]
       return response
   ```

2. In each test class, replace:
   - `mocker.patch("src.nodes.classifier_node.encode_pdf_async", ...)` →
     `mocker.patch("src.nodes.pioneer_node.encode_pdf_async", ...)`
   - `mocker.patch("src.nodes.classifier_node.AsyncAnthropic")` / classifier text-response mock →
     `mocker.patch("src.nodes.pioneer_node.AsyncAnthropic")` with pioneer client returning
     `_make_pioneer_response("baseline_core", [_valid_block(1)])` for pioneer calls
   - Keep `mocker.patch("src.nodes.worker_node.encode_pdf_async", ...)` for burst workers
   - Keep `mocker.patch("src.nodes.worker_node.AsyncAnthropic")` for burst workers

3. For `TestGraphPipelineRetry`, the side_effect list currently has 3 responses
   (invalid pioneer, valid pioneer retry, page-2 burst). After the merge, this becomes:
   - `pioneer_node.AsyncAnthropic` mock: 2 responses (invalid `_make_pioneer_response`,
     valid `_make_pioneer_response`)
   - `worker_node.AsyncAnthropic` mock: 1 response (page-2 burst)

4. For `TestGraphPipelineMaxRetryDegradation`, pioneer mock returns invalid blocks 4× (side_effect
   with 4 entries) and `worker_node` mock is unused (single-page, no burst).

New test file: `tests/unit/nodes/test_pioneer_node.py`

- `test_invoice_classified_and_blocks_extracted` — assert `result["document_type"] == "invoice"`,
  `result["extracted_flat_blocks"]` is a list, and
  `result["target_json_schema"] == SchemaRegistry()._load_schema("invoice")` (per-type, not universal)
- `test_scientific_paper_classified_and_blocks_extracted`
- `test_unknown_type_falls_back_to_baseline_core`
- `test_validation_error_appended_on_retry` — 3-item content list on second call
- `test_blocks_json_string_coerced_to_list` — tool returns blocks as JSON string; assert list result

### 8. Version & Changelog

Minor version bump: `1.4.1 → 1.5.0` (breaking internal node API; drops
classifier node).

---

## Failure Modes & Devil's Advocate

### A. Schema token overhead increases cost per burst worker call

Universal schema ≈ scientific_paper schema size (largest). Burst workers now
pay for unused metadata definitions on every call. However:
- Token overhead is small relative to the document itself (PDFs are large).
- The cache HIT savings from eliminating separate classifier calls far outweigh it.
- On a 5-page invoice: old cost = 1 classifier miss + 1 pioneer miss + 3 burst
  hits; new cost = 1 merged miss + 4 burst hits. Net saving ≈ 1 full cache-miss
  API call per document.

### B. Universal tool may degrade extraction quality on typed documents

With a type-specific tool the model implicitly knows (from the schema) which
metadata fields apply. With the universal schema, all metadata fields exist for
all doc types. Risk: model populates `bibliographic` fields for an invoice.

Mitigations:
- Explicit prompt instruction: "For invoice: populate table_data. For
  scientific_paper: populate bibliographic/section/reference/figure_table."
- `SchemaRegistry().validate()` in `pioneer_validation_route` still validates
  against the per-type schema → any schema violation triggers retry.
- `baseline_core` metadata schema is already open (`"type": "object"`) so there
  is no regression there.

### C. Classification from tool output is weaker than dedicated classifier call

The classifier currently makes a focused call: max_tokens=10, single task. The
merged call is max_tokens=4000, dual task (classify + extract). Risk: model
occasionally misclassifies when distracted by extraction.

Counter-argument: providing the FULL page-1 content to extract gives MORE
context for classification than the dedicated classifier, which also sees the
full document. The dual-task prompt is explicit about requiring a classification.
If misclassification occurs, the validation loop catches it (wrong metadata
schema → retry with error message → self-correction).

If empirical testing shows classification instability, mitigation is to add a
brief prefix instruction: "Step 1: determine document type from the header,
layout, and content. Step 2: extract page-1 blocks."

### D. `last_validation_error` injection on retry conflates classification + extraction errors

Currently `pioneer_validation_route` validates blocks against the per-type
schema. If the schema says `document_type` must be `"invoice"` but model
returned `"scientific_paper"`, the validation error message will mention
`document_type` mismatch. The retry prompt injects this error verbatim, which
should guide the model to correct both classification and extraction.

No special handling needed — the existing retry mechanism already works.

### E. `target_json_schema` field in state becomes a zombie for burst workers

`target_json_schema` is populated by `pioneer_classifier_node` (same as
before) using `SchemaRegistry().get_schema_and_tool(doc_type)` — the **per-type**
schema (e.g. `invoice.json`), not the universal schema. It is stored in state
but no node downstream reads it directly.

This must be explicitly tested: `test_pioneer_node.py::test_invoice_classified_and_blocks_extracted`
must assert `result["target_json_schema"] == SchemaRegistry()._load_schema("invoice")`.
Without this assertion, an implementor could silently store the universal schema and
nobody would notice until an API consumer compared schema outputs.

No change to `state.py` required.

### F. Cache TTL: 5-minute ephemeral window may not cover all burst workers on very long documents

For a 100-page document, burst workers for pages 2-100 are dispatched
concurrently but bounded by `CONCURRENCY_LIMIT=3`. If the full burst takes
>5 min, late-processed pages miss the cache. This is a pre-existing limitation
unrelated to Option B. Option B does not make it worse — in fact it improves
the window by starting the cache clock earlier (merged pioneer instead of
separate classifier + pioneer).

### G. Shared `_call_api` helper: code duplication between pioneer_node and worker_node

Both nodes need an identical `@retry` wrapper around `client.messages.create`.
Options:
1. Duplicate (current approach in `classifier_node.py` and `worker_node.py`).
2. Extract to `src/utils/api_utils.py`.

**Decision**: Duplicate into `pioneer_node.py`. Option B already changes two
files; introducing a third shared utility adds scope. If a third node later
needs it, extract then. (Rule: three uses before abstraction.)

---

## Implementation Steps (in order)

```
1. Create schemas/universal.json              → verify: loads via SchemaRegistry
2. Add get_universal_schema_and_tool()        → verify: unit test in test_schema_registry.py
3. Create src/nodes/pioneer_node.py           → verify: test_pioneer_node.py (mocked)
4. Update src/nodes/worker_node.py            → verify: test_worker_node.py passes
5. Update src/graph.py                        → verify: test_graph.py passes
6. Delete src/nodes/classifier_node.py        → verify: no import errors
7. Update affected tests                      → verify: full test suite passes
8. Bump version to 1.5.0, update CHANGELOG
9. Commit and push to plan/synthetic-pdf-test-fixtures-jOV4i
```

---

## Acceptance Criteria

- [ ] `uv run pytest tests/unit/ -q` passes with zero failures
- [ ] `uv run pytest tests/integration/test_graph_pipeline.py -q` passes
- [ ] `uv run pytest tests/integration/test_synthetic_grp_b.py -q` passes (classification via pioneer)
- [ ] Manual spot-check: `uv run scripts/generate_real_ground_truth.py --slot inv-1 --runs 2 --dry-run` prints expected output with no import errors
- [ ] No reference to `classifier_node` anywhere in `src/`
- [ ] Cache proof: pioneer call and burst worker call both use `extract_document_structure` tool
