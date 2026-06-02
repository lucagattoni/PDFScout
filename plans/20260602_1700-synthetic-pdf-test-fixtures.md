# Synthetic PDF Test Fixtures — Plan

_Created: 2026-06-02 17:00_
_Updated: 2026-06-02 17:30 · v2 — coordinate calibration, block-matching strategy, compare helper spec_
_Updated: 2026-06-02 18:00 · v3 — full redesign: replace linear levels with concern-separated groups after code review_
_Updated: 2026-06-02 18:30 · v4 — Option 2 narrow-test conclusions + full 33-point devil's advocate review_
_Updated: 2026-06-02 19:30 · v6 — narrow-test section rewritten: per-group verdict table corrected (A terminology, B mislabeled, C wrong argument, D "partially useful" → not justified, E dead E3 reference removed, F structural argument added, G sharpened, H strengthened)_

---

## Goal

Build a test corpus of synthetic PDF documents that lets us evaluate PDFScout's pipeline
from classification through extraction to hierarchy assignment, with as much input control
as a non-deterministic LLM system allows.

Failures should reveal **which capability broke** without requiring manual diagnosis.
Absolute "ground truth" is not achievable against a stochastic model — what golden files
capture is "the expected output given these specific inputs at this moment in time," not
mathematical truth.

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

1. **Expected output at generation time.** Every fixture PDF is produced by a reportlab
   generator script that also emits a `golden.json` capturing the output we expect.
   "Expected" means "consistent with what the model should produce given this input" —
   not a mathematical truth. Golden files (JSON) are committed; PDFs are not (see
   §Directory layout).

2. **One primary concern per group.** Each group targets one pipeline node. Within a
   group, PDFs increase in complexity. This doesn't mean zero interference from
   adjacent nodes — it means that if all earlier groups pass, a new failure is
   attributable to the new group's concern. This is **conditional isolation**,
   not absolute isolation (see §Narrow tests).

3. **Pytest marks for selective runs.** Every test carries `@pytest.mark.e2e` (excludes
   from `make test`) and `@pytest.mark.grp_X` (enables single-group runs).

4. **Two test tiers per group.** Most groups have an **e2e tier** (full pipeline, real
   API calls, tests integration) and Group F additionally has a **narrow tier** (direct
   function call, pre-built state, no PDF required, see §Narrow tests). Other groups do
   not benefit from narrow tests — see §Narrow tests for the analysis.

5. **Text matching is normalized by default.** `normalize_text=True` is the default in
   `_compare.py`. Tighten to exact matching only if a group's test passes normalization
   consistently across multiple runs. Starting strict and weakening later produces
   false regression cycles.

---

## Directory layout

```
tests/
  fixtures/
    generators/
      __init__.py
      _common.py                    # reportlab helpers + BBOX_ASSERTIONS_VIABLE constant
      calibration_notes.md          # Phase 0 results: COORD_SCALE, DPI finding, decision
      grp_a_native.py               # A1–A3
      grp_b_classifier.py           # B1–B2
      grp_c_blocktypes.py           # C1–C9
      grp_d_metadata.py             # D1–D5
      grp_e_multipage.py            # E1–E2
      grp_f_hierarchy.py            # F1–F5 (pre-built state; no PDF generator needed)
      grp_g_layout.py               # G1
      grp_h_edge.py                 # H1
      generate_all.py               # CLI + pytest session fixture
    pdfs/                           # .gitignore — regenerated at session start if missing
      [not tracked in git]
    golden/                         # committed — JSON, human-readable diffs
      grp_a_valid_1page.json
      grp_b_invoice.json
      grp_c_paragraph.json
      ...
  integration/
    test_synthetic_grp_a.py         # native extraction
    test_synthetic_grp_b.py         # classifier
    test_synthetic_grp_c.py         # block-type extraction
    test_synthetic_grp_d.py         # metadata schemas
    test_synthetic_grp_e.py         # multi-page burst
    test_synthetic_grp_f.py         # hierarchy (narrow: direct function calls)
    test_synthetic_grp_g.py         # layout / reading order
    test_synthetic_grp_h.py         # edge cases
    test_full_chain.py              # no mocks, all nodes real, integration chain
    _compare.py                     # assert_blocks_match, assert_table_data,
                                    # assert_hierarchy_structure, assert_nearest_heading_parent
```

`tests/fixtures/pdfs/` is in `.gitignore`. PDFs are regenerated by the pytest
`session`-scoped fixture in `generate_all.py` if the file is missing. Only generator
scripts and golden JSON files are tracked in git.

`make fixtures [GRP=x]` regenerates the specified group (or all groups) and updates
golden files. Requires adding a `fixtures` target to `Makefile` with optional `GRP`
parameter.

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

Before generating any golden files, run C1 (single paragraph, known position) through
the pioneer_parser only (mock classifier and hierarchy to save cost — only the extraction
output contains bbox data). Run it 3 times and compare returned `coordinates`:

- If `coordinates ≈ point_values` → Claude uses PDF points; `COORD_SCALE = 1.0`.
- If `coordinates ≈ point_values × k` → `COORD_SCALE = k` (store as float).
- If values vary widely across 3 runs → `BBOX_ASSERTIONS_VIABLE = False`.

A second check in Phase 1 (when D1-table and G1-twocolumn exist) verifies scale
consistency across content types. If scale differs between C1 and D1/G1:
`BBOX_ASSERTIONS_VIABLE = False`.

Store findings in `calibration_notes.md`. The constant in `_common.py` is either
`COORD_SCALE = <k>` (float, enables bbox) or `BBOX_ASSERTIONS_VIABLE = False`
(disables all bbox assertions permanently). These two constants are mutually exclusive.

---

## Comparison contract

Each golden file contains the subset of fields that are **deterministic given the
synthetic input**:

| Field | Compared | Notes |
|---|---|---|
| `document_type` | exact string | Core classifier signal |
| `blocks[*].type` | exact enum | Extraction quality |
| `blocks[*].text` | normalized string | Strip + collapse whitespace; no lowercasing |
| `blocks[*].is_continued` | **not compared** | E3 suspended; field untested |
| `blocks[*].metadata` | field-by-field, optional subfields | Schema-specific; see §Group D notes |
| `blocks[*].bbox` | ±5 % of block's own dimension (if assertions enabled post-calibration) | See note below |
| `blocks[*].block_id` | **not compared** | Non-deterministic, model-assigned |
| `blocks[*].parent_id` | structural check | Not exact ID; see §hierarchy assertions |

