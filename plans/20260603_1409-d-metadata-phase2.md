# D-Metadata Phase 2 — Reliable scientific_paper subfield population

_Created: 2026-06-03 14:09_
_Updated: 2026-06-03 14:15 · DA review v1 — Phase 0 made concrete, D4 ref-block assumption fixed, prompt ordering risk addressed, 0/3 exit condition added_

## Goal

D-group tests D2–D5 currently degrade to text-presence fallbacks because `metadata`
subfields (`bibliographic`, `section`, `reference`, `figure_table`) are not reliably
populated. After this plan the assertions become structural (the specific subfield must
be present and have correct values), not "if populated, check value".

**Success criterion:** D2, D3, D4, and D5 each pass a 5/5 stability gate with structural
assertions. D7 (absent-metadata guard) continues to pass.

---

## Root causes

Three independently controllable levers exist, all currently underused:

| Lever | Current state | Gap |
|---|---|---|
| `schemas/scientific_paper.json` field descriptions | None on metadata subfields | Claude receives field names only; no guidance on which block should carry which subfield |
| `_SCIENTIFIC_PAPER_INSTRUCTIONS` in `worker_node.py` | Suggestive — "populate … where present" | Not imperative; model may treat metadata as optional noise |
| D-test assertions | "if populated" fallbacks | Always pass even when metadata is empty |

`schema_registry.py` passes all non-`$schema`/non-`title` fields to Claude via `input_schema`,
so adding `description` fields to the schema costs zero extra prompt tokens and is immediately
visible to the model during tool-calling.

---

## Phases

### Phase 0 — Baseline sampling (calibration before touching anything)

Run a one-off diagnostic script that calls `app.ainvoke` for each D2–D5 PDF with
`scientific_paper` doc type (classifier mocked) and prints the full `metadata` dict for
every block. Three runs per fixture, output captured with `pytest -s` or a standalone
script. Log:

- Is the relevant subfield key present at all?
- If present, is the value populated (non-empty)?
- Is the content roughly correct?

