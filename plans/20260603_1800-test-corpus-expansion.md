# Test Corpus Expansion — Plan

_Created: 2026-06-03 18:00_\
_Updated: 2026-06-03 19:00 · v2 — DA review: fix goal count (38→37), coordinate-check risk clarified, D7 spec'd inline (not _run_d_test), C12 _normalize import added, G2 >3-bucket risk tightened, pyproject.toml row removed from files table, _C10_TEXT variable resolved_

---

## Goal

Add 9 targeted test improvements across the synthetic e2e suite:
two stability checks on existing tests (C5/C6), three zero-fixture assertion additions
(coordinate order, page bleeding, F6 orphan), four small new fixture tests (H2, D7,
C10, C12), and one medium new fixture test (G2 three-column). Suite grows from 31
to a target of 37 tests (31 + 6 new: F6, H2, D7, C10, C12, G2 — pending C5/C6 stability
gating in Phase 0, which may add 0 more tests).

---

## Items in scope

| ID | What | Type | Phase |
|---|---|---|---|
| C5/C6 stability | Run each 5× to gate confidence before treating as stable | Diagnostic | 0 |
| Coord check | Verify `[ymin, xmin, ymax, xmax]` order is honoured in extraction output | Assertion on C1 | 1 |
| Page bleeding | Verify no page-N block contains text exclusive to page-(N±1) | Assertion on E1 | 1 |
| F6 | Paragraph appearing before any heading → `parent_id=None` | Pre-built blocks | 1 |
| H2 | 6pt-font page — pipeline completes, no crash | New fixture | 2 |
| D7 | `scientific_paper` with no author/abstract/DOI — optional fields absent, no validation error | New fixture | 2 |
| C10 | Latin-1 accented text (Résumé, naïve, café) — accents preserved in extraction | New fixture | 2 |
| C12 | Alternating bold/normal draw-text calls — no content silently dropped | New fixture | 2 |
| G2 | Three-column A4 — L-column blocks all precede M-column, M precede R | New fixture | 3 |

---

## Items NOT in scope

- C5/C6 fixture redesign (handled inline if Phase 0 reveals failures)
- `is_continued` for `list_item` / `table` block types
- Merging continuation fragments
- Multi-page metadata integration (extraction → hierarchy full chain for `scientific_paper`)
- End-to-end performance tests (20-page, 100-block density) — cost too high

---

## Phase 0 — C5/C6 stability check

**No code changes. Run each test five times and record pass/fail.**

```
for i in 1 2 3 4 5; do uv run pytest tests/integration/test_synthetic_grp_c.py::TestGroupC::test_c5_footnote -v; done
for i in 1 2 3 4 5; do uv run pytest tests/integration/test_synthetic_grp_c.py::TestGroupC::test_c6_margin_element -v; done
```

**Decision tree:**

| Outcome | Action |
|---|---|
| 5/5 pass | Mark stable — proceed to Phase 1, no fixture changes |
| 1–2 failures | Strengthen fixture (see below), then require 3/3 before Phase 1 |
| 3+ failures | Weaken assertion to text-presence only (no `type` check), re-run 3/3 |
| Still failing after weakening | Remove C5 / C6 from suite |

**If strengthening is needed:**

- C5 (footnote): increase horizontal rule length to 80mm (currently 60mm), add
  `"FOOTNOTE:"` prefix to each footnote line, widen the visual gap between body and
  footnote zone (move rule to y=190mm from 200mm).
- C6 (margin_element): reduce sidebar width to 25mm (currently 30mm) — brings it
  below 12% of page width. Add `"SIDEBAR"` as a bold label at the top of the rect.

---

## Phase 1 — Zero-fixture enhancements

Entry condition: Phase 0 complete (C5/C6 either stable or fixed/removed).

No PDF regeneration required. Only Python changes.

### 1a — Coordinate order check

**Where:** `tests/integration/_compare.py` (new helper) + `tests/integration/test_synthetic_grp_c.py::test_c1_paragraph` (one call site).

**Helper** (add to bottom of `_compare.py`):