### Bbox note (phased)

Claude estimates bounding boxes by visual reasoning over the rendered PDF page — it
does not parse the coordinate stream from the file. Even on clean synthetic input, the
returned integers are model estimates that vary run-to-run.

**Phase 1 (pre-calibration):** no bbox assertions. Tests only check `document_type`,
`blocks[*].type`, `blocks[*].text`, and `len(blocks)`.

**Phase 2 (post-calibration):** golden files store the expected coordinates. Tests assert
each returned coordinate is within **±5 % of the block's own dimension** on each axis
(e.g., for a 20 pt tall block, ±1 pt; for a 200 pt wide block, ±10 pt). A floor of
±5 pt absolute applies for blocks smaller than 10 pt. This scales with block size and
is semantically meaningful — not a fixed page-relative band that would pass for blocks
placed anywhere in the same quadrant.

**Why not ±1 px or ±page dimension:** bbox values are model estimates. Page-relative
tolerance (e.g., ≈ 42 pt on A4) is too loose for small blocks. Pixel-exact assertions
are permanently flaky against a stochastic model.

### Block-matching strategy

The pipeline's `geometric_pre_sorter` applies a deterministic sort on the output:
**page ASC → column-bucket ASC (bucket width = `COLUMN_BUCKET_PX = 50`) → ymin ASC**.
This means the order of blocks in `structured_payload` is fully determined by their
bboxes — it is not the insertion order from the model.

For **single-column groups** (A, B, C, D, E, F, H), the geometric sort order is stable
and blocks can be matched positionally: `output[i]` is compared to `golden[i]`.

For **G1** (two-column layout), positional matching is unreliable because the sort
interleaves columns. Use set-based matching: for each expected text string, assert that
*some* block in the output contains it. Column ordering is verified separately (all
L-prefixed blocks before all R-prefixed blocks in `structured_payload`).

For **H1** (blank page), no positional matching is attempted. The test only asserts
pipeline completes without exception and `len(blocks) <= 1`.

### `_compare.py` helper spec

```python
def assert_blocks_match(
    expected: list[dict],
    actual: list[dict],
    *,
    check_bbox: bool = False,
    bbox_tolerance_pct: float = 0.05,
    normalize_text: bool = True,  # default True per Design Principle 5
) -> None:
    """
    Raises AssertionError with a diff on the first mismatch.
    - Matches blocks positionally by default.
    - check_bbox=False until Phase 2 calibration is complete.
    - normalize_text: strip + collapse whitespace, normalize quotes. Do NOT lowercase.
    - bbox_tolerance_pct applies to block's own dimension, not page dimension.
    """

def assert_hierarchy_structure(blocks: list[dict], rules: list[HierarchyRule]) -> None:
    """
    Checks parent-child relationships without pinning exact block_id values.
    HierarchyRule: (child_type: str, expected_parent_type: str | None)
    """

def assert_table_data(block: dict, expected_rows: int, expected_cols: int,
                      header_row_count: int = 1) -> None:
    """Validates metadata.table_data cell count, dimensions, and header flags."""

def assert_nearest_heading_parent(blocks: list[dict]) -> None:
    """
    For each paragraph block, asserts its parent_id points to the block_id of the
    nearest preceding heading in the sorted block list. Requires blocks to already
    be in geometric sort order (as returned by the pipeline).
    Raises AssertionError if any paragraph's parent is not its nearest heading.
    """
```

### Hierarchy assertions

`parent_id` values are model-assigned UUIDs and cannot be golden-pinned. Instead we
assert structural relationships. The following are based on the **documented rules in
the hierarchy node prompt** — assertions must not assume undocumented behavior:

**Documented rules (assert these):**
- Paragraphs/tables/list_items directly following a `heading` → `parent_id` points
  to that heading's `block_id`.
- `title` blocks → `parent_id == null`.
- Unpaired/standalone `heading` blocks → `parent_id == null`.

**Undocumented (do not assert without prompt evidence):**
- Figure-caption nesting: NOT in the hierarchy prompt. Do not assert
  `caption.parent_id → figure`. See F4 note.
- `list_item` parent rules: documented in the prompt as falling under the general
  "directly following a heading" rule. No dedicated test case currently; add F6 if
  list_item nesting needs explicit coverage.

---

## Golden file format

Each golden file in `tests/fixtures/golden/` is a JSON document with two top-level keys:

```json
{
  "meta": {
    "generator": "grp_c_paragraph",
    "page_size_pts": [595.28, 841.89],
    "coord_scale": null,
    "created": "2026-06-02"
  },
  "expected": {
    "document_type": "baseline_core",
    "blocks": [
      {
        "type": "paragraph",
        "text": "Hello, synthetic world.",
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

- `meta.coord_scale` is `null` until Phase 0 calibration; set to `false` if assertions
  are disabled, or to the numeric scale factor if enabled.
- `expected.blocks` omits `block_id`, `parent_id`, and `is_continued` (E3 suspended).
- No `block_count` field — count assertions use `len(blocks) >= minimum` in tests.
- `coordinates` key may be omitted when `BBOX_ASSERTIONS_VIABLE = False`.

Generator scripts write this file at generation time with the content placed on the page.

---

## Narrow tests — Group F only

A narrow test is defined by three conditions: (1) the node function is called directly,
bypassing `build_app()`; (2) state is pre-built in code, not derived from running
upstream nodes; (3) no PDF file is required — all inputs are constructible as Python
objects in memory. Every verdict below is evaluated against these three conditions.

After systematically evaluating every group against these conditions, the conclusion is
that narrow tests are **only justified for Group F** — the only LLM node that does not
consume `file_path`.

### Why narrow tests fail for most groups

**The `file_path` structural constraint.** Every LLM node except `layout_hierarchy_agent_node`
calls `encode_pdf_async(file_path)` to send PDF bytes to the model. Calling these nodes
"directly" still requires the same real PDF file as the e2e test — condition (3) can never
be met. There is no simplification over running the e2e.

**The identity problem.** The e2e tests for C and D already mock the classifier via
`src.nodes.classifier_node.AsyncAnthropic`. After that patch fires, `window_parser_node`
is called with the injected `document_type` from state — exactly what a "narrow" call
would do. Narrow C/D produces the same execution path as e2e C/D, minus
`pioneer_validation_route` (schema validation). Narrow is not an independent signal;
it is a strictly weaker version of the test that already exists.

**The schema-validation bypass (D specifically).** For Group D, `pioneer_validation_route`
is the mechanism that detects malformed metadata and triggers retries. Bypassing the
graph skips this entirely. A narrow D test that passes gives no assurance that the
pipeline catches broken `table_data` — the opposite of what D is designed to test.
"Partially useful for development" understates the problem: narrow D creates false
confidence.

**The LangGraph dependency (E).** The burst dispatch mechanism uses the LangGraph Send
API, which only exists inside a compiled graph. Calling `burst_dispatcher_node` directly
cannot simulate concurrent Send routing or the `merge_flat_blocks` reducer. E's behavior
is architecturally inseparable from `build_app()`.

**The already-covered problem.** The existing mock-based unit tests already test each
node's logic in isolation with mocked API responses. What they don't test is "does the
real model behave correctly on real PDF content?" — and that is answered by the e2e
tests. Narrow tests occupy an awkward middle ground that duplicates both without adding
signal.

### Group-by-group verdict

| Group | Narrow test verdict | Reason |
|---|---|---|
| A | N/A — deterministic | No LLM; direct function call is the only sensible approach, not a strategy choice. The three conditions are meaningless for a pure-Python deterministic function. |
| B | Not narrow — concern-isolated only | Requires `file_path` + real PDF (classifier calls `encode_pdf_async`); runs via graph with all other nodes mocked. Concern-isolated, but fails all three narrow-test conditions. |
| C | Not justified | Classifier already mocked in e2e C; calling `window_parser_node` directly produces the same path minus schema validation. No independent signal. |
| D | **Not justified** | Bypasses `pioneer_validation_route` — schema validation is the key signal D is designed to stress. Narrow D passes even when the validation route is broken: false confidence. |
| E | Not applicable | LangGraph Send API cannot be invoked outside the compiled graph. Burst dispatch and `merge_flat_blocks` are architecturally inseparable from `build_app()`. |
| F | **Add narrow tests** | See below |
| G | Not justified | `window_parser_node` still requires `file_path`; no PDF savings over e2e. Conditional isolation already provides diagnostic specificity: sorter is deterministically unit-tested, so a G1 failure always points to extractor xmin. |
| H | Not applicable | H1's exception-propagation concern requires the full pipeline. Empty-block behavior in the hierarchy node is already unit-tested (`test_empty_blocks_skips_api`). |

### Group F narrow tests (no PDF required)

`layout_hierarchy_agent_node` is the **only LLM node that qualifies** for narrow tests,
for a structural reason: it is the only LLM node that does not call `encode_pdf_async`.
Every other LLM node (classifier, pioneer_parser, parser_worker) passes `file_path` to
`encode_pdf_async` to send PDF bytes to the model — making them fundamentally
PDF-dependent regardless of how state is otherwise constructed. `layout_hierarchy_agent_node`
reads only `extracted_flat_blocks`, which is a list of Python dicts constructible entirely
in memory. Conditions (2) and (3) of the narrow-test definition are met by the node's
architecture, not by clever test design.

This structural property produces three benefits:
- Its input (a flat block list) is fully constructible without any PDF on disk
- Its output (`parent_id` assignments) does not depend on HOW those blocks were extracted
- No false-confidence risk: the hierarchy LLM's behavior is genuinely independent of upstream schema selection

Implementation: call `layout_hierarchy_agent_node(state)` directly as a function.
Bypass `build_app()`. State is hand-crafted:

```python
# Only the keys that layout_hierarchy_agent_node actually reads:
state = {
    "document_type": "baseline_core",   # written to hierarchical_document_tree output
    "pdf_hash": "x" * 64,               # written to hierarchical_document_tree output
    "extracted_flat_blocks": [           # the input under test
        # hand-crafted blocks go here
    ],
    "extraction_warnings": [],           # merged into output warnings
}
result = await layout_hierarchy_agent_node(state)
```

**Critical**: hand-crafted blocks MUST have `bbox.coordinates` that produce the
intended sort order under `geometric_pre_sorter` (which runs inside the node before the
API call). Sort key is `(page ASC, xmin // 50 ASC, ymin ASC)`. If `ymin` values are
not in reading order, the sorter reorders blocks and the hierarchy assertion tests a
different sequence than intended. Always set ymin in monotonically increasing order for
single-column fixtures.

### The B→C→E→F integration gap

Neither narrow tests nor the current group structure test the end-to-end chain:
**classifier output → schema selection → extraction → hierarchy**. This chain can break
at its seams (e.g., state key name changes) while all individual groups pass.

**Resolution:** add one **full-chain integration test** with no mocks:
- 1-page invoice PDF with a heading, paragraph, and line-items table
- Runs `build_app()` with all nodes real
- Asserts: `document_type == "invoice"`, at least one `table` block with `table_data`,
  `extraction_warnings == []`
- Tagged `@pytest.mark.e2e @pytest.mark.integration_chain`
- Lives in `tests/integration/test_full_chain.py`

---

## Devil's advocate: known weaknesses and resolutions

A systematic review of every assumption in this plan, organized by section.

---

### On the goal: "ground truth" is a misnomer

The plan previously used "ground truth at generation time." Ground truth implies
mathematical certainty. What golden files actually contain is **expected output** based
on a single (or a few) runs at a point in time. If the model updates, golden files
become stale silently. Using "expected output" throughout is more accurate.

**Resolution:** terminology changed throughout the plan.

---

### On binary PDFs in git

Committing PDF binaries creates diffs that are unreadable, review impossible, and
repository size that compounds with every regeneration. A generator script change that
fixes a typo produces a binary diff with no way to verify the fix.

**Resolution:** evaluate two alternatives before committing to binary storage:
1. **Regenerate at test time** via a pytest `session`-scoped fixture. Generators run
   once per test session if the PDF doesn't exist. Cost: ~1 s per generator at session
   start. PDFs are in `.gitignore`; only generators and golden files are tracked.
2. **Git LFS** for PDF storage. Keeps PDFs in git history but defers binary to LFS.

Option 1 is recommended: no binary bloat, no LFS dependency, golden files (JSON) remain
the committed artifact reviewable as text diffs. The downside is that tests cannot run
entirely offline — the PDF must be regenerated if missing. Since tests already require
an API key, this is an acceptable constraint.

**Decision: PDFs are NOT committed. Only generators and golden files are committed.**
`tests/fixtures/pdfs/` goes in `.gitignore`. `make fixtures` or the pytest session
fixture regenerates them.

---

### On coordinate calibration: scale consistency assumption

The calibration plan runs ONE fixture (C1) and derives a single `COORD_SCALE`. But
Claude's internal coordinate space might:
1. Vary by page content density (more complex pages might render at different effective
   DPI)
2. Be a non-integer multiplier — applying a float scale to integer source coordinates
   produces rounding that compounds per-block

Additionally, the coordinate formula:
```
ymin_claude = page_height_pts − (y_rl + height_rl)
```
assumes Claude uses top-left origin. This is unverified. If Claude uses a different
reference point, the formula is wrong and all golden bboxes are wrong.

**Resolution:** Phase 0 calibration must run THREE different fixtures (C1, C7-table, G1-
twocolumn) and compare the scale factors. If they differ, bbox assertions are disabled
permanently. The `COORD_SCALE` constant is replaced with `BBOX_ASSERTIONS_VIABLE = False`
and all bbox checks are skipped. The calibration doc is committed as
`tests/fixtures/generators/calibration_notes.md`.

---

### On ±5 % bbox tolerance: wrong denominator

±5 % of page HEIGHT is ≈ 42 pt on A4. For a block that's 20 pt tall, the allowed error
is ±42 pt — more than two block heights. A block in the wrong region of the page would
still pass. This tolerance validates almost nothing about block location.

If bbox assertions are viable, use **±5 % of the block's own dimension** (height for y
coords, width for x coords) rather than page dimension. This scales with block size and
is semantically meaningful: a block is within 5 % of where it should be relative to
itself. For blocks smaller than 10 pt, apply a floor of ±5 pt absolute.

