# Synthetic PDF Test Fixtures — Plan

_Created: 2026-06-02 17:00_
_Updated: 2026-06-02 17:30 · v2 — coordinate calibration, block-matching strategy, compare helper spec_
_Updated: 2026-06-02 18:00 · v3 — full redesign: replace linear levels with concern-separated groups after code review_

---

## Goal

Build a self-contained, deterministic test corpus of synthetic PDF documents that lets
us evaluate PDFScout's pipeline end-to-end — from classification through extraction to
hierarchy assignment — with full ground-truth control.

The corpus is ordered by structural complexity so that failures reveal exactly which
capability broke, without noise from real-world document quirks.

---

## Why the original single-scale approach was wrong

After reading all source files, the original "9 levels of increasing complexity" design
has a fundamental flaw: **each level conflates multiple pipeline concerns**. Level 4
(Invoice) tested the classifier, the invoice schema selection, table_data metadata
population, and the burst phase simultaneously. A failure at that level could originate
in any of those four components.

A failing test should point at ONE broken capability. The new design enforces that by
separating tests on **three independent axes**:

| Axis | Question answered |
|---|---|
| **Which node?** | classifier / pioneer_parser / burst_worker / hierarchy_node |
| **Which schema feature?** | block type / metadata subfield / hierarchy rule |
| **How complex is the PDF?** | 1 block / multi-block / multi-column / multi-page |

Complexity now increases **within each group**, not across groups. The result is a set
of narrow-focus tests where `group B` failing always means "classifier broke", `group C`
failing always means "extraction/block-type recognition broke", and so on.

---

## What the existing unit tests already cover (do NOT duplicate)

Reading the test suite reveals complete mock-based coverage for:

| Behavior | Existing test |
|---|---|
| Pioneer retry loop (1→3 retries, degradation warning) | `test_graph_pipeline.py` |
| `pioneer_validation_route` routing (empty blocks, wrong page, valid, invalid, max retry) | `test_edges.py` |
| `geometric_pre_sorter` (page sort, ymin sort, column bucket sort) | `test_hierarchy_node.py` |
| Hierarchy node: dedup, single-block skip, orphan warning, no-tool-use error | `test_hierarchy_node.py` |
| Worker node: tool-use parsing, no-tool-use error, error injection in prompt | `test_worker_node.py` |
| Classifier: invoice, sci, unknown fallback, whitespace strip | `test_classifier_node.py` |

**The retry loop cannot be exercised by synthetic PDFs.** There is no clean, valid PDF
that reliably makes Claude produce a JSON schema violation. The retry loop is deterministically
exercised by mocked API responses and is already fully covered. **Do not add a synthetic
PDF fixture for it.**

A further code-derived insight: `classifier_node` **never directly returns `baseline_core`**.
It returns the model's response only if it is in `SUPPORTED_DOC_TYPES`
(`{"invoice", "scientific_paper"}`); otherwise it falls through to `FALLBACK_DOC_TYPE`.
Group B therefore tests the fallback path, not a direct classification.

---

## Design principles

1. **Ground truth at generation time.** Every fixture PDF is produced by a reportlab
   generator script that also emits a `golden.json`. Golden files are committed alongside
   the PDFs so tests run offline.

2. **One concern per test.** Each test group targets exactly one pipeline node and one
   schema feature. Within a group, PDFs increase in complexity, but the tested concern
   stays fixed.

3. **Pytest marks for selective runs.** Every test is tagged with its group
   (`@pytest.mark.grp_b`, `@pytest.mark.grp_c`, …) so any group can be run in isolation.
   All synthetic tests also carry `@pytest.mark.e2e` to exclude them from the default
   `make test` run.

4. **Full end-to-end within each test.** Tests invoke the pipeline via `build_app()`,
   collect the JSON output, and diff it against the golden file field by field.

---

## Directory layout