```python
def assert_valid_bbox_fields(blocks: list[dict]) -> None:
    """For every block, assert bbox coordinates follow [ymin, xmin, ymax, xmax]
    order and are non-negative. Does not validate against mm values."""
    for b in blocks:
        coords = b["bbox"]["coordinates"]
        assert len(coords) == 4, f"block {b['block_id']!r}: expected 4 coordinates, got {len(coords)}"
        ymin, xmin, ymax, xmax = coords
        assert ymin < ymax, f"block {b['block_id']!r}: ymin ({ymin}) >= ymax ({ymax}) — wrong coordinate order?"
        assert xmin < xmax, f"block {b['block_id']!r}: xmin ({xmin}) >= xmax ({xmax}) — wrong coordinate order?"
        assert ymin >= 0 and xmin >= 0, f"block {b['block_id']!r}: negative coordinates {coords}"
```

**C1 addition** — append to `test_c1_paragraph` after existing assertions:

```python
from tests.integration._compare import assert_valid_bbox_fields
assert_valid_bbox_fields(blocks)
```

**Rationale:** Single-block, single-page fixture → simplest possible validation surface.
The helper can be adopted by other tests later without changing the plan.

**Risk:** A block with ymin == ymax has zero height — that is a malformed coordinate,
not a valid text block. Strict `<` is intentionally correct here: it would catch this
defect. The comment "would fail" does not mean the test is wrong; it means we would
detect an extraction error. All existing and planned fixtures produce blocks with
finite height, so no false positives are expected.

---

### 1b — Page bleeding assertion

**Where:** `tests/integration/test_synthetic_grp_e.py::test_e1_two_page` (assertion addition).

The `grp_e_2page.pdf` fixture has:
- Page 1: `"Page 1 content: This paragraph is exclusively on page 1."`
- Page 2: `"Page 2 content: This paragraph is exclusively on page 2."`

The unique cross-page marker is `"exclusively on page N"`. Add after the existing
`block_ids` assertion:

```python
# Page boundary isolation: no page-N block should carry text exclusive to page-(N+1/N-1).
page1_text = " ".join(b["text"] for b in blocks if b["bbox"]["page_number"] == 1).lower()
page2_text = " ".join(b["text"] for b in blocks if b["bbox"]["page_number"] == 2).lower()
assert "exclusively on page 2" not in page1_text, (
    "Page-1 blocks contain text from page 2 — possible page-bleeding in extraction"
)
assert "exclusively on page 1" not in page2_text, (
    "Page-2 blocks contain text from page 1 — possible page-bleeding in extraction"
)
```

**Rationale:** Uses verbatim fixture text that cannot appear on the "wrong" page by
coincidence. Does not assert exact text — only absence of cross-page contamination.

**Risk:** Claude might paraphrase "exclusively on page 1" as "only on the first page".
Mitigation: the fixture text uses the unusual phrase "exclusively on page N" which
is unlikely to be paraphrased into "exclusively on page M" where M ≠ N. No plan
changes needed — if this becomes a source of false positives in practice, add a
stronger unique token to the fixture text.

---

### 1c — F6 Orphan paragraph

**Where:** `tests/fixtures/generators/grp_f_hierarchy.py` (add `F6_BLOCKS`) +
`tests/integration/test_synthetic_grp_f.py` (add `test_f6_orphan_paragraph`).

**F6_BLOCKS:**

```python
# F6: [orphan_para, heading, child_para] — orphan appears before any heading.
# Verifies hierarchy assigns parent_id=None for a pre-heading paragraph,
# and still correctly parents the post-heading paragraph.
F6_BLOCKS = [
    {
        "block_id": "orphan",
        "type": "paragraph",
        "text": "Preamble text that appears before any section heading.",
        "bbox": {"page_number": 1, "coordinates": [30, 70, 45, 500]},
    },
    {
        "block_id": "h1",
        "type": "heading",
        "text": "Section One",
        "bbox": {"page_number": 1, "coordinates": [60, 70, 75, 500]},
    },
    {
        "block_id": "p1",
        "type": "paragraph",
        "text": "This paragraph belongs under section one.",
        "bbox": {"page_number": 1, "coordinates": [90, 70, 105, 500]},
    },
]
```

`geometric_pre_sorter` order: page=1, all xmin=70 (bucket 1), ymin ascending →
`orphan` first, `h1` second, `p1` third. ✓

