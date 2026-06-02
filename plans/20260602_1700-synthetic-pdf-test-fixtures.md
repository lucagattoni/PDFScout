# Synthetic PDF Test Fixtures — Plan

_Created: 2026-06-02 17:00_
_Updated: 2026-06-02 17:30 · v2 — coordinate calibration, block-matching strategy, compare helper spec_

---

## Goal

Build a self-contained, deterministic test corpus of synthetic PDF documents that lets
us evaluate PDFScout's pipeline end-to-end — from classification through extraction to
hierarchy assignment — with full ground-truth control.

The corpus is ordered by structural complexity so that failures reveal exactly which
capability broke, without noise from real-world document quirks.

---

## Design principles

1. **Ground truth at generation time.** Every fixture PDF is produced by a reportlab
   generator script that also emits a `golden.json` — a JSON file containing the exact
   block list we expect the pipeline to return. Golden files are committed alongside
   the PDFs so tests run offline.

2. **Graduated complexity.** Levels 1–9 add exactly one new structural challenge each.
   A failing test at level N implies the capability introduced at N is broken; all lower
   levels still pass.

3. **Classifier coverage.** At least one level exercises each document type
   (`baseline_core`, `invoice`, `scientific_paper`).

4. **Full end-to-end.** Tests invoke `main.py` (or the equivalent `run_pipeline` entry
   point) with the fixture PDF, collect the JSON output, and diff it against the golden
   file field by field.

---

## Directory layout

```
tests/
  fixtures/
    generators/
      __init__.py
      _common.py             # shared reportlab helpers (page size, fonts, grid)
      level_01_minimal.py
      level_02_multiblock.py
      level_03_blocktypes.py
      level_04_invoice.py
      level_05_sci_single.py
      level_06_sci_multipage.py
      level_07_twocolumn.py
      level_08_tables_figures.py
      level_09_edge_cases.py
      generate_all.py        # CLI: python -m tests.fixtures.generators.generate_all
    pdfs/                    # committed, pre-generated
      level_01_minimal.pdf
      ...
    golden/                  # committed, expected JSON output
      level_01_minimal.json
      ...
  integration/
    test_synthetic_L01.py
    test_synthetic_L02.py
    ...
    test_synthetic_L09.py
    _compare.py              # shared diff/assertion helpers
```

A `make fixtures` Makefile target regenerates all PDFs and golden files from scratch
(used when generators change, not on every test run).

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

For **Levels 1–6** (single-column or well-separated columns), the sort order is stable
and blocks can be matched positionally: `output[i]` is compared to `golden[i]`.

For **Level 7** (two-column layout), the sort interleaves columns inside the same
column-bucket boundaries. The test uses set-based matching: for each expected text
string, assert that *some* block in the output contains it. Positional order is
verified separately (left-column blocks must all appear before right-column blocks in
the sorted output).

For **Level 9a** (empty page), the output may have zero blocks; the test asserts
`len(blocks) == 0` and no exception.

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

## Complexity levels

### Level 1 — Minimal single-page

**What the PDF contains:** one A4 page, one short paragraph in the centre.

**What it tests:**
- Pipeline runs end-to-end on the simplest possible input
- Classifier returns `baseline_core`
- Pioneer parser extracts exactly one block of type `paragraph`
- No burst phase (single-page doc)

**Assertions:**
- `document_type == "baseline_core"`
- `len(blocks) == 1`
- `blocks[0].type == "paragraph"`, `blocks[0].text == <exact string>`
- Bbox within ±5 % tolerance

---

### Level 2 — Single-page, multi-block, single-column

**What the PDF contains:** 1 page — title + three short paragraphs stacked vertically,
generous spacing so blocks are well-separated.

**What it tests:**
- Multiple blocks extracted in correct reading order
- Block type detection: `title` vs `paragraph`

**Assertions:**
- 4 blocks in order: `[title, paragraph, paragraph, paragraph]`
- Each block's text matches the generated string
- Bboxes ordered top-to-bottom (y_min monotonically increasing)

---

### Level 3 — All baseline block types

**What the PDF contains:** 1–2 pages using every block type in `baseline_core`:
`title`, `heading`, `paragraph`, `list_item` (×3), `footnote`, `margin_element`.

**What it tests:**
- Full type vocabulary recognised
- `footnote` and `margin_element` placed at correct positions (bottom and margin)

**Assertions:**
- At least one block of each type present
- `footnote` bbox is in the bottom 20 % of its page
- `margin_element` bbox left edge < 10 % of page width or right edge > 90 %

---

### Level 4 — Invoice (classifier gate)

**What the PDF contains:** a 2-page invoice:
- Page 1: company logo area (paragraph/title), billing address table (2-col),
  line-items table (4-col: description, qty, unit price, total)
- Page 2: subtotal/tax/total rows, payment terms paragraph, footer

**What it tests:**
- Classifier identifies `invoice` (not `baseline_core`)
- `table_data` metadata populated correctly for both tables
- Burst phase runs for page 2

**Assertions:**
- `document_type == "invoice"`
- Line-items table: `total_rows`, `total_cols`, all cells present in `table_data`
- Header cells flagged `is_header == true`
- No `ValidationError` in pipeline warnings

---

### Level 5 — Scientific paper, single page

**What the PDF contains:** 1 page formatted like an academic paper front page:
title, authors list, abstract heading + abstract paragraph, two keywords.

**What it tests:**
- Classifier identifies `scientific_paper`
- `bibliographic` metadata block populated (title, authors, abstract)
- Schema validation passes on pioneer page

**Assertions:**
- `document_type == "scientific_paper"`
- One block with `metadata.bibliographic.authors` containing all generated author strings
- One block with `metadata.bibliographic.abstract` matching generated abstract text

