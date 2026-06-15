# B1 — New Document Schema: Contract

_Created: 2026-06-15 20:20_
_Updated: 2026-06-15 20:45 · Devil's advocate pass: fixed test placement bug, clarified test specs, added classifier unit test, added adversarial B4 fixture, documented schema design decisions_

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
| `tests/fixtures/generators/grp_b_classifier.py` | Add B3 contract PDF + golden; add B4 adversarial invoice PDF + golden |
| `tests/integration/test_synthetic_grp_b.py` | Add `test_b3_contract` and `test_b4_invoice_not_reclassified` inside `TestGroupB` |
| `tests/unit/nodes/test_classifier_node.py` | Add `test_contract_classified` |
| `tests/unit/test_schema_registry.py` | Add contract schema unit tests |
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

**Design decision — no conditional `required`**: The schema does not enforce
`metadata.signature` when `type == "signature_block"` via `if/then` conditionals.
This is intentional and consistent with how `invoice.json` handles `table_data`
(not conditionally required on `table` blocks) and `scientific_paper.json`
(bibliographic not required on `title` blocks). The extraction instructions
(`_CONTRACT_INSTRUCTIONS`) carry the enforcement signal to the model; schema
validation catches structural violations, not instructional compliance.

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

## 4. Test Fixtures: `tests/fixtures/generators/grp_b_classifier.py`

### B3 — Contract fixture (happy path)

Add `_make_b3_contract()` — a one-page synthetic "SERVICE AGREEMENT" that is
unambiguously a contract with no invoice-like elements:

- Title: "SERVICE AGREEMENT"
- Parties block: "THIS AGREEMENT is entered into… by and between Alpha Corp ("Client") and Beta LLC ("Service Provider")"
- Recitals heading: "RECITALS"
- Two recital paragraphs ("WHEREAS, Client wishes to obtain services…", "NOW, THEREFORE…")
- Clause heading: "1. SERVICES" + paragraph body
- Clause heading: "2. PAYMENT TERMS" + paragraph body
- Clause heading: "3. GOVERNING LAW" + "This Agreement shall be governed by the laws of the State of New York."
- Signature block: Two columns (Client / Service Provider) with name/title/date lines

Golden file: `_write_golden_b("grp_b_contract", "contract")` → `grp_b_contract.json`
with `{"expected": {"document_type": "contract", "blocks": []}}`.

### B4 — Adversarial invoice with legal boilerplate

Add `_make_b4_invoice_legal()` — a vendor invoice that includes a "Terms and
Conditions" section (the key stress case for alphabetical-first bias on "contract"):

- Title: "INVOICE #099"
- Bill-to / ship-to header
- Line-items table (Qty, Unit Price, Amount)
- Total + payment due date
- Footer section: "TERMS AND CONDITIONS: Payment is due within 30 days.
  This invoice is governed by the laws of California. No warranty is implied."

The footer includes legal-sounding language but the document is structurally
an invoice. The classifier must return `"invoice"`, not `"contract"`.

Golden file: `_write_golden_b("grp_b_invoice_legal", "invoice")` → `grp_b_invoice_legal.json`.

Update `generate()` to call both new helpers.

**Note on `generate_all.py`**: No changes needed. The hash-based manifest mechanism
in `generate_all.py` keys on the `grp_b_classifier.py` file hash. Modifying that file
changes its hash, which triggers regeneration on the next `hash_check_all()` run. CI
environments that cache the manifest from before the change will regenerate on first run
after the file changes.

---

## 5. Tests

### 5.1 Unit tests: `tests/unit/nodes/test_classifier_node.py`

Add inside `TestClassifierNode`:
- `test_contract_classified` — mocked response `"contract"` → `result["document_type"] == "contract"` and `result["target_json_schema"]` is a dict with `"properties"` (verifies schema loaded, not just type set).

### 5.2 Unit tests: `tests/unit/test_schema_registry.py`

Extend `TestLoadSchema`:
- `test_contract_loads` — `registry._load_schema("contract")` returns a dict with `"properties"`

Extend `TestGetSchemaAndTool`:
- `test_contract_tool_name` — `get_schema_and_tool("contract")` returns tool with `name == "extract_contract_structure"`

Extend `TestValidate`:
- `test_contract_paragraph_block_passes` — payload with one `paragraph`-type block validates without error
- `test_contract_signature_block_type_accepted` — payload with one `signature_block`-type block validates (these are two separate payloads, not one block with both types)
- `test_contract_invalid_block_type_rejected` — payload with `type == "invalid_type_xyz"` raises `ValidationError`

