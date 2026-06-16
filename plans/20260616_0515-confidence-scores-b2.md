# B2 — Extraction Quality Flags on Blocks

_Created: 2026-06-16 05:15_
_Updated: 2026-06-16 05:25 · Replaced scalar confidence with structured flags after design review_
_Updated: 2026-06-16 05:45 · Fixed 4 bugs found in devil's advocate review: uniqueItems, _base_block helper, sample_block fixture arg, invocation count_

## Overview

Add an optional `extraction_flags` array to every extracted block. Each flag names a
specific reason why the extraction may be uncertain — giving RAG pipelines actionable
signals they can filter or route on, rather than an opaque scalar they can't interpret.

**Design decision:** A self-reported `confidence: 0.7` is unreliable (LLMs are
miscalibrated, hard to validate, not testable without ground truth). A defined enum
of named flags forces the model to commit to a specific reason, is schema-validatable,
and lets downstream consumers act on type rather than threshold. Empty array = high
confidence extraction.

**Primary use case:** RAG pipeline filtering. A consumer can do:
```python
high_quality = [b for b in blocks if not b.get("extraction_flags")]
uncertain = [b for b in blocks if b.get("extraction_flags")]
```
Or route uncertain blocks to human review while indexing the rest.

---

## 1. Flag Enum

Four flags, chosen for LLM reliability and RAG actionability:

| Flag | When to set | RAG action |
|------|-------------|------------|
| `"partial_visibility"` | Block is cut off at a page edge — text appears to continue beyond the visible area, or coordinates are flush against the page boundary | Exclude or mark incomplete |
| `"low_legibility"` | Text is hard to read due to scan quality, low contrast, overlapping content, or background interference | Exclude or lower weight |
| `"ambiguous_type"` | Block type assignment is uncertain — the content could reasonably be classified as two different types (e.g., a short paragraph vs. a heading, or a figure caption vs. a footnote) | Flag for review; use text content, not type |
| `"possible_encoding_error"` | Extracted text contains likely OCR or encoding artifacts — garbled character sequences, unusual punctuation patterns, mixed scripts that don't match surrounding context | Exclude or flag for re-extraction |

---

## 2. Schema Changes

All four schema files receive the same addition to the block item properties:

```json
"extraction_flags": {
  "type": "array",
  "uniqueItems": true,
  "items": {
    "type": "string",
    "enum": [
      "partial_visibility",
      "low_legibility",
      "ambiguous_type",
      "possible_encoding_error"
    ]
  },
  "description": "Set when extraction quality is uncertain. Omit (or use []) for high-confidence blocks. Flags: 'partial_visibility' — block cut off at page edge; 'low_legibility' — text hard to read due to scan/contrast/overlap; 'ambiguous_type' — block type classification uncertain; 'possible_encoding_error' — text contains likely OCR or encoding artifacts."
}
```

`extraction_flags` is **not** added to `required` — the model omits it on
unambiguously clean blocks, keeping the response compact.

`"uniqueItems": true` prevents the model from emitting duplicate flags (e.g.
`["ambiguous_type", "ambiguous_type"]`), which would otherwise pass validation silently.

**Files:** `schemas/baseline_core.json`, `schemas/invoice.json`,
`schemas/scientific_paper.json`, `schemas/contract.json`.

---

## 3. Extraction Prompt: `src/nodes/worker_node.py`

Add a module-level constant (never duplicated) and append to the shared
text content block in **both** `window_parser_node` and `burst_worker_node`.

**Exact splice point:** Concatenate `_EXTRACTION_FLAGS_INSTRUCTION` directly after
`{extra_instructions}` in the existing f-string (lines 95 and 162 of `worker_node.py`).
The constant starts with a space, so the result for `baseline_core` reads
`"the schema parameters. Set extraction_flags..."` and for doc-types with
`extra_instructions` it reads `"...doc-type-specific text. Set extraction_flags..."`.
Do **not** add a separate content item — stay within the existing text block.

```python
_EXTRACTION_FLAGS_INSTRUCTION = (
    " Set extraction_flags on a block only when quality is uncertain: "
    "'partial_visibility' if the block is cut off at the page edge; "
    "'low_legibility' if text is hard to read (scan, low contrast, overlapping content); "
    "'ambiguous_type' if you are uncertain which block type is most appropriate; "
    "'possible_encoding_error' if the text contains likely OCR or encoding artifacts. "
    "Omit extraction_flags (or use []) for clearly readable, unambiguous blocks."
)
```

Appended to the existing `text` content block in both node functions — the instruction
string is kept in a single constant, not inlined twice.

---

## 4. Tests

### 4.1 Schema unit tests (`tests/unit/test_schema_registry.py`)

Add a `_base_block()` helper (alongside the existing `_contract_block()`):

```python
def _base_block() -> dict:
    return {
        "block_id": "b1",
        "type": "paragraph",
        "text": "Sample text.",
        "bbox": {"page_number": 1, "coordinates": [50, 50, 100, 80]},
    }
```

`paragraph` is valid in all four schemas, so this helper works uniformly without
any `doc_type` branching. For `invoice` and `scientific_paper` the `document_type`
enum constraint in those schemas requires the payload's `document_type` to match —
passing `doc_type` as the payload value satisfies that automatically.

Parametrized over all 4 schemas to catch any schema that missed the change:

```python
@pytest.mark.parametrize("doc_type", ["baseline_core", "invoice", "scientific_paper", "contract"])
def test_extraction_flags_valid_flag_accepted(doc_type):
    registry = SchemaRegistry()
    block = {**_base_block(), "extraction_flags": ["ambiguous_type"]}
    registry.validate(doc_type, {"document_type": doc_type, "blocks": [block]})

@pytest.mark.parametrize("doc_type", ["baseline_core", "invoice", "scientific_paper", "contract"])
def test_extraction_flags_invalid_flag_rejected(doc_type):
    registry = SchemaRegistry()
    block = {**_base_block(), "extraction_flags": ["made_up_flag"]}
    with pytest.raises(jsonschema.ValidationError):
        registry.validate(doc_type, {"document_type": doc_type, "blocks": [block]})

@pytest.mark.parametrize("doc_type", ["baseline_core", "invoice", "scientific_paper", "contract"])
def test_extraction_flags_absent_passes(doc_type):
    registry = SchemaRegistry()
    registry.validate(doc_type, {"document_type": doc_type, "blocks": [_base_block()]})

@pytest.mark.parametrize("doc_type", ["baseline_core", "invoice", "scientific_paper", "contract"])
def test_extraction_flags_duplicate_flag_rejected(doc_type):
    registry = SchemaRegistry()
    block = {**_base_block(), "extraction_flags": ["ambiguous_type", "ambiguous_type"]}
    with pytest.raises(jsonschema.ValidationError):
        registry.validate(doc_type, {"document_type": doc_type, "blocks": [block]})
```

(4 doc_types × 4 test functions = 16 total new parametrized unit tests)

### 4.2 Unit test: flags survive pipeline passthrough

A unit-level test in `tests/unit/nodes/test_worker_node.py` that mocks a
`_call_api` response carrying `extraction_flags` and asserts the flags appear in
`result["extracted_flat_blocks"][0]`:

```python
async def test_extraction_flags_passed_through(self, sample_state, sample_block, mocker):
    block_with_flags = {**sample_block, "extraction_flags": ["low_legibility"]}
    response = _make_tool_use_response([block_with_flags])
    _setup_mocks(mocker, response)
    result = await window_parser_node(sample_state)
    assert result["extracted_flat_blocks"][0].get("extraction_flags") == ["low_legibility"]
```

Note: `sample_block` must be a function parameter (pytest fixture injection), not a
module-level variable. Note also that `window_parser_node` does not run schema
validation — it returns the raw `tool_block.input["blocks"]` unchanged — so this test
confirms the field is not stripped in transit. Schema validation of flags is covered by
the parametrized tests in section 4.1.

This gives non-e2e coverage that the flag survives the full extraction path.

### 4.3 H-group e2e test (optional, `@pytest.mark.e2e`)

A synthetic fixture where the content is genuinely ambiguous — for example, a single
short line of text (3–4 words) that could be either a heading or a paragraph — should
trigger `ambiguous_type`. The test only asserts structure: any `extraction_flags` value
that appears must be a member of the valid enum. No assertion that flags must be present
(too flaky) and no assertion on specific values.

---

## 5. Scope

| File | Change |
|------|--------|
| `schemas/baseline_core.json` | Add `extraction_flags` enum array |
| `schemas/invoice.json` | Same |
| `schemas/scientific_paper.json` | Same |
| `schemas/contract.json` | Same |
| `src/nodes/worker_node.py` | Add `_EXTRACTION_FLAGS_INSTRUCTION` constant; append in both node functions |
| `tests/unit/test_schema_registry.py` | 3 parametrized tests × 4 schemas = 12 unit tests |
| `tests/unit/nodes/test_worker_node.py` | 1 new unit test: flags survive passthrough |
| `tests/fixtures/generators/grp_h_edge.py` | New ambiguous-type fixture (optional) |
| `tests/integration/test_synthetic_grp_h.py` | New H-group e2e test (optional) |
| `schemas/README.md` | Document `extraction_flags` field; update "existing schemas" table |
| `README.md` | Update test count; document new field in block types / output format |
| `pyproject.toml` | Version bump (minor: new feature) |
| `CHANGELOG.md` | Entry |
| `ROADMAP.md` | Mark B2 done |

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Model emits unknown flag string (not in enum) | Schema validation rejects it → retry loop fires, error fed back |
| Model never sets flags on genuinely ambiguous content | No test asserts flags are present; no regression. Quality observable only via e2e runs |
| Model always sets all 4 flags (over-flagging) | Prompt says "omit for clearly readable"; e2e review catches systemic over-flagging |
| Flags add tokens on clean docs | Model omits the field when absent; typical overhead near zero |
| Downstream consumers treat absent field differently from `[]` | Document that absent = empty = high confidence; consider schema `default: []` |

---

## 7. Acceptance Criteria

- [ ] All 4 schemas accept valid flags and reject unknown flags
- [ ] All 4 schemas reject duplicate flags (`uniqueItems: true`)
- [ ] Block without `extraction_flags` still passes validation in all 4 schemas
- [ ] `_EXTRACTION_FLAGS_INSTRUCTION` constant defined once; appended after `{extra_instructions}` in both node functions
- [ ] 17 new non-e2e tests pass (16 parametrized schema + 1 passthrough unit test)
- [ ] `make test` passes with no regressions
- [ ] `schemas/README.md` and `README.md` updated to document the field