```
tests/
  fixtures/
    generators/
      __init__.py
      _common.py             # shared reportlab helpers (A4 canvas, text, table, figure)
      grp_a_native.py        # A1–A2: valid/encrypted/zero-page PDFs
      grp_b_classifier.py    # B1–B3: invoice signals, sci signals, plain fallback
      grp_c_blocktypes.py    # C1–C7: one block type per generator
      grp_d_metadata.py      # D1–D5: one metadata subfield per generator
      grp_e_multipage.py     # E1–E3: 2-page, 5-page, continuation
      grp_f_hierarchy.py     # F1–F4: nesting patterns
      grp_g_layout.py        # G1–G2: two-column, dense page
      grp_h_edge.py          # H1–H2: empty page, long paragraph
      generate_all.py        # CLI: python -m tests.fixtures.generators.generate_all
    pdfs/                    # committed, pre-generated
      grp_a_valid_1page.pdf
      grp_b_invoice.pdf
      grp_c_paragraph.pdf
      grp_c_table.pdf
      ...
    golden/                  # committed, expected JSON output
      grp_a_valid_1page.json
      grp_b_invoice.json
      grp_c_paragraph.json
      grp_c_table.json
      ...
  integration/
    test_synthetic_grp_a.py  # native extraction
    test_synthetic_grp_b.py  # classifier
    test_synthetic_grp_c.py  # block-type extraction
    test_synthetic_grp_d.py  # metadata schemas
    test_synthetic_grp_e.py  # multi-page burst
    test_synthetic_grp_f.py  # hierarchy assignment
    test_synthetic_grp_g.py  # layout / reading order
    test_synthetic_grp_h.py  # edge cases
    _compare.py              # shared diff/assertion helpers
```

A `make fixtures` Makefile target regenerates all PDFs and golden files.
Individual groups can be regenerated with `make fixtures GRP=c`.

---

## Coordinate system and bbox calibration

The extraction prompt tells Claude: `"Coordinates must follow [ymin, xmin, ymax, xmax] order."` Claude
produces **integers** in whatever coordinate space it uses internally when reading the PDF natively.
That space is not publicly documented — it could be typographic points (1 pt = 1/72 in), PDF user units,
or pixel coordinates at an implicit render DPI.

reportlab writes PDFs in standard PDF units (points), with origin at **bottom-left** (y increases
upward). Claude reads the page top-down (y increases downward). The conversion formula is:

```
ymin_claude = page_height_pts − (y_rl + height_rl)
ymax_claude = page_height_pts − y_rl
xmin_claude = x_rl
xmax_claude = x_rl + width_rl
```

**However**, if Claude renders to pixels before processing, the values would be scaled by
`(DPI / 72)`. This is unknown until we run the pipeline on a known document.

### Calibration run (Phase 0)

Before generating golden files for any level, run Level 1 (single paragraph, known position) through
the pipeline and inspect the returned `coordinates`. Compare against the expected point values:

- If `coordinates ≈ points_values` → coordinate space is PDF points; golden files store converted
  point values.
- If `coordinates ≈ points_values × k` for some `k` (e.g. 2.0 for 144 DPI, 1.389 for 100 DPI) →
  golden files store scaled values derived by multiplying the reportlab point coords by `k`.

The calibration result is stored in `tests/fixtures/generators/_common.py` as a constant
(`COORD_SCALE = <k>`) used by all golden file generators.

Until the calibration run is done, Phase 1 integration tests skip bbox assertions entirely
and only assert `document_type`, `blocks[*].type`, `blocks[*].text`, and block count.

---

## Comparison contract

Each golden file contains the subset of fields that are **deterministic given the
synthetic input**:

| Field | Compared | Notes |
|---|---|---|
| `document_type` | exact string | Core classifier signal |
| `blocks[*].type` | exact enum | Extraction quality |
| `blocks[*].text` | exact string | Extraction quality |
| `blocks[*].is_continued` | exact bool | Continuation detection |
| `blocks[*].metadata` | field-by-field | Schema-specific (table_data, bibliographic, …) |
| `blocks[*].bbox` | tolerance ±5 % of page dimension | See note below |
| `blocks[*].block_id` | **not compared** | Non-deterministic, model-assigned |
| `blocks[*].parent_id` | structural check | Not exact ID, see §hierarchy assertions |

### Bbox note (phased)

Claude estimates bounding boxes by visual reasoning over the rendered PDF page — it
does not parse the coordinate stream from the file. Even on clean synthetic input, the
returned integers are model estimates that vary run-to-run.

**Phase 1 (pre-calibration):** no bbox assertions. Tests only check `document_type`,
`blocks[*].type`, `blocks[*].text`, and `len(blocks)`.