**Resolution:** change tolerance formula in `_compare.py` if bbox assertions are enabled
post-calibration. Remove the "≈ ±36 pt on A4" statement which is misleading.

---

### On exact text matching: will fail immediately

Claude normalizes whitespace (collapses multiple spaces to one), may alter quote styles
(straight → curly), and may include/exclude trailing punctuation. Starting with exact
matching means tests fail from the first run and we spend time weakening assertions
rather than testing behavior.

**Resolution (already in Design Principle 5):** `normalize_text=True` is the default.
Normalization: strip leading/trailing whitespace, collapse internal whitespace to single
spaces, normalize Unicode quotes to ASCII. Do NOT lowercase (case changes are meaningful
extraction errors).

---

### On `block_count` in golden files: strict count causes false negatives

If Claude merges two adjacent paragraphs into one block (acceptable behavior), a test
asserting `block_count == 3` fails even though the content is fully present. This
produces a false negative — the test flags a regression where none exists.

**Resolution:** remove `block_count` from golden files. Assert instead:
- For known-single-block tests (C1–C3, C5, C6): `len(blocks) >= 1` and the
  expected text appears in some block.
- For known-multi-block tests (C4, F2, etc.): `len(blocks) >= expected_minimum`,
  not `len(blocks) == expected_exact`.

---

### On Group B: Design Principle 4 contradiction

Group B mocks all nodes except the classifier. Design Principle 4 says "full e2e."
These are contradictory. Resolving in favour of Group B's design: **Group B tests
the classifier in isolation (other nodes mocked)**. This is explicitly not full e2e.
The full-chain integration test (see §Narrow tests) covers what Group B's e2e would
have covered.

---

### On B3: the assertion is trivially true

The proposed fallback assertion for B3 is "document_type is a non-empty string." But
`document_type` is always non-empty — the fallback path hardcodes it to `"baseline_core"`.
This assertion would pass for any input, including a broken classifier that always
falls back.

**Resolution:** remove B3 as a standalone test. The fallback path is already exhaustively
tested in `test_classifier_node.py:test_unknown_falls_back`. An e2e fixture for an
ambiguous PDF adds no diagnostic value and is inherently unreliable (we can't control
what the model returns for ambiguous content). **B3 is dropped. Group B has two tests:
B1 (invoice) and B2 (scientific paper).**

---

### On C5 and C6: block types without visual signals are unreliable

C5 (footnote): a paragraph placed at page bottom without a horizontal rule, superscript
references, or reduced font size is visually indistinguishable from a regular paragraph.
The model will likely classify it as `paragraph`, not `footnote`.

C6 (margin element): text in a narrow left-column without distinctive formatting (grey
background, smaller font, or explicit sidebar styling) will likely be classified as
`paragraph`.

Both tests will be flaky because achieving the target block type depends on visual
signals that are difficult to guarantee in programmatic PDF generation.

**Resolution:** C5 and C6 are redesigned:
- C5 becomes **C5_footnote_styled**: uses reduced font size (7pt vs. 11pt body), a
  thin horizontal rule above it, and a superscript reference marker in the body text.
  Multiple strong signals, not just position.
- C6 becomes **C6_margin_styled**: uses a sidebar with a grey rectangle behind the
  text and a clearly narrower column (< 25% of page width).
- If after implementation both still prove flaky (> 20% failure rate across 10 runs),
  they are removed from Group C and noted as "block types that require real-world
  documents."

---

### On C7: `baseline_core` schema doesn't validate `table_data` structure

`window_parser_node` calls `SchemaRegistry().get_schema_and_tool(state["document_type"])`.
For C7, the injected `document_type="baseline_core"` makes it use the `baseline_core`
schema, which defines `metadata` as `{"type": "object"}` — completely open. The model
can return any structure for `metadata.table_data` and the schema validation passes.
This means the retry loop won't fire even on malformed table_data, and the test won't
catch a broken table structure.

**Resolution:** C7 is moved to Group D where the classifier is mocked to return
`invoice`, forcing the invoice schema (which has `table_data` as a typed subfield).
C7's slot in Group C is replaced by a simpler table-presence test: assert a `table`
block exists with non-empty `text`. D1 handles the structured `table_data` assertion.