### 5.3 Classifier e2e tests: `tests/integration/test_synthetic_grp_b.py`

Both new tests are **methods inside the existing `class TestGroupB`** so they inherit
the `@pytest.mark.e2e` and `@pytest.mark.grp_b` class-level markers. A bare function
outside the class would not carry these marks, causing it to run without API key
protection and be excluded from `grp_b`-targeted runs.

```python
class TestGroupB:
    # ... existing test_b1_invoice, test_b2_scientific_paper ...

    async def test_b3_contract(self):
        golden = _load_golden("grp_b_contract")
        result = await _run_b_test(str(_PDFS / "grp_b_contract.pdf"))
        doc_type = result["hierarchical_document_tree"]["document_type"]
        assert doc_type == golden["expected"]["document_type"]

    async def test_b4_invoice_not_reclassified(self):
        """Invoice with legal boilerplate footer must not be misclassified as contract."""
        golden = _load_golden("grp_b_invoice_legal")
        result = await _run_b_test(str(_PDFS / "grp_b_invoice_legal.pdf"))
        doc_type = result["hierarchical_document_tree"]["document_type"]
        assert doc_type == golden["expected"]["document_type"]
```

---

## 6. Classifier Prompt Dilution Risk

**Risk**: Adding "contract" adds a third valid token. Documents with legal boilerplate
(e.g. vendor invoices with "Terms and Conditions" sections) might shift toward "contract".

**Mitigation 1 — fixture design**: The B3 synthetic PDF contains exclusively
contract-specific signals. No tables resembling invoice line items.

**Mitigation 2 — adversarial fixture (B4)**: A vendor invoice with legal-sounding
footer text is explicitly tested (Section 5.3). This is the stress case for
position-bias and for the "Terms and Conditions" boundary. It must return `"invoice"`.

**Mitigation 3 — existing B1/B2 act as regression guards**: If `grp_b_invoice.pdf`
or `grp_b_scientific_paper.pdf` starts returning "contract" post-change, B1/B2 catch it.

**Mitigation 4 — classifier fallback**: If the model returns something other than
`{"contract", "invoice", "scientific_paper"}`, `FALLBACK_DOC_TYPE` ("baseline_core")
kicks in. No data loss — degraded schema, not a crash.

**Risk: "contract" is alphabetically first** — `sorted(SUPPORTED_DOC_TYPES)` produces
`['contract', 'invoice', 'scientific_paper']`. The classifier prompt is
`"Return ONLY one token from ['contract', 'invoice', 'scientific_paper']."`.
If Claude has any first-item bias, "contract" is over-exposed. B4 is the direct
regression guard for this risk. The risk is speculative given Claude's strong
instruction following, but B4 removes the need to merely hope.

---

## 7. Acceptance Criteria

- [ ] `schemas/contract.json` validates a canonical contract payload (parties, clauses, signature_block) with no errors
- [ ] `SchemaRegistry().get_schema_and_tool("contract")` returns a tool named `"extract_contract_structure"`
- [ ] `src/config.py` `SUPPORTED_DOC_TYPES` contains `"contract"`
- [ ] All existing unit tests pass unchanged
- [ ] All existing integration tests pass unchanged (B1, B2)
- [ ] New unit tests pass:
  - `test_contract_classified` in `test_classifier_node.py`
  - `test_contract_loads`, `test_contract_tool_name` in `test_schema_registry.py`
  - `test_contract_paragraph_block_passes`, `test_contract_signature_block_type_accepted`, `test_contract_invalid_block_type_rejected` in `test_schema_registry.py`
- [ ] Fixture generator produces `grp_b_contract.pdf`, `grp_b_invoice_legal.pdf` and their golden files
- [ ] B3 e2e test classifies the synthetic contract PDF as `"contract"` (requires `ANTHROPIC_API_KEY`)
- [ ] B4 adversarial e2e test classifies the invoice-with-legal-footer PDF as `"invoice"` (requires `ANTHROPIC_API_KEY`)
- [ ] `make test` (non-e2e suite) passes with no regressions

---

## 8. Out of Scope

- Real-document corpus entry for contracts (can be added later as a grp_r slot)
- Hierarchy rules specific to contracts (clauses → sub-clauses parent assignment)
- Extraction quality evaluation on real contracts
- Any OCR / scan handling