**Phase 2 (post-calibration):** after the Phase 0 calibration run (see §Coordinate
system), golden files store the expected coordinates in Claude's coordinate space.
Tests assert each returned coordinate is within **±5 % of the corresponding page
dimension** (≈ ±36 pt on A4 at 792 pt height). This catches gross mis-location while
tolerating normal model variance.

**Why not ±1 px:** bbox values are model-generated, not parser-derived. ±1 px
assertions would be permanently flaky on non-deterministic inputs.

If calibration shows Claude is consistently accurate (variance < 5 pt on simple docs),
the tolerance can be tightened in a follow-up iteration.

### Block-matching strategy

The pipeline's `geometric_pre_sorter` applies a deterministic sort on the output:
**page ASC → column-bucket ASC (bucket width = `COLUMN_BUCKET_PX = 50`) → ymin ASC**.
This means the order of blocks in `structured_payload` is fully determined by their
bboxes — it is not the insertion order from the model.

For **groups A–F and H** (single-column content), the sort order is stable
and blocks can be matched positionally: `output[i]` is compared to `golden[i]`.

For **group G1** (two-column layout), the sort interleaves columns inside the same
column-bucket boundaries. The test uses set-based matching: for each expected text
string, assert that *some* block in the output contains it. Positional order is
verified separately (left-column blocks must all appear before right-column blocks in
the sorted output).

For **H1** (empty page), the output may have zero blocks; the test asserts
`len(blocks) <= 2` and no exception. No positional matching is attempted.

### `_compare.py` helper spec

```python
def assert_blocks_match(
    expected: list[dict],
    actual: list[dict],
    *,
    check_bbox: bool = False,
    bbox_tolerance_pct: float = 0.05,
    normalize_text: bool = False,
) -> None:
    """
    Raises AssertionError with a diff on the first mismatch.
    - Matches blocks positionally by default.
    - check_bbox=False until Phase 2 calibration is complete.
    - normalize_text=True strips extra whitespace and lowercases before comparing.
    """

def assert_hierarchy_structure(blocks: list[dict], rules: list[HierarchyRule]) -> None:
    """
    Checks parent-child relationships without pinning exact block_id values.
    HierarchyRule: (child_type: str, expected_parent_type: str | None)
    """

def assert_table_data(block: dict, expected_rows: int, expected_cols: int,
                      header_row_count: int = 1) -> None:
    """Validates metadata.table_data cell count, dimensions, and header flags."""
```

### Hierarchy assertions

`parent_id` values are model-assigned UUIDs and cannot be golden-pinned. Instead we
assert structural relationships:

- Every `paragraph` block whose nearest preceding block is a `heading` has
  `parent_id` pointing to some block whose `type == "heading"`.
- Every `list_item` has a `parent_id` pointing to a block of type
  `"heading"` or `"paragraph"`.
- Top-level blocks (title, standalone paragraphs) have `parent_id == null`.

---

## Golden file format

Each golden file in `tests/fixtures/golden/` is a JSON document with two top-level keys:

```json
{
  "meta": {
    "generator": "level_01_minimal",
    "page_size_pts": [595.28, 841.89],
    "coord_scale": 1.0,
    "created": "2026-06-02"
  },
  "expected": {
    "document_type": "baseline_core",
    "block_count": 1,
    "blocks": [
      {
        "type": "paragraph",
        "text": "Hello, synthetic world.",
        "is_continued": false,
        "bbox": {
          "page_number": 1,
          "coordinates": [380, 70, 410, 525]
        },
        "metadata": {}
      }
    ]
  }
}
```

- `meta.coord_scale` is filled in after Phase 0 calibration; set to `null` until then.
- `expected.blocks` omits `block_id` and `parent_id` — neither is pinned exactly.
- For levels that skip bbox (`check_bbox=False`), the `coordinates` key may be omitted.

The generator scripts write this file at generation time, so the ground truth is
tightly coupled to what was actually placed on the page.

---

## Test groups

Groups are ordered by concern, not by complexity. Within each group, tests are numbered
and increase in complexity. All tests in a group share a `@pytest.mark.grp_X` marker.

---

### Group A — Native extraction (no LLM, no API key required)

Node under test: `native_extractor_node` (pypdf only).