---

### On C8: a grey rectangle may not be classified as `figure`

A `canvas.rect()` call in reportlab produces a grey rectangle with no semantic
metadata in the PDF content stream. Claude reads the page visually — a grey box
without a "Figure N:" label or caption is likely classified as nothing (skipped) or
as a generic `paragraph` with empty text.

**Resolution:** C8 generates a PDF with:
1. A grey filled rectangle (figure placeholder)
2. "Figure 1: Synthetic chart placeholder" in caption text immediately below it (bold, smaller font)
The caption provides the critical signal. Assert: at least one `figure` OR a block
whose text starts with "Figure 1:". The `figure` type detection is an aspirational
assertion; the caption text assertion is the hard one.

---

### On Group D: optional metadata subfields are not guaranteed

The `scientific_paper` schema's `bibliographic`, `section`, `reference`, and
`figure_table` subfields are in `properties` but NOT in `required` within `metadata`.
The extraction prompt does not instruct the model to populate specific metadata
subfields — it says only "return structured data matching the schema parameters."
Without explicit instructions, the model may return all content in `text` without
populating any metadata subfields, and schema validation still passes.

**Resolution:** D2–D5 assertions change from "assert subfield is populated" to
"assert subfield is populated OR text contains the expected content." This
acknowledges that the model may put the information in `text` rather than structured
metadata. If a subfield is consistently unpopulated across runs, the extraction prompt
needs updating (a prompt change), not a test change.

D5's `referenced_block_id` assertion is **dropped** — block IDs are non-deterministic
and cannot be pinned.

---

### On D3 section metadata format: model may format differently

D3 asserts `section_number == "2"` and `section_title == "Methodology"`. The model
might return `section_number == "2."` (with period) or `section_title == "2. Methodology"`
(with the number included). These are not schema violations but are value mismatches.

**Resolution:** use normalized substring matching: assert `"2" in section_number` and
`"Methodology" in section_title` rather than exact equality.

---

### On E2: `len(blocks) == 5` is fragile

A 5-page doc where each page has 1 paragraph does not guarantee exactly 5 blocks.
The extractor for any page might return 0 blocks (triggering a retry for page 1, or
silently producing nothing for pages 2–5). Asserting exact count will produce false
negatives whenever the model splits or merges content.

**Resolution:** assert `for page in range(1, 6): any block with bbox.page_number == page`.
This tests "all pages were extracted" without assuming one block per page.

---

### On E3: `is_continued` is not prompted

The extraction prompt says only "Extract structure elements EXCLUSIVELY located on
physical Page N." There is no instruction to set `is_continued`. The field's schema
default is `false`. The model will reliably return `false` because it receives no
signal to do otherwise.

**Resolution:** E3 is **suspended** pending a decision on the extraction prompt. Before
implementing E3, confirm in the extraction prompt that `is_continued` should be set
when content continues. If the prompt is not updated, E3 will always fail and should
not be committed. Document this as a known gap in the extraction prompt.

---

### On F3: contradicts the hierarchy node's documented rules

The hierarchy node prompt states: "Top-level blocks (title, unpaired headings) get
`parent_id = null`." F3 expects "heading is child of title" — i.e., heading should
have `parent_id` pointing to the title. The documented rule says headings are always
root-level (parent_id = null).

Either F3's assertion is wrong (the heading SHOULD be null per the prompt) or the
hierarchy prompt needs to be extended to describe title→heading nesting explicitly.

**Resolution:** F3 is redesigned. The 3-level test is replaced by verifying that
the hierarchy node correctly keeps a standalone title at root AND simultaneously
assigns paragraphs under a heading when both are present. This is two separate
assertions within the same test, not a 3-level nesting assertion.

---

### On F5: type-of-parent check cannot distinguish heading-1 from heading-2

F5 has 2 headings each with 2 paragraphs. `assert_hierarchy_structure` checking
"paragraph's parent is some heading" passes even if ALL paragraphs point to the same
heading (which is wrong). The structural rule requires that each paragraph points to
its NEAREST preceding heading.

**Resolution:** F5 assertion uses position-based checking: sort blocks by ymin,
identify heading positions, then for each paragraph verify its `parent_id` matches
the `block_id` of the nearest preceding block with `type == "heading"` in the sorted
list. This requires a new helper: `assert_nearest_heading_parent(blocks)`.

---

### On G2: duplicates existing unit test coverage

G2 ("10 paragraphs in monotonic top-to-bottom order") tests the same behavior as
`test_hierarchy_node.py:test_sorts_by_ymin_within_column` — which already covers the
geometric_pre_sorter. G2 adds an API call cost to verify behavior that is already
deterministically unit-tested.

**Resolution:** G2 is dropped. Group G has one test: G1 (two-column layout).

---

### On H1: the assertion is too weak

Allowing `len(blocks) <= 2` on a blank page means the test only catches exceptions,
not behavioral regressions. If the model hallucinates 5 blocks on a blank page, the
test still passes.

**Resolution:** H1 asserts `len(blocks) <= 1`. If a block is returned, it must have
`text.strip() == ""` or `len(text.strip()) < 10` (any "hallucinated" content is
short). H1 is fundamentally a smoke test, not a quality test — name it accordingly.

---

### On H2: duplicate of C1 extension

H2 (500-word full-page paragraph) tests extraction quality on longer text. This is
C1 with more words — not a distinct concern. H2 is moved to **C9** (long paragraph
extraction) and Group H is reduced to H1 only.

---

### On `COLUMN_BUCKET_PX` dependency

G1 relies on `COLUMN_BUCKET_PX = 50` being the column bucket width. If `src/config.py`
changes this constant, G1 may silently start failing. The test should import
`COLUMN_BUCKET_PX` from `src.config` and document the column placement calculation
explicitly so a future developer knows why the left column starts at xmin ≈ 36 pt
and the right column at xmin ≈ 315 pt.

---

### On cost estimate: retries not accounted for

The estimate of ~30 calls assumes every pioneer extraction passes on the first attempt.
With retries, a 25% retry rate on 20 extraction tests = ~5 extra calls. Actual expected
range: **30–50 Claude calls per full run**. At ~$0.02/call average: $0.60–$1.00 per
run. The estimate is directionally correct but should be stated as a range.

