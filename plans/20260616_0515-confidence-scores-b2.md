# B2 — Extraction Quality Flags on Blocks

_Created: 2026-06-16 05:15_
_Updated: 2026-06-16 05:25 · Replaced scalar confidence with structured flags after design review_
_Updated: 2026-06-16 05:45 · Fixed 4 bugs found in devil's advocate review: uniqueItems, _base_block helper, sample_block fixture arg, invocation count_
_Updated: 2026-06-16 05:50 · Added extraction_note string field to feed a future remediation agent_
_Updated: 2026-06-16 05:58 · Fixed prompt (over-anchoring example removed, counter-pressure added), maxLength moved to config constant, extraction_note passthrough test added, plan fully synced with implementation_

## Overview

Add two optional companion fields to every extracted block:

- **`extraction_flags`** — array of named enum strings, each naming a specific reason why
  the extraction may be uncertain. Gives RAG pipelines actionable signals they can filter or
  route on, rather than an opaque scalar they can't interpret.
- **`extraction_note`** — one-sentence free-text description of the specific observable symptom
  on that block. Set only when `extraction_flags` is non-empty. Designed to feed a downstream
  remediation agent that can inspect flagged blocks and attempt targeted correction.

**Design decision:** A self-reported `confidence: 0.7` is unreliable (LLMs are
miscalibrated, hard to validate, not testable without ground truth). A defined enum
of named flags forces the model to commit to a specific reason, is schema-validatable,
and lets downstream consumers act on type rather than threshold. Empty array = high
confidence extraction.

**Primary use case:** RAG pipeline filtering + remediation agent input.
```python
high_quality = [b for b in blocks if not b.get("extraction_flags")]
uncertain    = [b for b in blocks if b.get("extraction_flags")]
# uncertain blocks carry extraction_note for a remediation agent
```

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

All four schema files receive the same two additions to the block item properties:

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
  "description": "Set when extraction quality is uncertain. Omit (or use []) for high-confidence blocks. ..."
},
"extraction_note": {
  "type": "string",
  "description": "One-sentence explanation of the specific issue on this block. Set only when extraction_flags is non-empty. Provides context for a downstream remediation agent."
}
```

`extraction_flags` is **not** added to `required` — the model omits it on
unambiguously clean blocks, keeping the response compact.

`"uniqueItems": true` prevents the model from emitting duplicate flags.

`extraction_note` has **no `maxLength` in the JSON files** — the limit is injected at
load time by `SchemaRegistry._load_schema()` using `EXTRACTION_NOTE_MAX_LENGTH` from
`src/config.py` (currently 200). This keeps the value in one place and schema files
free of hardcoded limits.

**Known limitation:** JSON Schema draft-07 cannot enforce that `extraction_note` requires
`extraction_flags` to be non-empty (`dependentRequired` is draft 2019-09+). The constraint
is enforced by prompt instruction only. A model that emits `extraction_note` with no flags
will pass schema validation. This is acceptable — the note is additive and the downstream
consumer should treat `extraction_flags` as the authoritative signal.

**Files:** `schemas/baseline_core.json`, `schemas/invoice.json`,
`schemas/scientific_paper.json`, `schemas/contract.json`.

---

## 3. Extraction Prompt: `src/nodes/worker_node.py`

Module-level constant, defined once, appended after `{extra_instructions}` in the
existing f-string in **both** `window_parser_node` (line ~104) and `burst_worker_node`
(line ~171). Do **not** add a separate content item — stay within the existing text block.

```python
_EXTRACTION_FLAGS_INSTRUCTION = (
    " Flags should be rare — omit extraction_flags (or use []) for clearly readable, "
    "unambiguous blocks. Set extraction_flags only when quality is genuinely uncertain: "
    "'partial_visibility' if the block is cut off at the page edge and text is missing; "
    "'low_legibility' if text is hard to read due to scan quality, low contrast, or overlap; "
    "'ambiguous_type' if you are uncertain which block type is most appropriate; "
    "'possible_encoding_error' if the text contains likely OCR or encoding artifacts "
    "(garbled characters, unexpected symbols, mixed scripts). "
    "When you set extraction_flags, also set extraction_note to one sentence naming what "
    "is specifically wrong — describe the observable symptom, not a generic label "
    "(e.g. 'Top third of text is obscured by a watermark' or "
    "'Characters alternate between Cyrillic and Latin with no language boundary'). "
    "Omit extraction_note when extraction_flags is absent or empty."
)
```

Key prompt design choices:
- **"Flags should be rare"** leads — establishes counter-pressure before listing when to set them
- **Two examples for `extraction_note`** — one per qualitatively different flag type; avoids the model anchoring to spatial/coordinate language for non-spatial flags
- **"Observable symptom, not a generic label"** — guards against non-actionable notes like "text quality is poor"

---

## 4. Config: `src/config.py`

```python
EXTRACTION_NOTE_MAX_LENGTH = 200  # max chars for extraction_note; injected into all schemas at load time
```

---

## 5. SchemaRegistry: `src/schema_registry.py`

`_load_schema()` injects `maxLength` after loading the JSON:

```python
note_props = (
    schema.get("properties", {})
    .get("blocks", {})
    .get("items", {})
    .get("properties", {})
    .get("extraction_note")
)
if note_props is not None:
    note_props["maxLength"] = EXTRACTION_NOTE_MAX_LENGTH
```

This means: changing `EXTRACTION_NOTE_MAX_LENGTH` in config.py automatically updates all
four schemas. No schema JSON file needs touching.

---

## 6. Tests

### 6.1 Schema unit tests (`tests/unit/test_schema_registry.py`)

`_base_block()` helper (alongside existing `_contract_block()`):

```python
def _base_block() -> dict:
    return {
        "block_id": "b1",
        "type": "paragraph",
        "text": "Sample text.",
        "bbox": {"page_number": 1, "coordinates": [50, 50, 100, 80]},
    }
