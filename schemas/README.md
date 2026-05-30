# Adding a New Document Type

PDFScout uses JSON Schema Draft-07 files to drive three things at once: Claude's
tool-calling contract, runtime output validation, and the self-healing retry
feedback loop. Adding a new document type means writing one JSON file and
updating one constant. Nothing else in the pipeline changes.

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

## The two-step process

### Step 1 — Add `schemas/<your_type>.json`

The filename (without `.json`) is the type token. It must be a single lowercase
string with no spaces (use underscores). The classifier returns this exact string.

### Step 2 — Add the token to `SUPPORTED_DOC_TYPES` in `src/config.py`

```python
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper", "your_type"}
```

That's it. The classifier, schema registry, validation loop, and Langfuse
metadata enrichment all pick it up automatically.

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
          "metadata": { "type": "object" }
        },
        "required": ["block_id", "type", "bbox", "text"]
      }
    }
  },
  "required": ["document_type", "blocks"]
}
```

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

**`schemas/contract.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgnosticContractStructure",
  "type": "object",
  "properties": {
    "document_type": { "type": "string", "enum": ["contract"] },
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
          "metadata": {
            "type": "object",
            "properties": {
              "parties": {
                "type": "object",
                "properties": {
                  "role":  { "type": "string" },
                  "name":  { "type": "string" },
                  "address": { "type": "string" }
                }
              },
              "clause": {
                "type": "object",
                "properties": {
                  "clause_number": { "type": "string" },
                  "clause_title":  { "type": "string" }
                }
              },
              "effective_date": { "type": "string" },
              "jurisdiction":   { "type": "string" }
            }
          }
        },
        "required": ["block_id", "type", "bbox", "text"]
      }
    }
  },
  "required": ["document_type", "blocks"]
}
```

**`src/config.py`** — one line added:

```python
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper", "contract"}
```

---

## Constraints and pitfalls

| Rule | Why |
|---|---|
| The 8-type block enum must not change | The pipeline, hierarchy agent, and all downstream consumers depend on exactly these 8 types |
| `document_type` enum must match the filename | `SchemaRegistry` loads `schemas/<doc_type>.json`; a mismatch causes Claude to extract with the wrong type token |
| `coordinates` must include the `[ymin, xmin, ymax, xmax]` description | `hierarchy_node.py`'s `geometric_pre_sorter` unpacks `ymin, xmin, _, _` at index 0,1 — wrong order silently breaks reading-order sorting |
| Do not add `"required"` to `metadata` properties | Claude populates metadata only on relevant blocks; required fields would cause validation failures on every other block |
| `$schema` and `title` are stripped before sending to Claude | `SchemaRegistry.get_schema_and_tool()` removes them; they are safe to include for your own reference |
| The fallback schema (`baseline_core`) is used for unknown types | If the classifier returns a token not in `SUPPORTED_DOC_TYPES`, the registry silently falls back to `baseline_core.json` |

---

## Existing schemas

| File | Document type | Domain metadata fields |
|---|---|---|
| `baseline_core.json` | Generic fallback | None — bare `metadata: {}` |
| `invoice.json` | `invoice` | `metadata.table_data` (normalized cell matrix) |
| `scientific_paper.json` | `scientific_paper` | `metadata.bibliographic`, `metadata.section`, `metadata.reference`, `metadata.figure_table`, `metadata.table_data` |