| ID | PDF | Assertions |
|---|---|---|
| A1 | Valid 1-page PDF | `total_pages == 1`; `pdf_hash` is a 64-char hex string |
| A2 | Valid 10-page PDF | `total_pages == 10` |
| A3 | Encrypted PDF | `ValueError` raised immediately; pipeline does not reach classifier |

> A3 uses a programmatically encrypted PDF (pypdf can write them); no API call is made.

---

### Group B — Classifier accuracy (1 Claude call per test)

Node under test: `classifier_node`.
Each PDF contains strong, unambiguous visual signals for exactly one document type.
All other pipeline nodes are mocked.

| ID | PDF content | Expected `document_type` |
|---|---|---|
| B1 | Company header, "INVOICE #001", billing table, line items | `invoice` |
| B2 | Paper title in large font, two authors, "Abstract" heading, body text, "DOI:" line | `scientific_paper` |
| B3 | Plain short paragraph, no formatting signals | `baseline_core` (fallback path: model returns unknown token, pipeline uses `FALLBACK_DOC_TYPE`) |

**Why B3 matters:** the only code path that produces `baseline_core` is the fallback
branch in `classifier_node`. This test confirms the fallback activates correctly when
the model's response is not in `SUPPORTED_DOC_TYPES`. The PDF content is deliberately
ambiguous to maximise the chance the model responds with a non-invoice, non-sci-paper
token; if it does return one of the two supported types, the test still passes (the
classifier worked; it just classified it differently than expected, which is acceptable
for an ambiguous doc). The important assertion is that `document_type` is always a valid
string and never causes a downstream crash.

---

### Group C — Block-type extraction (1–2 Claude calls per test)

Node under test: `window_parser_node` (pioneer page).
One PDF per block type. Each PDF contains ONLY the target block type to maximise
extraction signal and prevent interference.

| ID | PDF content | Expected block type(s) | Key assertions |
|---|---|---|---|
| C1 | One short paragraph | `paragraph` | `len(blocks) == 1`; exact text |
| C2 | One large title line | `title` | `len(blocks) == 1`; exact text |
| C3 | One bold heading | `heading` | `len(blocks) == 1`; exact text |
| C4 | Unordered list (3 items) | `list_item` ×3 | `len(blocks) == 3`; each item text |
| C5 | Small text at page bottom, separated from body | `footnote` | `len(blocks) >= 1`; footnote block present; bbox in bottom 20 % of page |
| C6 | Short text in left margin, narrow column | `margin_element` | Block present; bbox xmin < 10 % of page width |
| C7 | 3×4 data table with header row | `table` | `len(blocks) == 1`; `metadata.table_data.total_rows==3`, `total_cols==4`; header cells flagged |
| C8 | Grey rectangle (figure) + caption text below it | `figure` + `paragraph` | Figure block present; caption block present |

> For C5 and C6, bboxes are used positionally to confirm the model placed the block in the
> right region, not just gave it the right type.

---

### Group D — Schema-specific metadata (1–2 Claude calls per test)

Node under test: `window_parser_node` + schema validation in `pioneer_validation_route`.
One PDF per metadata subfield. Each PDF contains only the content needed to populate that subfield.
Classifier is mocked to return the appropriate doc type so the correct schema is loaded.

| ID | Doc type mocked | PDF content | Metadata subfield | Key assertions |
|---|---|---|---|---|
| D1 | `invoice` | 4-col line-items table (description, qty, price, total) | `table_data` | `cells` contains all generated values; `is_header` set on row 0 |
| D2 | `scientific_paper` | Title + 3 authors + abstract paragraph | `bibliographic` | `authors` list matches; `abstract` text matches; `title` text matches |
| D3 | `scientific_paper` | "2. Methodology" heading + 2 body paragraphs | `section` | `section_number == "2"`; `section_title == "Methodology"` |
| D4 | `scientific_paper` | 3 reference entries (numbered, author-year format) | `reference` | Each reference block has `year`, `title`, `authors` populated |
| D5 | `scientific_paper` | "Figure 1: Caption text" below a grey rectangle | `figure_table` | `label == "Figure 1"`; `caption` matches generated string |

---

### Group E — Multi-page pipeline / burst + merge (N Claude calls per test)

Nodes under test: `burst_dispatcher_node`, `window_parser_node` (pages 2–N), `merge_flat_blocks` reducer.
Hierarchy node is mocked to return trivial relations.

