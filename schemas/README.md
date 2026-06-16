# Adding a New Document Type

PDFScout uses JSON Schema Draft-07 files to drive three things at once: Claude's
tool-calling contract, runtime output validation, and the self-healing retry
feedback loop. Adding a new document type requires writing one JSON schema file, updating one
constant, and optionally adding domain-specific extraction instructions.

---

## How the schema system works

`SchemaRegistry` (`src/schema_registry.py`) loads a schema at runtime and
uses it in two ways:

1. **Claude tool definition** — the schema becomes the `input_schema` of the
   tool Claude is forced to call. This is what constrains Claude's output
   structure. The fields `$schema` and `title` are stripped before sending
   (Anthropic's API rejects JSON Schema meta-fields in `input_schema`).

2. **Validation** — `jsonschema.validate()` checks the extracted blocks against
   the same schema. Failures feed a structured error message back to Claude for
   up to 3 self-healing retries.

The `coordinates` field carries a `description` that is forwarded to Claude
inside the schema. This is the only place the coordinate ordering convention
(`[ymin, xmin, ymax, xmax]`) is enforced — omitting it causes the geometric
pre-sorter in `hierarchy_node.py` to silently receive wrong coordinates.

---

## The three-step process

### Step 1 — Add `schemas/<your_type>.json`

The filename (without `.json`) is the type token. It must be a single lowercase
string with no spaces (use underscores). The classifier returns this exact string.

### Step 2 — Add the token to `SUPPORTED_DOC_TYPES` in `src/config.py`

```python
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper", "your_type"}
```

The classifier prompt is built at runtime from `sorted(SUPPORTED_DOC_TYPES)`, so no
prompt edit is needed. The schema registry, validation loop, and Langfuse metadata
enrichment all pick up the new type automatically.

### Step 3 — Add extraction instructions in `src/nodes/worker_node.py` *(recommended)*

Add a constant and a new branch in `_doc_type_instructions()`:

```python
_YOUR_TYPE_INSTRUCTIONS = (
    "\nFor your_type documents, populate metadata subfields where present on the page:"
    "\n- heading blocks introducing a section → your_domain (field_a, field_b)"
    # ...
)

def _doc_type_instructions(doc_type: str) -> str:
    if doc_type == "scientific_paper":
        return _SCIENTIFIC_PAPER_INSTRUCTIONS
    if doc_type == "contract":
        return _CONTRACT_INSTRUCTIONS
    if doc_type == "your_type":
        return _YOUR_TYPE_INSTRUCTIONS
    return ""
```

These instructions are appended to the extraction prompt for every page, guiding the
model to populate domain metadata subfields on the relevant block types. Without this
step the pipeline still functions — the model receives only the JSON schema as a tool
definition — but metadata fields will be sparsely populated.

---

## Schema structure

Every schema must include the **full baseline block structure**. The 8-type enum
and the `coordinates` description are non-negotiable — they are relied upon by
the rest of the pipeline.

### Required skeleton

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "YourTypeTitle",
  "type": "object",
  "properties": {
    "document_type": {
      "type": "string",
      "enum": ["your_type"]
    },
    "blocks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "block_id": { "type": "string" },
          "type": {
            "type": "string",
            "enum": ["title", "heading", "paragraph", "list_item", "table", "figure", "footnote", "margin_element"]
          },
          "bbox": {
            "type": "object",
            "properties": {
              "page_number": { "type": "integer" },
              "coordinates": {
                "type": "array",
                "description": "Bounding box as [ymin, xmin, ymax, xmax] integers in page coordinate space.",
                "items": { "type": "integer" },
                "minItems": 4,
                "maxItems": 4
              }
            },
            "required": ["page_number", "coordinates"]
          },
          "text": { "type": "string" },
          "is_continued": { "type": "boolean", "default": false },
          "extraction_flags": {
            "type": "array",
            "uniqueItems": true,
            "items": {
              "type": "string",
              "enum": ["partial_visibility", "low_legibility", "ambiguous_type", "possible_encoding_error"]
            }
          },
          "metadata": { "type": "object" }
        },
        "required": ["block_id", "type", "bbox", "text"]
      }
    }
  },
  "required": ["document_type", "blocks"]
}
```

### extraction_flags

`extraction_flags` is present in all four schemas as an optional array of named quality signals. The model sets it when extraction is uncertain; it omits the field (or uses `[]`) for clearly readable, unambiguous blocks.

Valid enum values: `"partial_visibility"`, `"low_legibility"`, `"ambiguous_type"`, `"possible_encoding_error"`. See the main README's "Extraction Flags" section for RAG filter patterns. Do not add a new schema without including `extraction_flags` — it is part of the shared baseline block structure.

`extraction_note` is a companion string field, present only when `extraction_flags` is non-empty. It holds one sentence describing the specific issue on that block (e.g. `"Left margin is flush at x=0, text appears truncated"`). Intended for a downstream remediation agent that inspects flagged blocks and attempts targeted correction.

### Adding domain-specific metadata

All domain-specific data goes inside the `metadata` object on each block. This
keeps the 8-type enum contract intact while allowing arbitrary structured fields
per document type.

Replace the bare `"metadata": { "type": "object" }` with a typed object that
declares your domain fields as optional properties:

```json
"metadata": {
  "type": "object",
  "properties": {
    "your_domain_field": {
      "type": "object",
      "properties": {
        "field_a": { "type": "string" },
        "field_b": { "type": "integer" }
      }
    }
  }
}
```

Making fields optional (no `"required"` on the metadata properties) lets Claude
populate them only on the blocks where they are relevant, without failing
validation on blocks where they don't apply.

---

## Worked example — `contract`

The contract schema is already implemented. It demonstrates two features beyond the
baseline: a domain-specific block type (`signature_block`) and multiple metadata
subfields per block.

**Key additions in `schemas/contract.json`:**

- Block type enum extended with `"signature_block"` — for areas containing signature
  lines, signatory names, and date fields
- `metadata.contract_meta` — document-level fields (`contract_type`, `effective_date`,
  `governing_law`); populate on `title` or `heading` blocks
- `metadata.party` — party identification (`party_name`, `party_role`, `address`);
  populate on `paragraph` or `heading` blocks
- `metadata.clause` — clause numbering (`clause_number`, `clause_title`); populate
  on `heading` blocks
- `metadata.signature` — signatory details (`signatory_name`, `party_role`,
  `date_label`); populate on `signature_block` blocks
- `metadata.table_data` — reused from invoice/scientific_paper for schedule tables

**`src/config.py`** — one line added:

```python
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper", "contract"}
```

**`src/nodes/worker_node.py`** — extraction instructions added:

```python
_CONTRACT_INSTRUCTIONS = (
    "\nFor contract documents, populate metadata subfields where present on the page:"
    "\n- title block for the document title → contract_meta (contract_type, effective_date, governing_law)"
    "\n- paragraph or heading blocks identifying a party → party (party_name, party_role, address)"
    "\n- heading blocks introducing a clause → clause (clause_number, clause_title)"
    "\n- signature area blocks → use type='signature_block' and metadata.signature (signatory_name, party_role, date_label)"
    "\n- schedule or exhibit tables → table_data (total_rows, total_cols, cells)"
)
```

---

## Constraints and pitfalls

| Rule | Why |
|---|---|
| The 8-type block enum is the baseline | The hierarchy agent and downstream consumers expect these 8 types. You may extend the enum with domain-specific types (e.g. `signature_block` in the contract schema), but only in that schema's own file — never remove the 8 base types |
| `document_type` enum must match the filename | `SchemaRegistry` loads `schemas/<doc_type>.json`; a mismatch causes Claude to extract with the wrong type token |
| `coordinates` must include the `[ymin, xmin, ymax, xmax]` description | `hierarchy_node.py`'s `geometric_pre_sorter` unpacks `ymin, xmin, _, _` at index 0,1 — wrong order silently breaks reading-order sorting |
| Do not add `"required"` to `metadata` properties | Claude populates metadata only on relevant blocks; required fields would cause validation failures on every other block |
| `$schema` and `title` are stripped before sending to Claude | `SchemaRegistry.get_schema_and_tool()` removes them; they are safe to include for your own reference |
| The fallback schema (`baseline_core`) is used for unknown types | If the classifier returns a token not in `SUPPORTED_DOC_TYPES`, the registry silently falls back to `baseline_core.json` |

---

## Existing schemas

| File | Document type | Block types | Domain metadata fields |
|---|---|---|---|
| `baseline_core.json` | Generic fallback | 8 base types | None — bare `metadata: {}` |
| `invoice.json` | `invoice` | 8 base types | `metadata.table_data` (normalized cell matrix) |
| `scientific_paper.json` | `scientific_paper` | 8 base types | `metadata.bibliographic`, `metadata.section`, `metadata.reference`, `metadata.figure_table`, `metadata.table_data` |
| `contract.json` | `contract` | 8 base + `signature_block` | `metadata.contract_meta`, `metadata.party`, `metadata.clause`, `metadata.signature`, `metadata.table_data` |