```

`TestExtractionFlags` class — 7 test functions × 4 doc types = 28 parametrized tests:

| Test | Asserts |
|------|---------|
| `test_extraction_flags_valid_flag_accepted` | Valid flag passes |
| `test_extraction_flags_invalid_flag_rejected` | Unknown flag raises ValidationError |
| `test_extraction_flags_absent_passes` | No flags field passes |
| `test_extraction_flags_duplicate_flag_rejected` | `uniqueItems` rejects duplicates |
| `test_extraction_note_with_flags_accepted` | String note alongside flags passes |
| `test_extraction_note_absent_passes` | No note field passes |
| `test_extraction_note_too_long_rejected` | 201-char note raises ValidationError |

### 6.2 Pipeline passthrough tests (`tests/unit/nodes/test_worker_node.py`)

Two tests in `TestWindowParserNode`:

```python
async def test_extraction_flags_passed_through(self, sample_state, sample_block, mocker):
    block_with_flags = {**sample_block, "extraction_flags": ["low_legibility"]}
    ...
    assert result["extracted_flat_blocks"][0].get("extraction_flags") == ["low_legibility"]

async def test_extraction_note_passed_through(self, sample_state, sample_block, mocker):
    block_with_note = {**sample_block, "extraction_flags": ["low_legibility"], "extraction_note": "Text is faint."}
    ...
    assert result["extracted_flat_blocks"][0].get("extraction_note") == "Text is faint."
```

`window_parser_node` returns `tool_block.input["blocks"]` unchanged — these tests confirm
neither field is stripped in transit.

### 6.3 H-group e2e test (optional, `@pytest.mark.e2e`)

A synthetic fixture where content is genuinely ambiguous (3–4 word line that could be
heading or paragraph) should trigger `ambiguous_type`. The test only asserts structure:
any `extraction_flags` value that appears must be a member of the valid enum. No assertion
that flags must be present (too flaky) and no assertion on specific values.

---

## 7. Scope

| File | Change |
|------|--------|
| `schemas/baseline_core.json` | Add `extraction_flags` enum array + `extraction_note` string |
| `schemas/invoice.json` | Same |
| `schemas/scientific_paper.json` | Same |
| `schemas/contract.json` | Same |
| `src/config.py` | Add `EXTRACTION_NOTE_MAX_LENGTH = 200` |
| `src/schema_registry.py` | Inject `maxLength` from config in `_load_schema()` |
| `src/nodes/worker_node.py` | Add `_EXTRACTION_FLAGS_INSTRUCTION` constant; append in both node functions |
| `tests/unit/test_schema_registry.py` | `_base_block()` helper; `TestExtractionFlags` with 7 × 4 = 28 parametrized tests |
| `tests/unit/nodes/test_worker_node.py` | 2 passthrough tests (flags + note) |
| `tests/fixtures/generators/grp_h_edge.py` | New ambiguous-type fixture (optional) |
| `tests/integration/test_synthetic_grp_h.py` | New H-group e2e test (optional) |
| `schemas/README.md` | Document both fields; note config constant |
| `README.md` | Update test count (157); document fields in output format + Extraction Flags section |
| `pyproject.toml` | Version bump to 1.6.0 |
| `CHANGELOG.md` | v1.6.0 entry |
| `ROADMAP.md` | Mark B2 done |

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Model emits unknown flag string (not in enum) | Schema validation rejects it → retry loop fires, error fed back |
| Model never sets flags on genuinely ambiguous content | No test asserts flags are present; no regression. Quality observable only via e2e runs |
| Model over-flags (sets flags on clean blocks) | Prompt leads with "flags should be rare"; e2e review catches systemic over-flagging |
| Model emits `extraction_note` without `extraction_flags` | Schema cannot enforce coupling (draft-07 limitation); prompt says "omit when no flags". Spurious notes are harmless — downstream consumer treats `extraction_flags` as authoritative |
| Model writes a generic, non-actionable note | Prompt says "observable symptom, not a generic label" with two concrete examples. Unverifiable without e2e; prompt is the best available guard |
| `extraction_note` exceeds one sentence / 200 chars | `maxLength: 200` enforced by `SchemaRegistry` at load time; violation triggers retry loop |
| Flags add tokens on clean docs | Model omits both fields when absent; typical overhead near zero |
| `EXTRACTION_NOTE_MAX_LENGTH` changed to a very small value | Lowering below ~50 breaks meaningful notes. No validation guards the config constant itself |

---

## 9. Acceptance Criteria

- [ ] All 4 schemas accept valid flags and reject unknown flags
- [ ] All 4 schemas reject duplicate flags (`uniqueItems: true`)
- [ ] All 4 schemas accept `extraction_note` ≤ 200 chars and reject > 200 chars
- [ ] Block without `extraction_flags` or `extraction_note` passes validation in all 4 schemas
- [ ] `EXTRACTION_NOTE_MAX_LENGTH` in `src/config.py` is the single source for the limit
- [ ] `SchemaRegistry._load_schema()` injects `maxLength` from config — no hardcoded value in JSON files
- [ ] `_EXTRACTION_FLAGS_INSTRUCTION` constant defined once; appended after `{extra_instructions}` in both node functions
- [ ] 30 new non-e2e tests pass (28 parametrized schema + 2 passthrough unit tests)
- [ ] `make test` passes with no regressions
- [ ] `schemas/README.md` and `README.md` updated to document both fields