| ID | PDF | Assertions |
|---|---|---|
| E1 | 2-page doc (1 paragraph per page) | Blocks from both pages present (`bbox.page_number` ∈ {1, 2}); no duplicate `block_id` |
| E2 | 5-page doc (1 paragraph per page) | Blocks from all 5 pages present; `len(blocks) == 5` |
| E3 | 2-page doc: paragraph starts on page 1, continues on page 2 (text split mid-sentence at page boundary) | Page 1 block has `is_continued == true`; a continuation block exists on page 2 |

> E3 is the only fixture that specifically tests `is_continued`. The PDF must make the
> continuation unambiguous: the sentence on page 1 ends mid-word or with an em dash.

---

### Group F — Hierarchy assignment quality (pipeline runs fully, including hierarchy LLM call)

Node under test: `layout_hierarchy_agent_node`.
Classifier is mocked to return `baseline_core`. PDFs increase in nesting depth.

| ID | PDF content | Expected hierarchy | Key assertions |
|---|---|---|---|
| F1 | Title only | Root node | `parent_id == null` |
| F2 | Heading + 2 paragraphs | Paragraphs are children of heading | Each paragraph's `parent_id` → block of `type == "heading"` |
| F3 | Title → Heading → Paragraph (3-level) | Three levels of nesting | title at root; heading is child of title; paragraph is child of heading |
| F4 | Figure + caption paragraph | Caption is child of figure | Caption's `parent_id` → block of `type == "figure"` |
| F5 | 2 headings, each with 2 paragraphs | Each paragraph under its nearest preceding heading | Paragraphs after heading-1 point to heading-1's `block_id`; paragraphs after heading-2 point to heading-2's `block_id` |

> Assertions use `assert_hierarchy_structure()` which checks type-of-parent, not
> exact `block_id` values (model-generated, non-deterministic).

---

### Group G — Layout / reading order (1–2 Claude calls per test)

Nodes under test: `window_parser_node` + `geometric_pre_sorter` (the sort happens after
extraction, so the PDF must produce blocks with predictable xmin values).

| ID | PDF content | Assertions |
|---|---|---|
| G1 | 2-column layout (A4 split at x=297 pt): left column has "L1…L2…L3", right has "R1…R2…R3" | All L-prefixed texts appear before all R-prefixed texts in `structured_payload`; no text bleed between columns |
| G2 | Dense single-column page with 10 short paragraphs | `len(blocks) == 10`; paragraphs in top-to-bottom order (ymin monotonically increasing) |

> G1 exercises the `geometric_pre_sorter`'s column-bucket logic. With `COLUMN_BUCKET_PX=50`,
> left-column blocks (xmin ≈ 36 pt → bucket 0) sort before right-column blocks
> (xmin ≈ 315 pt → bucket 6). If this test fails, check whether the bucket width needs
> adjustment for the chosen column layout.

---

### Group H — Edge cases / graceful degradation (1–2 Claude calls per test)

| ID | PDF content | Assertions |
|---|---|---|
| H1 | 1 page with no text, no objects (blank white page) | Pipeline completes without exception; `blocks` is `[]` or length ≤ 2 (model may hallucinate a block — assert no crash) |
| H2 | 1 page, one 500-word paragraph filling the full page | `len(blocks) == 1`; block type `paragraph`; text contains the first and last sentences of the generated paragraph |

---

## Phased delivery

### Phase 0 — Calibration (prerequisite, no tests written yet)

- Implement `_common.py` and the C1 (single paragraph) generator only
- Generate `grp_c_paragraph.pdf` and run it through the full pipeline with no mocks
- Inspect returned `coordinates`; derive `COORD_SCALE` and document it in `_common.py`
- If variance is > ±5 % of page dimension even on a trivial doc, skip bbox assertions
  entirely and add a `# COORD_SCALE: not viable` comment in `_common.py`

### Phase 1 — Foundation: Groups A, B, C (native extraction + classifier + block types)

- `tests/fixtures/` directory structure + `generate_all.py` CLI
- `_common.py` reportlab helpers (canvas, drawString, table helper, figure helper)
- Generators and golden files for A1–A3, B1–B3, C1–C8
- `tests/integration/_compare.py` with `assert_blocks_match` and `assert_table_data`
- Integration tests for groups A, B, C
- `make fixtures` target; `make test-e2e` shortcut