---

### On pytest markers: not registered in `pyproject.toml`

The `grp_a`, `grp_b`, …, `integration_chain` markers don't exist in `pyproject.toml`.
Running pytest with unregistered markers triggers warnings and can cause marker
mismatches. **Add all markers to `pyproject.toml` under `[tool.pytest.ini_options]`
as part of Phase 1.**

---

### On `make fixtures GRP=c`: not in the Makefile

The current `Makefile` doesn't accept a `GRP` parameter. **Add `fixtures` target with
optional `GRP` filter as part of Phase 1.**

---

## Test groups

Groups are ordered by concern, not by complexity. Within each group, tests are numbered
and increase in complexity. All tests in a group share a `@pytest.mark.grp_X` marker.

---

### Group A — Native extraction (no LLM, no API key required)

Node under test: `native_extractor_node` (pypdf only).
Tests call `native_extractor_node(state)` **directly as a function** — same pattern
as F narrow tests. This captures intermediate state (`total_pages`, `pdf_hash`)
without running the graph or needing intermediate state capture from LangGraph.
`state` is minimal: only `file_path` is required.

| ID | PDF | Assertions |
|---|---|---|
| A1 | Valid 1-page PDF | `result["total_pages"] == 1`; `len(result["pdf_hash"]) == 64` |
| A2 | Valid 10-page PDF | `result["total_pages"] == 10` |
| A3 | Encrypted PDF (pypdf-generated) | `pytest.raises(ValueError)`; classifier mock `assert_not_called()` to confirm early exit |

> A3 uses a programmatically encrypted PDF (`pypdf.PdfWriter` with encryption). This
> tests the actual pypdf encryption detection, which the existing unit test bypasses via
> `mocker.patch("get_page_count")`. No API call is made for any A test.

---

### Group B — Classifier accuracy (1 Claude call per test)

Node under test: `classifier_node`. All other nodes mocked (not full e2e — see §Design
principles and §Narrow tests for the rationale).

| ID | PDF content | Expected `document_type` |
|---|---|---|
| B1 | Company header, "INVOICE #001", billing table, line items | `invoice` |
| B2 | Paper title in large font, two authors, "Abstract" heading, body text, "DOI:" line | `scientific_paper` |

> B3 (ambiguous → fallback) is removed. The fallback path is already exhaustively
> tested in `test_classifier_node.py:test_unknown_falls_back`. An e2e fixture for
> ambiguous content is unreliable because we can't control the model's response — see
> §Devil's advocate for the full reasoning.

---

### Group C — Block-type extraction (1–2 Claude calls per test)

Node under test: `window_parser_node` (pioneer page, 1-page PDFs so burst never fires).
Classifier is mocked by patching `src.nodes.classifier_node.AsyncAnthropic` to return
`"baseline_core"`. Hierarchy is mocked by patching
`src.nodes.hierarchy_node.AsyncAnthropic` to return trivial relations — **not** by
patching the whole functions, so deduplication and sort still run. One PDF per block type.

All count assertions use `>= minimum`, not `== exact`. Text assertions use normalized
matching (strip + collapse whitespace).

| ID | PDF content | Expected block type | Key assertions |
|---|---|---|---|
| C1 | One short paragraph | `paragraph` | `len(blocks) >= 1`; expected text in some block |
| C2 | One large-font title line | `title` | `len(blocks) >= 1`; expected text in some block |
| C3 | One bold heading line | `heading` | `len(blocks) >= 1`; expected text in some block |
| C4 | Unordered list (3 items, bullet points) | `list_item` ×3 | `len(blocks) >= 3`; each item text present in some block |
| C5 | Footnote-styled text: 7pt font, horizontal rule above, superscript marker in body | `footnote` | `len(blocks) >= 2`; at least one block with `type=="footnote"` |
| C6 | Margin sidebar: grey background rect, narrow column (< 25% page width), smaller font | `margin_element` | At least one block with `type=="margin_element"` |
| C7 | 3×4 table; table presence only (full metadata in D1) | `table` | At least one `table` block with non-empty `text` |
| C8 | Grey rectangle + "Figure 1: Synthetic chart" caption below | `figure` or `paragraph` with "Figure 1:" | Figure block OR block whose text starts with "Figure 1:" |
| C9 | 500-word paragraph filling the full page | `paragraph` | `len(blocks) >= 1`; first and last sentence present in some block's text |

> C5 and C6 use multiple visual signals (not just position) to reduce type
> misclassification. If either fails > 20% across 10 runs, they are removed and
> documented as "block types requiring real-world documents."
>
> C7 asserts only presence; structured `table_data` validation is in D1 where the
> invoice schema enforces structure. In C7 with `baseline_core`, metadata is open
> and the schema won't catch malformed table_data.
>
> C9 replaces H2 (long paragraph), which is a C extension, not a distinct concern.

---

### Group D — Schema-specific metadata (1–2 Claude calls per test)

Node under test: `window_parser_node` + schema validation in `pioneer_validation_route`.
Classifier is mocked to return the target doc type so the correct schema is loaded.
Hierarchy is mocked (trivial parent_ids). 1-page PDFs.

**Important:** `bibliographic`, `section`, `reference`, and `figure_table` are optional
subfields in the scientific_paper schema — the model is not required to populate them.
Assertions use "if populated, assert content; else assert content appears in block text."
The extraction prompt may need updating to explicitly request these subfields; that is
a prompt change, not a test change.

| ID | Doc type mocked | PDF content | Metadata subfield | Key assertions |
|---|---|---|---|---|
| D1 | `invoice` | 4-col line-items table (description, qty, price, total) with header row | `table_data` | `table` block present; if `table_data` populated: `cells` contains all generated values; `is_header` on row 0 |
| D2 | `scientific_paper` | Title + 3 author names + "Abstract" heading + abstract paragraph | `bibliographic` | If `bibliographic.authors` populated: all 3 generated author names present in list; else all 3 author names present somewhere in block text |
| D3 | `scientific_paper` | "2. Methodology" as bold heading + 2 paragraphs | `section` | If `section` populated: `"2" in section_number` and `"Methodology" in section_title`; else "Methodology" present in some block's text |
| D4 | `scientific_paper` | 3 numbered reference entries (author-year-title format) | `reference` | If `reference` populated on any block: `year` is an integer; else reference text present in some block's text |
| D5 | `scientific_paper` | Grey rectangle + "Figure 1: Caption text" caption below | `figure_table` | If `figure_table` populated: `"Figure 1" in label` and caption text present; `referenced_block_id` is **not asserted** (non-deterministic block IDs) |