---

### Level 6 — Scientific paper, multi-page (burst phase)

**What the PDF contains:** 5 pages — cover (title + abstract), three content sections
(heading + paragraphs each), references page.

**What it tests:**
- Burst dispatcher emits `Send` for pages 2–5
- Merge (`merge_flat_blocks`) combines all pages without duplication
- Cross-page hierarchy assigned by `hierarchy_node`
- `metadata.section` populated for each section block

**Assertions:**
- Blocks from all 5 pages present (check `bbox.page_number`)
- No duplicate `block_id` values
- Section headings have `metadata.section.section_title` matching generated titles
- Paragraphs under each heading share `parent_id` pointing to that heading

---

### Level 7 — Two-column layout

**What the PDF contains:** 1 page in two-column newspaper layout (standard academic
style): left column has heading + 2 paragraphs; right column has heading + 2 paragraphs.

**What it tests:**
- Reading order follows column flow (left column fully before right column)
- Multi-column blocks don't bleed into each other

**Assertions:**
- Blocks from left column appear before blocks from right column in `blocks` array
- No text from right column appears in a left-column block's `text` field (check
  against known generated strings)

---

### Level 8 — Tables and figures

**What the PDF contains:** 1 page with:
- A data table (3×4, with header row)
- A grey rectangle standing in as a figure, with a caption below it

**What it tests:**
- `table` block type with full `table_data` metadata
- `figure` block type detected
- Caption associated with figure (hierarchy: figure → caption `list_item`/`paragraph`)

**Assertions:**
- `table` block present with `metadata.table_data.total_rows == 3`,
  `total_cols == 4`, header row flagged
- `figure` block present
- Figure caption block has `parent_id` pointing to the figure block

---

### Level 9 — Edge cases

Three lightweight PDFs in a single level, each targeting a graceful-degradation path:

| Sub-case | PDF content | Asserts |
|---|---|---|
| `9a_empty_page` | 1 page, no text, no objects | Pipeline completes; `blocks` may be `[]`; no exception raised |
| `9b_long_single_block` | 1 page, one paragraph filling the full page (500 words) | 1 block of type `paragraph`; `is_continued` tracking works |
| `9c_continuation` | 2 pages, one paragraph split mid-sentence at page boundary | Block on page 1 has `is_continued == true`; continuation block on page 2 exists |

---

## Phased delivery

### Phase 0 — Calibration (prerequisite)

- Implement `_common.py` and the Level 1 generator only
- Generate `level_01_minimal.pdf` and run it through the full pipeline
- Inspect returned `coordinates`; derive `COORD_SCALE` and the coordinate-system note
- Document findings in `tests/fixtures/generators/_common.py` as constants
- If Claude's bbox accuracy is > ±5 % variance on this trivial document, re-evaluate
  whether bbox assertions add value at all

### Phase 1 — Infrastructure + Levels 1–3 (baseline)

- Set up `tests/fixtures/` directory structure
- Implement `_common.py` reportlab helpers (A4 canvas, text block, table helper)
- Implement `generate_all.py` CLI
- Generators and golden files for Levels 1–3
- `tests/integration/_compare.py` comparison helpers
- Integration tests for Levels 1–3
- `make fixtures` Makefile target

### Phase 2 — Classifier coverage: Levels 4–5

- Invoice and scientific-paper generators
- Golden file format extended with `metadata` assertions
- Integration tests for Levels 4–5

### Phase 3 — Multi-page and layout: Levels 6–8

- Multi-page generator, two-column generator, figure/table generator
- Hierarchy assertion helpers
- Integration tests for Levels 6–8

### Phase 4 — Edge cases: Level 9

- Three sub-case generators
- Graceful-degradation assertions
- `make test-synthetic` shortcut that runs only synthetic fixture tests

---

## Open questions / risks

1. **Bbox variance is higher than ±5 %.** On complex layouts (two-column, tables),
   Claude's visual bbox estimates may deviate more. If flakiness appears in Levels 7–8,
   consider skipping bbox assertions for those levels and only asserting text + type.

2. **Classifier prompt sensitivity.** The classifier prompt is not under test control;
   if it changes, Levels 4–5 may break without a code change. Consider pinning the
   model version in the test configuration.

3. **Golden file staleness.** When the pipeline prompt changes (e.g. new extraction
   instructions), golden files must be regenerated. A `make fixtures` run + `git diff`
   review is the designated workflow.

4. **Cost.** Each integration test invokes Claude 1–5 times. Running all 9 levels in CI
   on every push is expensive. Recommend a `@pytest.mark.e2e` tag so the synthetic
   suite runs nightly or on demand, not on every commit.

5. **Determinism of text extraction.** Claude may paraphrase or lightly rephrase
   extracted text even on clean synthetic input. If exact text matching proves too
   brittle, fall back to normalised string comparison (strip whitespace, lowercase).

---

## Running the test suite

```bash
# Regenerate all fixture PDFs and golden files from scratch
make fixtures

# Run only the synthetic e2e tests (requires ANTHROPIC_API_KEY)
pytest tests/integration/test_synthetic_*.py -m e2e -v

# Run everything including unit tests (no API key needed for unit tests)
make test
```

All synthetic integration tests are tagged `@pytest.mark.e2e` so they are excluded
from the default `make test` run and can be triggered explicitly or nightly in CI.

---

## Iteration log

_v1 — 2026-06-02 17:00 — initial draft_
_v2 — 2026-06-02 17:30 — added coordinate calibration section, Phase 0, block-matching strategy, `_compare.py` spec, golden file format, phased bbox assertions_