**F6 test:**

```python
async def test_f6_orphan_paragraph(self):
    """[orphan_para, heading, child_para] → orphan at root (no preceding heading);
    child_para under heading (Rule 1)."""
    from src.nodes.hierarchy_node import layout_hierarchy_agent_node

    result = await layout_hierarchy_agent_node(make_state(list(F6_BLOCKS)))
    blocks = result["hierarchical_document_tree"]["structured_payload"]
    by_id = {b["block_id"]: b for b in blocks}

    assert by_id["orphan"]["parent_id"] is None, (
        f"Pre-heading paragraph should be root-level, got parent_id={by_id['orphan']['parent_id']!r}"
    )
    assert by_id["p1"]["parent_id"] == "h1", (
        f"Post-heading paragraph should have parent_id='h1', got {by_id['p1']['parent_id']!r}"
    )
```

**Determinism pre-check:** 3/3 before committing.

**Risk:** The hierarchy LLM might assign `orphan.parent_id = "h1"` (forward reference).
The prompt says "Blocks directly following a heading" — orphan appears before the
heading, so it should be null. If the LLM still assigns a forward parent:
→ Add explicit Rule 0 to the hierarchy prompt: "A block that appears before any
heading in the manifest is root-level (parent_id = null)."
Do not remove F6 or weaken the assertion — the forward-reference case is a real
production bug if it occurs.

**Distinction from orphan_warnings:** The `extraction_warnings` orphan mechanism fires
when a block is absent from the relation_map entirely. F6 tests the semantically
correct case — the LLM explicitly returns `parent_id=null` for the orphan. Both
outcomes (`null` via explicit relation or `null` via missing-from-map fallback) satisfy
the F6 assertion. F6 does NOT assert that an orphan warning is emitted.

---

## Phase 2 — New fixture additions

Entry condition: Phase 1 complete, 3/3 determinism checks passed for F6.

All four can be developed in parallel (different generator files). Commit as a single
batch after all four pass their pre-checks.

---

### H2 — Tiny text (graceful degradation)

**Generator:** Add `_make_h2_tiny_text()` to `grp_h_edge.py`; add to `generate()`.

```python
def _make_h2_tiny_text():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "Tiny text line one.", 20, 50, size=6)
    draw_text(pdf, "Tiny text line two.", 20, 58, size=6)
    draw_text(pdf, "Tiny text line three.", 20, 66, size=6)
    return pdf
```

**Fixture file:** `grp_h_tiny_text.pdf`

**Test:** Add `test_h2_tiny_text` to `TestGroupH`.

```python
async def test_h2_tiny_text(self):
    """6pt text page: pipeline completes without exception.
    Extraction quality is not asserted — only pipeline stability."""
    from src.graph import build_app

    app = build_app(checkpointer=None)
    with (
        patch("src.nodes.classifier_node._classify", new=AsyncMock(return_value="baseline_core")),
        patch("src.nodes.hierarchy_node._call_api",
              new=AsyncMock(return_value=_make_relation_response([]))),
    ):
        result = await app.ainvoke({"file_path": str(_PDFS / "grp_h_tiny_text.pdf")})

    tree = result["hierarchical_document_tree"]
    assert "structured_payload" in tree, "hierarchical_document_tree missing structured_payload key"
```

**Rationale:** This is a smoke test. If Claude returns 0 blocks, that is acceptable.
If Claude throws an exception or the pipeline crashes, the test fails. No `len(blocks)`
assertion — we do not require content to be readable at 6pt.

**Risk:** None. The assertion is the weakest possible above a trivial pass. If the
concern is "too weak to be useful", the value is entirely in catching future regressions
where 6pt text causes an API error or a pipeline exception.

---

### D7 — Scientific paper without metadata

**Generator:** Add `_make_d7_no_metadata()` to `grp_d_metadata.py`; add to `generate()`.

```python
def _make_d7_no_metadata():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "Computational Methods in PDF Analysis", 20, 25, size=16, style="B", align="C", w=170)
    draw_multiline(
        pdf,
        "This paper presents a method for extracting structured content from PDF documents "
        "without relying on heuristic layout rules. The approach is evaluated on a controlled "
        "benchmark of synthetic documents with known ground-truth annotations.",
        20, 50, size=11, w=170,
    )
    return pdf
```