---

### Group E — Multi-page pipeline / burst + merge (N Claude calls per test)

Nodes under test: `burst_dispatcher_node`, `window_parser_node` (pages 2–N), `merge_flat_blocks` reducer.
Hierarchy LLM is mocked by patching `src.nodes.hierarchy_node.AsyncAnthropic` to return
trivial `{block_id: ..., parent_id: null}` relations — **not** by patching the whole
`layout_hierarchy_agent_node` function. This preserves the deduplication and sort steps
so the `block_id` uniqueness assertion is meaningful.

| ID | PDF | Assertions |
|---|---|---|
| E1 | 2-page doc (1 paragraph per page, distinct text per page) | At least one block with `bbox.page_number == 1` AND at least one with `bbox.page_number == 2`; no duplicate `block_id` values |
| E2 | 5-page doc (1 paragraph per page) | For each page 1–5: at least one block with `bbox.page_number == page` present; no duplicate `block_id` |

> `len(blocks) == N` is not asserted (model may split or merge content across pages).
> The assertion is "every page contributed at least one block."
>
> E3 (`is_continued`) is **suspended** until the extraction prompt explicitly instructs
> the model to set `is_continued`. The current prompt has no such instruction; the field
> defaults to `false` and E3 would always fail. See §Devil's advocate for details.

---

### Group F — Hierarchy assignment quality (narrow tests, no PDF required)

Node under test: `layout_hierarchy_agent_node`.
Tests call the function directly with pre-built state (not via `build_app()`). No PDF,
no classifier, no pioneer. Real hierarchy LLM call. See §Narrow tests for implementation.

Pre-built blocks MUST have `bbox.coordinates[0]` (ymin) in monotonically increasing
order within a page and in the same `xmin // 50` bucket (e.g., all `xmin = 70`) so
`geometric_pre_sorter` preserves the intended reading order.

| ID | Pre-built blocks | Expected hierarchy | Key assertions |
|---|---|---|---|
| F1 | `[heading, paragraph]` | paragraph under heading | `paragraph.parent_id` resolves to `heading.block_id`; heading `parent_id == null` |
| F2 | `[heading, paragraph, paragraph, table]` | paragraphs + table under heading | all three blocks' `parent_id` → heading's `block_id` |
| F3 | `[title, heading, paragraph]` | title at root; heading at root; paragraph under heading | `title.parent_id == null`; `heading.parent_id == null`; `paragraph.parent_id` → heading |
| F4 | `[heading-A, para-A1, para-A2, heading-B, para-B1, para-B2]` | each paragraph under its nearest preceding heading | `assert_nearest_heading_parent(blocks)` |

> **F1 replaces the old "single title block" case.** The single-block path is already
> covered by `test_hierarchy_node.py:test_single_block_skips_api_and_sets_parent_none`
> — it skips the LLM call entirely (hardcoded). F1 now tests the simplest REAL LLM
> call: heading + paragraph.
>
> **F4 (figure-caption) is removed.** The hierarchy prompt has no documented rule for
> figure→caption relationships. Asserting this would test undocumented/inferred model
> behavior and produce unpredictable flakiness. If figure-caption nesting is desired,
> the hierarchy prompt must first be updated with an explicit rule, then F4 is added.
>
> **F3 confirms the documented rule:** both `title` AND `heading` are root-level. This
> is the key insight from the F3 redesign — the hierarchy agent treats them symmetrically.
>
> F4 (old numbering) is renumbered to F4 (multi-heading disambiguation).

---

### Group G — Layout / reading order (1 Claude call)

Node under test: `window_parser_node` (extraction quality on multi-column layout).
`geometric_pre_sorter` is already deterministically unit-tested. What G tests is whether
the extractor assigns `xmin` values that correctly distinguish columns, allowing the
sorter to order them correctly. G2 is dropped (duplicates existing sorter unit tests).

Tests import `COLUMN_BUCKET_PX` from `src.config` and document the column placement
calculation explicitly.

| ID | PDF content | Assertions |
|---|---|---|
| G1 | 2-column A4 (left column xmin ≈ 36 pt → bucket 0; right column xmin ≈ 315 pt → bucket 6): left has "L1", "L2", "L3"; right has "R1", "R2", "R3" | (1) All blocks whose `bbox.xmin < page_width/2` appear before all blocks whose `bbox.xmin >= page_width/2` in `structured_payload`; (2) "L1", "L2", "L3" texts are each in some block; (3) "R1", "R2", "R3" texts are each in some block |

> **Why `bbox.xmin`, not text prefix:** using text-prefix to identify column membership
> is circular — it can't detect bleed. Position-based assertion (xmin relative to page
> midpoint) is independent of text content. If the model bleeds L-text into an R-xmin
> block, assertion (1) catches the ordering failure. Assertions (2) and (3) confirm no
> content was lost.

---

### Group H — Graceful degradation (1 Claude call)

Reduced to H1 only. H2 (long paragraph) moved to C9.

| ID | PDF content | Assertions |
|---|---|---|
| H1 | 1 blank white page (no text, no objects) | Pipeline completes without exception; `len(blocks) <= 1`; if a block exists, `len(block.text.strip()) < 10` |

> H1 is explicitly a smoke test: it checks the pipeline doesn't crash on degenerate
> input. It does not assert meaningful extraction quality.

---

## Phased delivery

### Phase 0 — Calibration (prerequisite, no tests written yet)

- Implement `_common.py` and C1 generator only; add `tests/fixtures/pdfs/` to `.gitignore`
- Mock classifier and hierarchy; run only pioneer_parser on C1 PDF — 3 times
- Record returned `coordinates` each run; derive `COORD_SCALE` or flag as non-viable
- Commit `calibration_notes.md` with raw numbers and decision
- Set `COORD_SCALE = <k>` or `BBOX_ASSERTIONS_VIABLE = False` in `_common.py`
- Phase 1 (when D1 and G1 exist) repeats the check across content types to verify scale
  consistency; if inconsistent, override to `BBOX_ASSERTIONS_VIABLE = False`

