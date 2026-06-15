# B1 — New Document Schema: Contract

_Created: 2026-06-15 20:20_

## Overview

Add `contract` as a first-class document type alongside `invoice` and `scientific_paper`.
A contract schema must capture the structural units that make contracts distinct: parties,
recitals, numbered clauses, schedule tables, and signature blocks.

## Scope

| File | Change |
|------|--------|
| `schemas/contract.json` | **New** — JSON schema for contract extraction |
| `src/config.py` | Add `"contract"` to `SUPPORTED_DOC_TYPES` |
| `src/nodes/worker_node.py` | Add `_CONTRACT_INSTRUCTIONS` constant and branch in `_doc_type_instructions()` |
| `tests/fixtures/generators/grp_b_classifier.py` | Add B3 contract PDF fixture + golden file |
| `tests/integration/test_synthetic_grp_b.py` | Add `test_b3_contract` |
| `tests/unit/test_schema_registry.py` | Add `test_contract_loads` and `test_contract_validates` |
| `pyproject.toml` | Bump minor version |
| `CHANGELOG.md` | Document the addition |

---

## 1. Schema Design: `schemas/contract.json`

### Block type enum

The contract schema inherits the same eight base block types as the other schemas:

```
"title", "heading", "paragraph", "list_item",
"table", "figure", "footnote", "margin_element"
```

A ninth type `"signature_block"` is added, **contract-schema-only**. Signature blocks
are visually and semantically distinct: they contain a combination of signature lines,
name/title fields, and dates, and cannot be naturally represented as a paragraph or
list_item without losing structural meaning.

### Metadata subfields

Each metadata sub-object is fully optional. The model populates what is present on the page.

| Subfield | Block types it applies to | Fields |
|----------|--------------------------|--------|
| `contract_meta` | `title`, `heading` (document-level) | `contract_type` (string), `effective_date` (string, ISO 8601), `governing_law` (string) |
| `party` | `paragraph`, `heading` | `party_name` (string), `party_role` (string: "buyer", "seller", "licensor", "licensee", "employer", "employee", etc.), `address` (string) |
| `clause` | `heading`, `paragraph` | `clause_number` (string: "1.", "1.2", "Article I"), `clause_title` (string) |
| `signature` | `signature_block` | `signatory_name` (string), `party_role` (string), `date_label` (string: "Date:" or "Dated:") |
| `table_data` | `table` | Same structure as invoice/scientific_paper — `total_rows`, `total_cols`, `cells[]` |

### Full schema (prose spec)

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
            "enum": [
              "title", "heading", "paragraph", "list_item",
              "table", "figure", "footnote", "margin_element", "signature_block"
            ]
          },
          "bbox": {
            "type": "object",
            "properties": {
              "page_number": { "type": "integer" },
              "coordinates": {
                "type": "array",
                "description": "Bounding box as [ymin, xmin, ymax, xmax] integers.",
                "items": { "type": "integer" },
                "minItems": 4, "maxItems": 4
              }
            },
            "required": ["page_number", "coordinates"]
          },
          "text": { "type": "string" },
          "is_continued": {
            "type": "boolean", "default": false,
            "description": "True when block text is truncated at page bottom."
          },
          "metadata": {
            "type": "object",
            "properties": {
              "contract_meta": {
                "type": "object",
                "properties": {
                  "contract_type":   { "type": "string" },
                  "effective_date":  { "type": "string" },
                  "governing_law":   { "type": "string" }
                }
              },
              "party": {
                "type": "object",
                "properties": {
                  "party_name": { "type": "string" },
                  "party_role": { "type": "string" },
                  "address":    { "type": "string" }
                }
              },
              "clause": {
                "type": "object",
                "properties": {
                  "clause_number": { "type": "string" },
                  "clause_title":  { "type": "string" }
                }
              },
              "signature": {
                "type": "object",
                "properties": {
                  "signatory_name": { "type": "string" },
                  "party_role":     { "type": "string" },
                  "date_label":     { "type": "string" }
                }
              },
              "table_data": {
                "type": "object",
                "properties": {
                  "total_rows": { "type": "integer" },
                  "total_cols": { "type": "integer" },
                  "cells": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "r":  { "type": "integer" }, "c":  { "type": "integer" },
                        "rs": { "type": "integer" }, "cs": { "type": "integer" },
                        "value": { "type": "string" },
                        "is_header": { "type": "boolean", "default": false }
                      },
                      "required": ["r", "c", "rs", "cs", "value"]
                    }
                  }
                },
                "required": ["total_rows", "total_cols", "cells"]
              }
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

---

## 2. Config Change: `src/config.py`

```python
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper", "contract"}
```

`sorted(SUPPORTED_DOC_TYPES)` becomes `['contract', 'invoice', 'scientific_paper']`.
The classifier prompt is regenerated at runtime from `SUPPORTED_DOC_TYPES`, so no prompt
edit is needed.

---

## 3. Worker Instructions: `src/nodes/worker_node.py`

Add a new constant `_CONTRACT_INSTRUCTIONS` and a new branch in `_doc_type_instructions()`.