**Exit condition — 0/3 present on all subfields after Phase 1+2:** Prompt alone may be
insufficient. The simplest escalation path is to add an explicit per-block-type check in
the retry loop: if `pioneer_validation_route` detects a heading block with a clearly
numbered section but an empty `metadata.section`, inject a targeted error prompt ("block
X has section number but metadata.section is missing"). This is narrower and safer than
schema-level `minProperties`, which would flag legitimately-empty metadata on body paragraphs
as violations.

Decision gate:
- **0/3 subfield present on any fixture**: Phase 1+2 both needed; re-run after.
- **2–3/3 present, values correct**: skip to Phase 3 (stability gate only).
- **2–3/3 present, values wrong**: Phase 1 schema descriptions + Phase 3.

### Phase 1 — Schema descriptions on metadata subfields

Add `description` to each metadata subfield in `schemas/scientific_paper.json`:

```json
"bibliographic": {
  "description": "Populate on the block carrying the paper's title, author list, abstract, or DOI. Use at most one block per page. Leave absent on all other blocks.",
  ...
}
"section": {
  "description": "Populate on heading blocks that begin with a section number (e.g. '2.', 'A.', 'III.'). Do not populate on un-numbered headings.",
  ...
}
"reference": {
  "description": "Populate on paragraph or list_item blocks that are numbered reference entries (e.g. '[1] Smith et al. ...'). One block per reference entry.",
  ...
}
"figure_table": {
  "description": "Populate on figure or table blocks. `label` is the short label (e.g. 'Figure 1', 'Table 2'), `caption` is the full descriptive caption text.",
  ...
}
```

No code changes — schema is loaded at runtime. No schema-validation side effects (`description`
is not a validation keyword in JSON Schema Draft-07).

### Phase 2 — Prompt refinement

Change `_SCIENTIFIC_PAPER_INSTRUCTIONS` in `worker_node.py` from suggestive to imperative.
Move it to **before** the coordinate/is_continued instruction so it receives early attention
in a multi-instruction prompt.

**Current:**
```python
"\nFor scientific_paper documents, populate metadata subfields where present on the page:"
"\n- title/paragraph blocks containing author names, abstract, or DOI → bibliographic ..."
```

**Target structure** — move metadata instructions to _before_ the coordinates line in the
prompt f-string (currently `extra_instructions` is a suffix; restructuring means placing the
`{extra_instructions}` interpolation before the coordinate/is_continued sentences):
```python
"\nFor scientific_paper documents you MUST populate the relevant metadata subfield on each block:"
"\n- Any block containing the paper title, author names, abstract, or DOI → set metadata.bibliographic"
"\n- Any heading that begins with a section number (e.g. '2.', 'A.') → set metadata.section"
"\n- Any numbered reference entry (e.g. '[1] Smith et al. ...') → set metadata.reference"
"\n- Any figure or table block → set metadata.figure_table (label + caption)"
"\nBlocks that match none of the above must have metadata={}."
```

Key changes: "MUST populate", explicit when-to-leave-empty rule, moved earlier in prompt to
avoid dilution by later instructions.

### Phase 3 — 5/5 stability gate per subfield

After Phase 1+2, run each of D2, D3, D4, D5 **five times** and record per-run whether the
target subfield is (a) present and (b) has correct values. A subfield that passes 5/5 is
considered stable enough to tighten. A subfield that passes ≤4/5 is not tightened in this
iteration — a comment is added: `# Stability: X/5 — tighten when reliable`.

### Phase 4 — Tighten D assertions

Replace the "if populated" fallback pattern with direct assertions for every subfield that
passed 5/5:

**D2 — bibliographic**
```python
# After
bib_blocks = [b for b in blocks if b.get("metadata", {}).get("bibliographic")]
assert bib_blocks, "No block has metadata.bibliographic populated"
# Collect all author strings across all blocks that have bibliographic
all_authors_str = str([b["metadata"]["bibliographic"].get("authors", []) for b in bib_blocks])
for author in authors:
    assert author in all_authors_str, f"Author '{author}' not in bibliographic.authors"
```

**D3 — section**
```python
assert section, "heading block has no metadata.section"
assert "2" in section.get("section_number", ""), ...
assert "Methodology" in section.get("section_title", ""), ...
```

**D4 — reference**
```python
# Model may merge all 3 refs into 1 block or produce 3 blocks — both are valid.
# Assert ≥1 block has reference metadata, and that year is int where present.
ref_blocks = [b for b in blocks if b.get("metadata", {}).get("reference")]
assert ref_blocks, "No block has metadata.reference populated"
for block in ref_blocks:
    ref = block["metadata"]["reference"]
    if ref.get("year") is not None:
        assert isinstance(ref["year"], int), f"reference.year should be int, got {type(ref['year'])}"
# Still assert all three citation markers are extractable as text
assert _text_in_some("[1]", blocks) and _text_in_some("[2]", blocks) and _text_in_some("[3]", blocks)
```

The D4 stability gate criterion is: **5/5 runs with ≥1 reference block** having metadata.reference.
The "≥3 blocks" assumption is dropped because merging is model-valid behaviour.

**D5 — figure_table**
```python
ft_blocks = [b for b in blocks if b.get("metadata", {}).get("figure_table")]
assert ft_blocks, "No block has metadata.figure_table populated"
ft = ft_blocks[0]["metadata"]["figure_table"]
assert "Figure 1" in ft.get("label", ""), ...
assert ft.get("caption"), "figure_table.caption should be non-empty"
```

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Even with improved prompt, some subfields only appear 3–4/5 | Medium | Only tighten those that pass 5/5; defer the rest with `# Stability: X/5 — deferred` comment |
| Schema descriptions make the tool schema larger → token cost increase | Low | Descriptions are 1–2 sentences; prompt-cached PDF dominates token cost |
| D7 false positive: baseline_core starts hallucinating subfields after prompt changes | Low | `_doc_type_instructions` only fires for scientific_paper; re-run D7 after Phase 2 to confirm |
| Tightened assertions are value-brittle (e.g. section_number = "2" vs "2.") | Medium | Use substring check (`"2" in value`) not exact equality |
| Prompt wording breaks D1 (invoice) | Very low | `_doc_type_instructions` returns `""` for invoice; add D1 to post-change regression run |
| "MUST" language causes over-population (section on non-numbered headings) | Low | Phase 0 will surface this if it happens; add negative fixture if needed |
| Phase 1+2 produce 0/3 even after changes | Low | Escalate: targeted retry-prompt injection — if pioneer detects a heading with a section number but empty `metadata.section`, add that specific error to `last_validation_error`; safer than schema-level `minProperties` which would fire on legitimately-empty blocks |

---

## Files touched

| File | Change |
|---|---|
| `schemas/scientific_paper.json` | Add `description` to `bibliographic`, `section`, `reference`, `figure_table` subfields |
| `src/nodes/worker_node.py` | Rewrite `_SCIENTIFIC_PAPER_INSTRUCTIONS` |
| `tests/integration/test_synthetic_grp_d.py` | Tighten D2–D5 assertions (per stability gate results) |

No new fixtures, no new generators, no new golden files.

---

## Verification sequence

```
Phase 0: pytest -m grp_d -v  ×3 — record raw metadata output
Phase 1+2: edit schema + prompt
Phase 3: pytest -m grp_d -v  ×5 — stability gate
Phase 4: tighten assertions that passed 5/5
Final: pytest -m e2e -v — confirm 37/37, D7 included
```