**Fixture file:** `grp_d_no_metadata.pdf`

**Test:** Add `test_d7_absent_metadata` to `TestGroupD`. D7 must be implemented inline
(not via `_run_d_test`) because `_run_d_test` returns only `list[dict]` (blocks) and
D7 also needs `extraction_warnings` from the full tree. Do NOT modify `_run_d_test` —
it is used by D1–D5 and changing its signature would require updating all callers.

```python
async def test_d7_absent_metadata(self):
    """scientific_paper with no author/abstract/DOI: pipeline completes,
    schema validation passes (optional metadata fields tolerated absent)."""
    from src.graph import build_app

    app = build_app(checkpointer=None)
    with (
        patch("src.nodes.classifier_node._classify",
              new=AsyncMock(return_value="scientific_paper")),
        patch("src.nodes.hierarchy_node._call_api",
              new=AsyncMock(return_value=_make_relation_response([]))),
    ):
        result = await app.ainvoke({"file_path": str(_PDFS / "grp_d_no_metadata.pdf")})

    tree = result["hierarchical_document_tree"]
    blocks = tree["structured_payload"]
    warnings = tree.get("extraction_warnings", [])

    assert blocks, "No blocks extracted from bare scientific_paper"
    assert not any("validation" in w.lower() for w in warnings), (
        f"Schema validation errors found for absent optional metadata — "
        f"optional fields should be tolerated absent. Warnings: {warnings}"
    )
```