```python
_CONTRACT_INSTRUCTIONS = (
    "\nFor contract documents, populate metadata subfields where present on the page:"
    "\n- title block for the document title → contract_meta (contract_type, effective_date, governing_law)"
    "\n- paragraph or heading blocks identifying a party → party (party_name, party_role, address)"
    "\n- heading blocks introducing a clause → clause (clause_number, clause_title)"
    "\n- signature area blocks → use type='signature_block' and metadata.signature (signatory_name, party_role, date_label)"
    "\n- schedule or exhibit tables → table_data (total_rows, total_cols, cells)"
)

def _doc_type_instructions(doc_type: str) -> str:
    if doc_type == "scientific_paper":
        return _SCIENTIFIC_PAPER_INSTRUCTIONS
    if doc_type == "contract":
        return _CONTRACT_INSTRUCTIONS
    return ""
```

---

## 4. Test Fixture: `tests/fixtures/generators/grp_b_classifier.py`

Add `_make_b3_contract()` — a one-page synthetic "SERVICE AGREEMENT" that is
unambiguously a contract:

- Title: "SERVICE AGREEMENT"
- Parties block: "THIS AGREEMENT is entered into… by and between Alpha Corp ("Client") and Beta LLC ("Service Provider")"
- Recitals heading: "RECITALS"
- Two recital paragraphs ("WHEREAS, Client wishes to obtain services…", "NOW, THEREFORE…")
- Clause heading: "1. SERVICES" + paragraph body
- Clause heading: "2. PAYMENT TERMS" + paragraph body
- Clause heading: "3. GOVERNING LAW" + "This Agreement shall be governed by the laws of the State of New York."
- Signature block: Two columns (Client / Service Provider) with name/title/date lines

Update `generate()` to call `_make_b3_contract()` and write golden file with
`{"expected": {"document_type": "contract"}}`.

---

## 5. Tests

### 5.1 Unit tests: `tests/unit/test_schema_registry.py`

Extend `TestLoadSchema`:
- `test_contract_loads` — `registry._load_schema("contract")` returns a dict with `"properties"`
- `test_contract_tool_name` — `get_schema_and_tool("contract")` returns tool with `name == "extract_contract_structure"`

Extend `TestValidate`:
- `test_contract_valid_passes` — a minimal valid contract payload (one paragraph block, `signature_block` type) validates without error
- `test_contract_signature_block_type_accepted` — block with `type == "signature_block"` validates
- `test_contract_invalid_block_type_rejected` — block with `type == "invalid_type_xyz"` raises `ValidationError`

### 5.2 Classifier test: `tests/integration/test_synthetic_grp_b.py`

Add:
```python
async def test_b3_contract(self):
    golden = _load_golden("grp_b_contract")
    result = await _run_b_test(str(_PDFS / "grp_b_contract.pdf"))
    doc_type = result["hierarchical_document_tree"]["document_type"]
    assert doc_type == golden["expected"]["document_type"]
```

---

## 6. Classifier Prompt Dilution Risk

**Risk**: Adding "contract" adds a third valid token. Documents with legal boilerplate
(e.g. vendor invoices with "Terms and Conditions" sections) might shift toward "contract".

**Mitigation 1 — fixture design**: The B3 synthetic PDF must contain exclusively
contract-specific signals. No tables resembling invoice line items.

**Mitigation 2 — adversarial assertion**: The existing B1/B2 tests continue running.
If `grp_b_invoice.pdf` starts returning "contract" post-change, B1 will catch it.
No new adversarial tests are strictly needed because B1 already asserts the invoice
PDF produces "invoice". However, a pass of B1+B2+B3 together is the adversarial gate.

**Mitigation 3 — classifier fallback**: If the model returns something other than
{"contract", "invoice", "scientific_paper"}, `FALLBACK_DOC_TYPE` ("baseline_core") kicks in.
No data loss — degraded schema, not a crash.

**Risk: "contract" is alphabetically first** in the sorted list. The classifier
prompt is positional — if Claude has token-order bias, "contract" might be over-chosen.
This is worth watching in B-group tests but is speculative and low-probability given
Claude's instruction-following capability.

---

## 7. Acceptance Criteria

- [ ] `schemas/contract.json` validates a canonical contract payload (parties, clauses, signature_block) with no errors
- [ ] `SchemaRegistry().get_schema_and_tool("contract")` returns a tool named `"extract_contract_structure"`
- [ ] `src/config.py` `SUPPORTED_DOC_TYPES` contains `"contract"`
- [ ] All existing unit tests pass unchanged
- [ ] All existing integration tests pass unchanged (B1, B2)
- [ ] New unit tests pass: `test_contract_loads`, `test_contract_tool_name`, `test_contract_valid_passes`, `test_contract_signature_block_type_accepted`, `test_contract_invalid_block_type_rejected`
- [ ] Fixture generator produces `grp_b_contract.pdf` and golden file `grp_b_contract.json`
- [ ] B3 e2e test classifies the synthetic contract PDF as `"contract"` (requires `ANTHROPIC_API_KEY`)
- [ ] `make test` (non-e2e suite) passes with no regressions

---

## 8. Out of Scope

- Real-document corpus entry for contracts (can be added later as a grp_r slot)
- Hierarchy rules specific to contracts (clauses → sub-clauses parent assignment)
- Extraction quality evaluation on real contracts
- Any OCR / scan handling