### Phase 2 — Schema metadata: Group D

- Generators and golden files for D1–D5 (one per metadata subfield)
- `assert_blocks_match` extended with metadata field-level checking
- Integration tests for group D

### Phase 3 — Pipeline behavior: Groups E and F

- Multi-page generators (E1–E3) including the `is_continued` fixture (E3)
- Hierarchy generators (F1–F5)
- `assert_hierarchy_structure` helper added to `_compare.py`
- Integration tests for groups E and F

### Phase 4 — Layout and edge cases: Groups G and H

- Two-column generator (G1), dense page (G2)
- Edge-case generators (H1–H2)
- Integration tests for groups G and H
- `make test-e2e GRP=g` selective group run documented in README

---

## Open questions / risks

1. **Bbox variance.** Phase 0 calibration will determine whether bbox assertions are
   viable at all. If variance is > ±5 % even on trivial docs, disable bbox assertions
   globally and assert only `type`, `text`, and `len(blocks)`. This does not reduce the
   test value significantly — block position is less important than block content.

2. **Text paraphrasing.** Claude may lightly rephrase extracted text (reformat whitespace,
   normalize quotes). If exact text matching causes flakiness, switch to normalized
   comparison in `_compare.py` (`normalize_text=True`). Detect this early in Phase 1
   by running C1 and C2 multiple times and checking for consistency.

3. **B3 classifier fallback reliability.** The fallback path is exercised when the
   model returns a token not in `SUPPORTED_DOC_TYPES`. A completely plain PDF might
   still be classified as `invoice` or `scientific_paper` by the model. If B3 is
   flaky, change the assertion: instead of asserting `document_type == "baseline_core"`,
   assert only that `document_type` is a non-empty string and `extraction_warnings` is empty.

4. **E3 continuation detection.** The `is_continued` flag is not explicitly prompted for
   in the extraction instructions. Claude may not reliably set it unless the page break
   is visually unambiguous. If E3 is flaky, consider adding explicit continuation
   instructions to the extraction prompt (a prompt change, not a test change).

5. **F hierarchy quality.** Hierarchy assignment depends on the hierarchy node's LLM
   call. The model follows documented rules (items after a heading → child of heading;
   continued blocks → child relationship), but for complex F4/F5 patterns, it may
   produce unexpected structures. If F4/F5 are flaky, use looser assertions (e.g.,
   figure caption has *some* parent_id, not necessarily the figure block).

6. **Cost.** Total API calls across all groups: ~30 Claude calls (A: 0, B: 3, C: 8,
   D: 5, E: 8, F: 7, G: 2, H: 2). At ~$0.01–$0.05 per call, the full suite costs
   < $2 per run. Nightly CI is appropriate; exclude from per-commit runs via
   `@pytest.mark.e2e`.

7. **Golden file staleness.** Any change to extraction prompts or schemas requires
   `make fixtures` regeneration. The designated review workflow is
   `make fixtures && git diff tests/fixtures/golden/` — a golden diff that looks
   semantically reasonable means the prompt change is safe.

---

## Running the test suite

```bash
# Regenerate all fixture PDFs and golden files from scratch
make fixtures

# Regenerate only one group
make fixtures GRP=c

# Run only the synthetic e2e tests (requires ANTHROPIC_API_KEY)
pytest tests/integration/test_synthetic_*.py -m e2e -v

# Run only one group
pytest tests/integration/test_synthetic_grp_c.py -m "e2e and grp_c" -v

# Run everything including unit tests (no API key needed for unit tests)
make test
```

All synthetic integration tests carry two markers: `@pytest.mark.e2e` (excludes from
default `make test`) and `@pytest.mark.grp_X` (enables single-group runs).

---

## Iteration log

_v1 — 2026-06-02 17:00 — initial draft_
_v2 — 2026-06-02 17:30 — added coordinate calibration section, Phase 0, block-matching strategy, `_compare.py` spec, golden file format, phased bbox assertions_
_v3 — 2026-06-02 18:00 — full redesign after reading all source files: replaced single linear scale with 8 concern-separated groups (A–H); documented what existing unit tests already cover; noted retry loop cannot be triggered by synthetic PDFs; corrected `baseline_core` fallback mechanic; updated directory layout, phased delivery, open questions_