**Risk:** The `scientific_paper` extraction prompt explicitly requests optional subfields
(bibliographic, section, reference, figure_table). Claude may return `metadata: {}` or
`metadata: {"bibliographic": {"authors": [], "title": null}}`. Both are schema-valid.
However, `{"authors": null}` is NOT schema-valid (authors must be array).
If D7 reveals that null metadata values trigger schema violations, the fix is in the
extraction prompt (add: "Omit metadata subfields entirely when no data is available;
do not return null values for array fields"), NOT in the schema.

The test assertion for warnings is the key value here. If the assertion fires, we have
a prompt defect to fix.

---

### C10 — Latin-1 accented text

**Generator:** Add `_make_c10_unicode()` to `grp_c_blocktypes.py`; add to `generate()`.

**Supported character set:** Helvetica is a Latin-1 core font. Only Latin-1 code points
(U+0000–U+00FF) are safe. The following are all in range:
`é` (U+00E9), `ï` (U+00EF), `â` (U+00E2), `à` (U+00E0), `ô` (U+00F4), `È` (U+00C8).
Do NOT use: `ﬁ` (U+FB01 ligature), `—` (U+2014 em-dash), `€` (U+20AC).
The em-dash was confirmed unsupported in a previous session when it caused an fpdf2
encoding error.

The fixture text is used directly inside `_make_c10_unicode()` — no module-level
constant needed (single use).

```python
def _make_c10_unicode():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "Résumé: naïve café, document analysis approach.", 20, 50, size=12)
    return pdf
```

**Fixture file:** `grp_c_unicode.pdf`

**Test:** Add `test_c10_unicode_text` to `TestGroupC`.

```python
async def test_c10_unicode_text(self):
    """Latin-1 accented characters are preserved in extraction output."""
    blocks = await _run_c_test(str(_PDFS / "grp_c_unicode.pdf"))
    assert blocks, "No blocks extracted from unicode fixture"
    all_text = " ".join(b["text"] for b in blocks)
    # At least one of the three accented substrings must survive extraction.
    accented = ["sumé", "naïve", "café"]  # é=U+00E9, ï=U+00EF
    found = [s for s in accented if s.lower() in all_text.lower()]
    assert found, (
        f"No accented characters preserved in output. "
        f"Expected at least one of {accented!r} in extracted text. Got: {all_text!r}"
    )
```

**Rationale:** Requires at least 1 of 3 accented substrings to survive. This is
permissive enough to tolerate minor OCR/encoding drift (e.g., "naïve" → "naive" while
"café" and "Résumé" survive). If ALL three are mangled consistently, the test fails
and reveals a normalization issue in the extraction pipeline.

**Risk 1:** fpdf2 with Helvetica may encode `é` as the Latin-1 byte `0xE9`. Claude's
PDF parser must decode Latin-1 correctly. If it doesn't, all three fail → investigate
whether a Unicode-aware font (e.g., DejaVu) is needed in the fixture.

**Risk 2:** Claude might return "Resume" for "Résumé" consistently, failing the test.
In that case: add `"esum"` to `accented` as a fallback (tests that at least the ASCII
core of "Résumé" is present), and file a note that accent preservation is not guaranteed.
Do not remove the test — the degraded assertion still confirms the text is not dropped.

---

### C12 — Mixed emphasis (bold + normal)

**Generator:** Add `_make_c12_emphasis()` to `grp_c_blocktypes.py`; add to `generate()`.

```python
def _make_c12_emphasis():
    pdf = make_pdf()
    pdf.add_page()
    # Four alternating lines — two bold labels, two normal descriptions.
    # Each uses draw_text (separate visual blocks), not inline font switching.
    draw_text(pdf, "Introduction:", 20, 50, size=12, style="B")
    draw_text(pdf, "This section describes the core framework concepts.", 20, 60, size=12)
    draw_text(pdf, "Methodology:", 20, 78, size=12, style="B")
    draw_text(pdf, "We apply the extraction approach described above.", 20, 88, size=12)
    return pdf
```

**Fixture file:** `grp_c_emphasis.pdf`

**Test:** Add `test_c12_mixed_emphasis` to `TestGroupC`.

```python
async def test_c12_mixed_emphasis(self):
    """Bold and normal text lines: all four text fragments present in output.
    Tests that visual emphasis alternation does not cause content to be silently dropped."""
    from tests.integration._compare import _normalize  # already imported in other tests via _compare

    blocks = await _run_c_test(str(_PDFS / "grp_c_emphasis.pdf"))
    all_text = " ".join(_normalize(b["text"]) for b in blocks)
    for fragment in ["Introduction:", "core framework", "Methodology:", "extraction approach"]:
        assert _normalize(fragment).lower() in all_text.lower(), (
            f"Fragment {fragment!r} not found in any block — may have been silently dropped"
        )
```

**Implementation note:** `_normalize` is not currently imported in `test_synthetic_grp_c.py`.
Add `from tests.integration._compare import _normalize` alongside the existing import of
`_make_relation_response`.

**Rationale:** Tests content completeness, not block count. Claude may return 1 merged
block, 2 blocks (bold lines merged, normal lines merged), or 4 individual blocks.
All are acceptable as long as no text is dropped. The four fragments are chosen to be
distinctive and unlikely to be combined in a way that hides them.

**Risk:** The 10mm gap between "Introduction:" (y=50) and the start of "Methodology:"
(y=78) is large enough that Claude will likely treat these as separate semantic units.
Reducing the gap risks merging — increasing it has no downside. Keep at 10mm.

If the test fails because a bold label is merged into the following normal-text line
and the label itself disappears: the assertion `"Introduction:" in all_text` would
still pass since the combined text would contain the label. The only failure mode is
silent content omission, which is the precise defect being tested.

---

## Phase 3 — G2 Three-column layout

Entry condition: Phase 2 complete, all Phase 2 tests pass 3/3.

### G2 — Three-column reading order

**Generator:** Add `_make_g2_three_column()` to `grp_g_layout.py`; add golden file;
add to `generate()`.

**Column geometry:**

| Column | x start (mm) | width (mm) | Estimated Claude xmin | Estimated bucket (÷50) |
|---|---|---|---|---|
| Left (L) | 12 | 55 | ~55 | 1 |
| Middle (M) | 80 | 55 | ~215 | 4 |
| Right (R) | 148 | 42 | ~390 | 7 |

Right column ends at 148+42=190mm = A4 right margin. ✓

The Claude xmin estimate uses the same scale observed in G1 comments:
x=12.7mm→55, x=111mm→310, giving ~2.60 Claude units/mm. Actual values vary per
document but the bucket separation (1 vs 4 vs 7) is robust to ±30% scale variation.

Worst case: if Claude returns the middle column at xmin≈170 (bucket 3) and right at
xmin≈350 (bucket 7), the test still passes — it doesn't pin bucket numbers.

**Fixture text:** Two rows per column, with column identity in each label.

```
L1: Left column, block one.     M1: Middle column, block one.     R1: Right column, block one.
L2: Left column, block two.     M2: Middle column, block two.     R2: Right column, block two.
```

y positions: first row at y=40mm, second row at y=70mm (same for all columns).

**Generator code:**

```python
_LEFT_X_G2   = 12.0;  _MID_X_G2 = 80.0;  _RIGHT_X_G2 = 148.0
_COL_W_G2_LM = 55.0;  _COL_W_G2_R = 42.0
_Y_ROWS_G2   = [40, 70]

def _make_g2_three_column():
    pdf = make_pdf()
    pdf.add_page()
    for n, y in enumerate(_Y_ROWS_G2, start=1):
        draw_text(pdf, f"L{n}: Left column, block {n}.", _LEFT_X_G2, y, size=11, w=_COL_W_G2_LM)
        draw_text(pdf, f"M{n}: Middle column, block {n}.", _MID_X_G2, y, size=11, w=_COL_W_G2_LM)
        draw_text(pdf, f"R{n}: Right column, block {n}.", _RIGHT_X_G2, y, size=11, w=_COL_W_G2_R)
    return pdf
```

**Golden file:** `grp_g_three_column.json`, same structure as `grp_g_two_column.json`.

**Test:** Add `test_g2_three_column_reading_order` to `TestGroupG`.

```python
async def test_g2_three_column_reading_order(self):
    """Three-column layout: L-column blocks precede M-column, M precede R in output."""
    from src.config import COLUMN_BUCKET_PX
    from src.graph import build_app

    app = build_app(checkpointer=None)
    with (
        patch("src.nodes.classifier_node._classify", new=AsyncMock(return_value="baseline_core")),
        patch("src.nodes.hierarchy_node._call_api",
              new=AsyncMock(return_value=_make_relation_response([]))),
    ):
        result = await app.ainvoke({"file_path": str(_PDFS / "grp_g_three_column.pdf")})

    blocks = result["hierarchical_document_tree"]["structured_payload"]

    # Identify column buckets and verify strict left-to-right ordering.
    buckets = [b["bbox"]["coordinates"][1] // COLUMN_BUCKET_PX for b in blocks]
    unique_buckets = sorted(set(buckets))
    assert len(unique_buckets) >= 3, (
        f"Expected ≥3 column buckets, got {unique_buckets} — "
        "columns may not be sufficiently separated in Claude coordinates"
    )
    left_bkt, mid_bkt, right_bkt = unique_buckets[0], unique_buckets[1], unique_buckets[2]

    left_ix  = [i for i, bkt in enumerate(buckets) if bkt == left_bkt]
    mid_ix   = [i for i, bkt in enumerate(buckets) if bkt == mid_bkt]
    right_ix = [i for i, bkt in enumerate(buckets) if bkt == right_bkt]

    assert max(left_ix) < min(mid_ix), (
        f"Left-column blocks must all precede middle-column blocks. "
        f"Left indices: {left_ix}, middle indices: {mid_ix}"
    )
    assert max(mid_ix) < min(right_ix), (
        f"Middle-column blocks must all precede right-column blocks. "
        f"Middle indices: {mid_ix}, right indices: {right_ix}"
    )

    # Text presence
    all_text = " ".join(b["text"] for b in blocks).lower()
    for label in ["l1:", "l2:", "m1:", "m2:", "r1:", "r2:"]:
        assert label in all_text, f"Expected label {label!r} not found in output"
```

**Determinism pre-check:** 3/3 before committing.

**Risk 1:** Claude merges two columns into the same bucket. The `unique_buckets >= 3`
assertion catches this and fails the test. If this happens on any of the 3 pre-check
runs: widen the column separation (increase `_MID_X_G2` to 85mm and `_RIGHT_X_G2`
to 155mm), re-check 3/3.

**Risk 2:** If Claude returns x coordinates with enough noise that a single column's
blocks fall into two different buckets, `len(unique_buckets)` could be 4 or 5.
In that case `unique_buckets[1]` and `unique_buckets[2]` would both be sub-buckets
of the same physical column, and `mid_ix` / `right_ix` would contain blocks from the
same column rather than two different columns. The `max(mid_ix) < min(right_ix)`
assertion would then fail incorrectly (false failure) or pass incorrectly (false pass)
depending on block ordering.

**Mitigation for Risk 2:** Since all blocks in the same column are drawn at exactly
the same `x_mm` value, Claude should report the same (or very nearly the same) xmin
for all blocks in that column. With COLUMN_BUCKET_PX=50 providing ±25-unit tolerance,
intra-column coordinate noise would need to be >50 units (>19mm) to split a column
across buckets. This is well outside observed Claude coordinate variation for same-x
blocks. The risk is low. If it occurs during pre-check: add `assert len(unique_buckets) == 3`
to immediately surface the issue rather than silently producing a misleading result.

---

## Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | C5/C6 flaky → gating Phase 1 | Phase 0 decision tree (fix/weaken/remove) |
| 2 | F6: LLM assigns orphan a forward parent | Strengthen hierarchy prompt Rule 0; require 3/3 |
| 3 | C10: Claude normalises accents away | Permissive assertion (1 of 3 must survive) |
| 4 | G2: columns collapse into < 3 buckets | Wider column separation fallback |
| 5 | D7: null array fields trigger schema violation | Fix extraction prompt; this is a bug to discover |
| 6 | C12: content silently dropped | Assertion catches it (distinct fragment check) |

---

## Determinism pre-checks (required before committing each phase)

| Phase | Tests requiring 3/3 |
|---|---|
| 1 | F6 |
| 2 | H2, D7, C10, C12 |
| 3 | G2 |

Phase 1 coordinate check and page-bleeding check are deterministic by construction
(pure boolean assertions on extraction output) — no separate pre-check needed beyond
confirming the modified tests still pass.

---

## Done condition

- Phase 0: C5/C6 each pass 5/5, OR fixture is corrected and passes 3/3, OR test removed.
- Phase 1: coordinate check fires on C1 (manual verify by running C1); E1 page-bleeding
  fires if contaminated; F6 passes 3/3 and joins the suite.
- Phase 2: H2, D7, C10, C12 each pass 3/3 and full suite passes.
- Phase 3: G2 passes 3/3 and full suite passes.
- Final suite: 31 → 37 tests (31 + F6 + H2 + D7 + C10 + C12 + G2 = 37).
  C5/C6 stability check adds no new tests — it only determines whether the existing
  two tests remain in the suite or are fixed/removed.
- `make lint` clean throughout.

---

## Files that will change

| File | Change | Phase |
|---|---|---|
| `tests/integration/_compare.py` | Add `assert_valid_bbox_fields` helper | 1 |
| `tests/integration/test_synthetic_grp_c.py` | Add coord check to C1; add C10 + C12 tests | 1 + 2 |
| `tests/integration/test_synthetic_grp_e.py` | Add page-bleeding assertion to E1 | 1 |
| `tests/fixtures/generators/grp_f_hierarchy.py` | Add `F6_BLOCKS` | 1 |
| `tests/integration/test_synthetic_grp_f.py` | Add F6 test; import F6_BLOCKS | 1 |
| `tests/fixtures/generators/grp_h_edge.py` | Add `_make_h2_tiny_text()` + include in `generate()` | 2 |
| `tests/integration/test_synthetic_grp_h.py` | Add H2 test | 2 |
| `tests/fixtures/generators/grp_d_metadata.py` | Add `_make_d7_no_metadata()` + include in `generate()` | 2 |
| `tests/integration/test_synthetic_grp_d.py` | Add D7 test; check `_run_d_test` signature | 2 |
| `tests/fixtures/generators/grp_c_blocktypes.py` | Add `_make_c10_unicode()` + `_make_c12_emphasis()` + include in `generate()` | 2 |
| `tests/fixtures/generators/grp_g_layout.py` | Add `_make_g2_three_column()` + golden + include in `generate()` | 3 |
| `tests/integration/test_synthetic_grp_g.py` | Add G2 test | 3 |
| `tests/fixtures/manifest.json` | Updated automatically by `generate()` | 2 + 3 |