### Phase 1 — Foundation: Groups A, B, C + infrastructure

- `tests/fixtures/` directory structure; `tests/fixtures/pdfs/` in `.gitignore`
- `generate_all.py` CLI (session-scoped pytest fixture regenerates missing PDFs)
- `_common.py` reportlab helpers (canvas, drawString, table helper, figure rect)
- Generators and golden files for A1–A3, B1–B2, C1–C9
- `tests/integration/_compare.py`: `assert_blocks_match` (`normalize_text=True` default),
  `assert_table_data`
- Integration tests for groups A, B, C
- `make fixtures [GRP=x]` target; `make test-e2e` shortcut
- **Register all pytest markers in `pyproject.toml`**:
  `e2e`, `grp_a`, `grp_b`, `grp_c`, `grp_d`, `grp_e`, `grp_f`, `grp_g`, `grp_h`,
  `integration_chain`

### Phase 2 — Schema metadata: Group D

- Generators and golden files for D1–D5
- `_compare.py` extended with optional-metadata assertion helpers
- Integration tests for group D

### Phase 3 — Pipeline behavior: Groups E and F

- Multi-page generators (E1, E2); E3 remains suspended pending prompt update
- Hierarchy tests (F1–F5) as **narrow function calls** (no PDF; pre-built state)
- `assert_nearest_heading_parent` helper added to `_compare.py`
- Integration tests for group E; narrow tests for group F

### Phase 4 — Layout, edge cases, and full-chain

- Two-column generator (G1); edge-case generator (H1)
- Integration tests for groups G and H
- **Full-chain integration test** (`tests/integration/test_full_chain.py`):
  no mocks, reuses the B1 PDF (1-page invoice), all nodes real, asserts:
  `document_type == "invoice"`, at least one `table` block present,
  `not any("failed schema validation" in w for w in extraction_warnings)`
  (tolerates benign warnings, catches degradation)
- Update README with `make test-e2e GRP=x` usage

---

## Remaining open questions / risks

The §Devil's advocate section resolved most prior risks. The following remain open.

1. **C5 and C6 reliability.** The redesigned fixtures (footnote-styled, margin-sidebar)
   add multiple visual signals but still cannot guarantee the model returns the target
   type enum. Monitor failure rate during Phase 1. Remove if > 20% failure rate across
   10 runs.

2. **D-group optional metadata.** If the extraction prompt never causes the model to
   populate `bibliographic`, `section`, `reference`, or `figure_table`, the D2–D5 tests
   degrade to "expected text appears in some block" — which is a C-level assertion, not
   a D-level assertion. The decision to update the extraction prompt is out of scope for
   this plan but should be tracked as a separate issue.

3. **E3 suspended.** `is_continued` detection requires a prompt change. Until that
   change is made, the continuation behavior is untested at the e2e level. This is a
   known gap in the extraction prompt, not a gap in the test plan.

4. **F narrow test flakiness.** The hierarchy LLM makes judgment calls on ambiguous
   inputs. F4 (figure → caption) and F5 (2 headings, 4 paragraphs) may have higher
   variance. If either fails > 30% across 10 runs, loosen the assertion (e.g., F4:
   "caption has SOME parent_id" rather than "parent_id → figure block").

5. **Golden file staleness.** Prompt or schema changes require `make fixtures` +
   `git diff tests/fixtures/golden/` review. The diff is human-readable (golden files
   are JSON). A semantically reasonable diff means the change is safe.

6. **Cost.** Expected API calls: A: 0, B: 2, C: 9, D: 5, E: 4, F: 5 (narrow, no PDF),
   G: 1, H: 1, full-chain: 3 = ~30 calls + ~10 retry overhead = **30–50 calls per
   full suite run.** At ~$0.02/call: $0.60–$1.00 per run. Nightly CI is appropriate.

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
_v4 — 2026-06-02 18:30 — Option 2 narrow-test conclusions (Group F only; other groups not justified); full 33-point devil's advocate review; resolved: binary PDF storage → PDFs not committed; B3 dropped (trivially true assertion); C5/C6 require multi-signal design or removal; C7 moved to D1 (wrong schema in baseline_core); exact text → normalized default; block_count → minimum bounds; E3 suspended (is_continued not prompted); F3 corrected per hierarchy rules; F5 upgraded to nearest-heading-parent assertion; G2 dropped (duplicates unit tests); H2 → C9; bbox tolerance formula fixed (block dimension not page dimension); full-chain integration test added_
_v5 — 2026-06-02 19:00 — second devil's advocate pass; 18 further issues resolved: Design Principle 1 contradiction (PDFs not committed); comparison contract updated (is_continued removed, bbox tolerance corrected); bbox note formula corrected; normalize_text default fixed in _compare.py spec; docstring lowercasing removed; block_count removed from golden file example; D2 assertion garbled (copy-paste from D3) fixed; calibration section "Level 1" stale name fixed; Phase 0 C7/G1 impossibility fixed; F1 redesigned (single-block path skips LLM — already unit-tested, no value); F4 removed (figure-caption has no documented hierarchy rule); F state spec trimmed to only keys the function reads; G1 assertion fixed (xmin-based, not text-prefix-based — circular); E hierarchy mock clarified (AsyncAnthropic, not whole function); same for C; full-chain test assertion hardened; hierarchy assertions section updated with documented vs undocumented rules_
_v6 — 2026-06-02 19:30 — narrow-test section rewritten after third devil's advocate pass on that section specifically: added three-condition formal definition; A verdict corrected (N/A — not a strategy choice); B verdict corrected (concern-isolated, not technically narrow — fails all 3 conditions); C argument replaced (identity problem: narrow C = e2e C minus schema validation, false-confidence argument was empirically wrong); D verdict changed from "partially useful" to "not justified" (bypasses pioneer_validation_route — the key signal for D, creates false confidence); E verdict corrected (LangGraph Send API dependency — E3 reference was dead, E3 is suspended); F section rewritten to lead with the structural argument (only LLM node without encode_pdf_async); G verdict sharpened (file_path still required + conditional isolation already covers diagnostic gap); H verdict strengthened (full-pipeline exception propagation + already unit-tested empty-block behavior)_
