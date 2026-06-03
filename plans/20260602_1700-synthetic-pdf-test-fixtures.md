# Synthetic PDF Test Fixtures — Plan

- _Created: 2026-06-02 17:00_  
- _Updated: 2026-06-02 17:30 · v2 — coordinate calibration, block-matching strategy, compare helper spec_  
- _Updated: 2026-06-02 18:00 · v3 — full redesign: replace linear levels with concern-separated groups after code review_  
- _Updated: 2026-06-02 18:30 · v4 — Option 2 narrow-test conclusions + full 33-point devil's advocate review_  
- _Updated: 2026-06-02 19:00 · v5 — second devil's advocate pass: 18 further issues resolved_  
- _Updated: 2026-06-02 19:30 · v6 — narrow-test section rewritten: per-group verdict table corrected_  
- _Updated: 2026-06-02 20:00 · v7 — generator switched to fpdf2; binary-PDF storage resolved as approach 3 (manifest hash)_  
- _Updated: 2026-06-02 20:30 · v8 — D/A section removed (all 24 resolutions applied); stale references cleaned up_  
- _Updated: 2026-06-02 21:00 · v9 — pass 4 D/A: A3 classifier-mock assertion removed; hierarchy mock clarified to empty-relations pattern; E classifier mock documented; G1 column assertion rewritten to bucket-based (calibration-free); full-chain table_data assertion resolved; E cost corrected (7 not 4); all 6 risks rewritten; 2 new risks added_  
- _Updated: 2026-06-02 21:30 · v10 — pass 5 (automated): 8 MEDIUM + 3 LOW resolved: "tests fallback path" wording corrected; e2e marker clarified (API-key-required, not no-mocks); A and F removed from positional-matching group; _make_relation_response moved to _compare.py spec; model_version added to golden file format + meta note; Group B mock setup fully specified; C5/C6 note aligned with Risk 1; Group D hierarchy mock specified; Group E orphan-warning note added; Phase 0 classifier mock value specified; Phase 2 prompt prerequisite added; H1 text threshold 10→30; C8 text-presence intent documented_  
- _Updated: 2026-06-02 21:45 · v11 — pass 6 (automated): 1 MEDIUM + 1 LOW: Group C stale reference to test_graph_pipeline.py corrected (import from _compare.py); Group G mock setup added (classifier + hierarchy mocked, same pattern as C/E)_  
- _Updated: 2026-06-02 22:00 · v12 — pass 7 (automated): 2 MEDIUM + 2 LOW: _make_tool_use_response and _valid_block added to _compare.py spec (same shared-import problem as _make_relation_response); Group H mock setup added; HierarchyRule defined as NamedTuple in _compare.py spec; F2 assertion now explicitly lists both HierarchyRule entries (paragraph + table)_  
- _Updated: 2026-06-02 22:30 · v13 — pass 8 (automated): 1 HIGH + 3 MEDIUM + 2 LOW: conftest fake-key overwrite documented as Phase 1 change; generate_all.py session fixture must live in tests/integration/conftest.py; e2e marker semantics clarified (excluded-from-make-test, not always requires-API-key); assert_table_data extended with expected_values param; F state spec annotated with required block fields; assert_nearest_heading_parent no-preceding-heading edge case specified_  
- _Updated: 2026-06-02 22:45 · v14 — pass 9 (automated): 1 MEDIUM + 1 LOW: directory layout comment and prose updated to reflect fixture-in-conftest (generate_all.py is CLI only); HierarchyRule None case documented (asserts parent_id is None)_  
- _Updated: 2026-06-02 23:00 · v15 — pass 10 (automated): 1 LOW: tests/integration/conftest.py added to directory layout_  
- _Updated: 2026-06-03 · v16 — remaining LOWs resolved: F3 uses assert_hierarchy_structure with HierarchyRule(None) to exercise the None case; Phase 2 optional-metadata helper clarified as inline conditional checks; Phase 1 make test updated with -m "not e2e"_  
- _Updated: 2026-06-03 · v17 — pass 11 (automated): 1 MEDIUM: "Phase 1" calibration label renamed to "Development Phase 4" to avoid collision with development phase naming_  
- _Updated: 2026-06-03 · v18 — coherence review pass 1: 3 MEDIUM + 5 LOW fixed: structured_payload access path added (pipeline output section + F state spec + full-chain assertions); E mock setup now explicitly states worker_node is NOT mocked; Phase 3 checklist adds assert_hierarchy_structure alongside assert_nearest_heading_parent; is_continued rule 2 added to Documented Rules (suspended pending E3); B1/B2 page count column added; Phase 1 _compare.py checklist lists all 5 helpers incl. mock factories; Phase 0 bbox-invalidation rollback note for meta.coord_scale; F state spec explains is_continued default behaviour; B removed from positional-matching list; integration-gap assertion cross-references Phase 4; pipeline output comment clarified_  
- _Updated: 2026-06-03 · v19 — coherence review pass 2 (ambiguity + determinism): 3 MEDIUM fixed: classifier mock changed from AsyncAnthropic-class patch (3-level mock chain, unspecified) to `_classify` function patch (unambiguous, consistent across C/D/E/G/H); C test matching strategy clarified as scan-based (not positional) due to variable block count — D/E/H remain positional; golden file creation workflow section added (design-intent pre-written, not model-captured; first-run failures expected)_  
- _Updated: 2026-06-03 · v20 — coherence review pass 3 (coverage + missing parts): 4 LOW fixed: stale AsyncAnthropic reference in narrow-tests "identity problem" paragraph corrected to _classify; _valid_block docstring extended with schema-compatibility requirement; assert_table_data docstring clarified (expected_rows = total rows incl. headers); F4 note added (heading parent_ids not asserted by design — covered by F1/F3); Phase 1 API key skip-guard approach specified_  
- _Updated: 2026-06-03 · v21 — coherence review pass 4 (implicit assumptions + explicit instructions): 5 MEDIUM + 4 LOW fixed: H removed from positional-matching group (H1 never uses positional matching); worker/hierarchy mocks changed from AsyncAnthropic class patch (3-level chain, unspecified) to _call_api function patch throughout (B, C, D, E, G, H); HierarchyRule NamedTuple added as standalone class definition in _compare.py spec with valid Python syntax (removed from docstring only); API key skip guard corrected from session-scoped to function-scoped with explicit request.node.get_closest_marker check; Group B document_type access path added to pipeline output section; Phase 0 calibration mock targets made explicit (_classify + _call_api); B hierarchy mock no-op behaviour documented (single-block optimisation); _compare.py directory comment updated to list mock factories_  
- _Updated: 2026-06-03 · v22 — coherence review pass 5 (final cleanup): 3 LOW fixed: duplicate H1 matching description removed from block-matching strategy (de-duplicated against pre-existing "For H1" paragraph); Phase 3 checklist adds HierarchyRule NamedTuple alongside assert_hierarchy_structure; H1 assertion table corrected from block.text (attribute) to block["text"] (dict); Risk 7 stale language updated (model_version field already specified; when to re-run calibration clarified)_  

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
Group B therefore **cannot test `baseline_core`** as a direct model output — that type
is never returned by the model, only by the fallback. B1 and B2 test the happy
classification paths (`invoice` and `scientific_paper`).

---

## Design principles

1. **Expected output at generation time.** Every fixture PDF is produced by an fpdf2
   generator script that also emits a `golden.json` capturing the output we expect.
   "Expected" means "consistent with what the model should produce given this input" —
   not a mathematical truth. Golden files (JSON) are committed; PDFs are not (see
   §Directory layout). Every generator pins the creation date for byte-for-byte
   reproducibility: `pdf.set_creation_date(datetime(2000, 1, 1, tzinfo=timezone.utc))`.

2. **One primary concern per group.** Each group targets one pipeline node. Within a
   group, PDFs increase in complexity. This doesn't mean zero interference from
   adjacent nodes — it means that if all earlier groups pass, a new failure is
   attributable to the new group's concern. This is **conditional isolation**,
   not absolute isolation (see §Narrow tests).

3. **Pytest marks for selective runs.** Every test carries `@pytest.mark.e2e` (excludes
   from `make test`) and `@pytest.mark.grp_X` (enables single-group runs).

4. **Two test tiers per group.** Most groups have an **e2e tier** (real API calls;
   some nodes mocked for isolation — see each group for specifics) and Group F
   additionally has a **narrow tier** (direct function call, pre-built state, no PDF
   required, see §Narrow tests). Other groups do not benefit from narrow tests — see
   §Narrow tests for the analysis. The `@pytest.mark.e2e` marker means "excluded from
   `make test`", not "full pipeline with no mocks." Groups B–H require a real
   `ANTHROPIC_API_KEY` to pass; Group A tests also carry `@pytest.mark.e2e` (to exclude
   from `make test`) but make no API calls. Any conftest skip logic for a missing real
   key must target groups B–H only — not `@pytest.mark.e2e` at large.

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
      _common.py                    # fpdf2 helpers + determinism setup + BBOX_ASSERTIONS_VIABLE constant
      calibration_notes.md          # Phase 0 results: COORD_SCALE, DPI finding, decision
      grp_a_native.py               # A1–A3
      grp_b_classifier.py           # B1–B2
      grp_c_blocktypes.py           # C1–C9
      grp_d_metadata.py             # D1–D5
      grp_e_multipage.py            # E1–E2
      grp_f_hierarchy.py            # F1–F4 (pre-built state; no PDF generator needed; not tracked in manifest.json)
      grp_g_layout.py               # G1
      grp_h_edge.py                 # H1
      generate_all.py               # CLI + hash-check function (session fixture lives in tests/integration/conftest.py)
    pdfs/                           # .gitignore — regenerated at session start if missing
      [not tracked in git]
    golden/                         # committed — JSON, human-readable diffs
      grp_a_valid_1page.json
      grp_b_invoice.json
      grp_c_paragraph.json
      ...
    manifest.json                   # committed — SHA-256 per generator; detects stale goldens (grp_f excluded — no PDF output)
  integration/
    conftest.py                     # session-scoped autouse fixture: invokes generate_all.py hash-check at session start
    test_synthetic_grp_a.py         # native extraction
    test_synthetic_grp_b.py         # classifier
    test_synthetic_grp_c.py         # block-type extraction
    test_synthetic_grp_d.py         # metadata schemas
    test_synthetic_grp_e.py         # multi-page burst
    test_synthetic_grp_f.py         # hierarchy (narrow: direct function calls)
    test_synthetic_grp_g.py         # layout / reading order
    test_synthetic_grp_h.py         # edge cases
    test_full_chain.py              # no mocks, all nodes real, integration chain
    _compare.py                     # HierarchyRule NamedTuple; mock factories: _make_tool_use_response,
                                    # _valid_block, _make_relation_response; assertion helpers:
                                    # assert_blocks_match, assert_table_data,
                                    # assert_hierarchy_structure, assert_nearest_heading_parent
```

`tests/fixtures/pdfs/` is in `.gitignore`. At pytest session start, a session-scoped
autouse fixture in `tests/integration/conftest.py` invokes `generate_all.py`'s
hash-check function; a missing file or generator-hash mismatch triggers regeneration
and updates both the PDF and the manifest entry. Generator scripts, golden JSON files,
and `manifest.json` are all committed; PDFs are not.

`make fixtures [GRP=x]` regenerates the specified group (or all groups), updates golden
files, and updates `manifest.json`. Requires adding a `fixtures` target to `Makefile`
with optional `GRP` parameter.

---

## Coordinate system and bbox calibration

The extraction prompt tells Claude: `"Coordinates must follow [ymin, xmin, ymax, xmax] order."` Claude
produces **integers** in whatever coordinate space it uses internally when reading the PDF natively.
That space is not publicly documented — it could be typographic points (1 pt = 1/72 in), PDF user units,
or pixel coordinates at an implicit render DPI.

fpdf2 writes PDFs with origin at **top-left** (y increases downward), matching Claude's reading
convention exactly. A block placed at fpdf2 position `(x_mm, y_mm)` with size `(w_mm, h_mm)` maps
to Claude's expected output as a uniform scale — **no axis flip required**:

```
ymin_claude ≈ y_mm  × COORD_SCALE
xmin_claude ≈ x_mm  × COORD_SCALE
ymax_claude ≈ (y_mm + h_mm) × COORD_SCALE
xmax_claude ≈ (x_mm + w_mm) × COORD_SCALE
```

`COORD_SCALE` is a single unknown scale factor (Claude-units per mm), determined by Phase 0
calibration. If Claude reads PDF points directly, `COORD_SCALE ≈ 2.835` (72 pt ÷ 25.4 mm/in).
If Claude renders to pixels at 144 DPI, `COORD_SCALE ≈ 5.67`. The unit is irrelevant — only
the empirically measured factor matters.

### Calibration run (Phase 0)

Before generating any golden files, run C1 (single paragraph at a known mm position) through
the pioneer_parser only to save cost: mock the classifier by patching
`src.nodes.classifier_node._classify` to return `"baseline_core"`, and mock the hierarchy by
patching `src.nodes.hierarchy_node._call_api` with `AsyncMock(return_value=_make_relation_response([]))`.
Run it 3 times and compare returned `coordinates` against the known mm placement:

- If `coordinates ≈ mm_values × k` for consistent k across 3 runs → `COORD_SCALE = k`.
- If values vary widely across 3 runs → `BBOX_ASSERTIONS_VIABLE = False`.

A second check once D1 and G1 fixtures exist (Development Phase 4) verifies scale
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

For **D, E** (single-column, stable block count), the geometric sort order is stable
and blocks can be matched positionally: `output[i]` is compared to `golden[i]`.
For **C** (single-column, variable block count), block count is deliberately asserted as
`>= minimum` because the model may split or merge content. Use **scan-based** matching:
assert that each expected text is present in *some* block, not that `output[i]` equals
`golden[i]`. `assert_blocks_match` is not used for C tests.
Group A does not use block matching at all — A assertions check `total_pages` and
`pdf_hash` only. Group B only asserts `document_type` — no block matching.
Group F uses structural hierarchy assertions (`assert_hierarchy_structure`,
`assert_nearest_heading_parent`), not positional block matching.

For **G1** (two-column layout), positional matching is unreliable because the sort
interleaves columns. Use set-based matching: for each expected text string, assert that
*some* block in the output contains it. Column ordering is verified separately (all
L-prefixed blocks before all R-prefixed blocks in `structured_payload`).

For **H1** (blank page), no positional matching is attempted. The test only asserts
pipeline completes without exception, `len(blocks) <= 1`, and (if one block is returned)
`len(block["text"].strip()) < 30`.

### Pipeline output access

In every group test (B, C, D, E, F, G, H) and the full-chain test, output is accessed as:

```python
graph  = build_app()
result = await graph.ainvoke(initial_state)   # integration tests invoke the graph directly
blocks  = result["hierarchical_document_tree"]["structured_payload"]
doc_type = result["hierarchical_document_tree"]["document_type"]
warnings = result["hierarchical_document_tree"]["extraction_warnings"]
```

`structured_payload` is the sorted, deduplicated block list with `parent_id` assigned.
Pass it as the `actual` argument to `assert_blocks_match` and as the `blocks` argument
to `assert_hierarchy_structure` / `assert_nearest_heading_parent`.

### `_compare.py` helper spec

```python
from typing import NamedTuple

class HierarchyRule(NamedTuple):
    child_type: str                    # block["type"] to match
    expected_parent_type: str | None   # None asserts parent_id is None (top-level)

# --- Mock factories (shared across grp_b through grp_g tests) ---

def _make_tool_use_response(blocks: list) -> MagicMock:
    """Mock factory for worker/pioneer node API response. Move here from
    test_graph_pipeline.py so grp_b tests can import without cross-test-file imports."""

def _valid_block(page: int = 1) -> dict:
    """Minimal valid block for use as a worker mock return value in grp_b tests.
    Must include all required block fields (block_id, type, text, bbox, is_continued,
    metadata) and must pass baseline_core, invoice, and scientific_paper schema
    validation so that pioneer_validation_route does not trigger retries in B tests."""

def _make_relation_response(relations: list) -> MagicMock:
    """Mock factory for hierarchy node API response. Move here from test_graph_pipeline.py
    so grp_c through grp_g tests can import without cross-test-file imports."""

# --- Assertion helpers ---

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
    Each rule applies to ALL blocks of the given child_type, not just some.
    When expected_parent_type is None, asserts block["parent_id"] is None (top-level).
    When non-None, looks up the parent by parent_id and asserts parent["type"] == expected_parent_type.
    """

def assert_table_data(block: dict, expected_rows: int, expected_cols: int,
                      header_row_count: int = 1,
                      expected_values: list[str] | None = None) -> None:
    """Validates metadata.table_data dimensions and header flags.
    expected_rows is the TOTAL row count including header rows (e.g., 1 header + 3 data = 4).
    header_row_count rows starting from index 0 must have is_header=True; the rest False.
    When expected_values is provided, each string must appear in at least one cell's value field."""

def assert_nearest_heading_parent(blocks: list[dict]) -> None:
    """
    For each paragraph block, asserts its parent_id points to the block_id of the
    nearest preceding heading in the sorted block list. Requires blocks to already
    be in geometric sort order (as returned by the pipeline).
    Raises AssertionError if any paragraph's parent is not its nearest heading.
    A paragraph with no preceding heading triggers AssertionError — the fixture
    must ensure at least one heading appears before the first paragraph.
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
- Block with `is_continued=true` → the first block on the next page is its child.
  **Not currently asserted** — E3 is suspended because the extraction prompt does not
  instruct the model to set `is_continued`, so the field is always `false` in practice.

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
    "model_version": "claude-sonnet-4-6",
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
- `meta.model_version` is set at generation time from `src.config.MODEL`. When `MODEL`
  changes, Phase 0 calibration must re-run and all golden files must be regenerated.
- `expected.blocks` omits `block_id`, `parent_id`, and `is_continued` (E3 suspended).
- No `block_count` field — count assertions use `len(blocks) >= minimum` in tests.
- `coordinates` key may be omitted when `BBOX_ASSERTIONS_VIABLE = False`.

### Golden file creation workflow

Generator scripts write the golden file **at generation time** using design intent —
they do NOT run the model. The generator places text on the page and writes the
corresponding `type` and `text` values it expects the model to return:

```
Generator writes text "Hello" as a paragraph  →  golden: {"type": "paragraph", "text": "Hello"}
```

This means golden files are "expected-by-design", not "captured from a model run".
**First-run failures are expected and correct**: if the model returns a different `type`
than the generator expected, the test fails, and you update the golden file to match
the real model output (after judging whether the model's classification is acceptable).

**Exception — `make fixtures`** (used to regenerate after prompt/model changes): this
regenerates both the PDF and the golden file, using the generator's original design
intent again. It does NOT auto-capture model output. Manually re-run affected tests
and update golden files if the new model output differs from design intent.

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
`src.nodes.classifier_node._classify`. After that patch fires, `window_parser_node`
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
        # Required per-block fields: block_id (str), type (str), text (str),
        # bbox: {"page_number": int, "coordinates": [ymin, xmin, ymax, xmax]}
    ],
    "extraction_warnings": [],           # merged into output warnings
}
result = await layout_hierarchy_agent_node(state)
blocks = result["hierarchical_document_tree"]["structured_payload"]
# Pass `blocks` to assert_hierarchy_structure / assert_nearest_heading_parent
```

> `is_continued` is not a required field in the pre-built block dict — the node reads
> it via `b.get("is_continued", False)` and sends the defaulted value in the LLM manifest.
> With single-page fixtures where `is_continued` is absent (defaults to `false`),
> the cross-page child rule (rule 2) never fires. This is correct behaviour for F tests.

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
- Reuses the B1 PDF (1-page invoice); no new PDF needed
- Runs `build_app()` with all nodes real
- Asserts (see §Phase 4 for key paths): `document_type == "invoice"`, at least one
  `table` block with `table_data` populated, no "failed schema validation" in warnings
  (tolerates benign orphan warnings; catches schema degradation)
- Tagged `@pytest.mark.e2e @pytest.mark.integration_chain`
- Lives in `tests/integration/test_full_chain.py`

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
| A3 | Encrypted PDF (pypdf-generated) | `pytest.raises(ValueError)` |

> A3 uses a programmatically encrypted PDF (`pypdf.PdfWriter` with encryption). This
> tests the actual pypdf encryption detection, which the existing unit test bypasses via
> `mocker.patch("get_page_count")`. No API call is made for any A test.

---

### Group B — Classifier accuracy (1 Claude call per test)

Node under test: `classifier_node`. All other nodes mocked (not full e2e — see §Design
principles and §Narrow tests for the rationale).

**Mock setup for B tests:**
- `native_extractor_node` runs for real (deterministic pypdf calls on real PDF).
- `src.nodes.classifier_node.encode_pdf_async`: **NOT mocked** — classifier must read
  real PDF bytes to classify.
- `patch("src.nodes.worker_node._call_api", new=AsyncMock(return_value=_make_tool_use_response([_valid_block(1)])))` — prevents a real pioneer API call.
- `patch("src.nodes.hierarchy_node._call_api", new=AsyncMock(return_value=_make_relation_response([])))`.
  > With `_valid_block(1)` returning exactly one block, the hierarchy node's single-block
  > optimisation (`if len(sorted_blocks) > 1`) skips the `_call_api` call entirely. The patch
  > is a safety measure in case `_valid_block` is later changed to return multiple blocks.

| ID | PDF content | Pages | Expected `document_type` |
|---|---|---|---|
| B1 | Company header, "INVOICE #001", billing table, line items | 1 | `invoice` |
| B2 | Paper title in large font, two authors, "Abstract" heading, body text, "DOI:" line | 1 | `scientific_paper` |

> B3 (ambiguous → fallback) is removed. The fallback path is already exhaustively
> tested in `test_classifier_node.py:test_unknown_falls_back`. An e2e fixture for
> ambiguous content is unreliable because we can't control the model's response.

---

### Group C — Block-type extraction (1–2 Claude calls per test)

Node under test: `window_parser_node` (pioneer page, 1-page PDFs so burst never fires).
Classifier is mocked by patching `src.nodes.classifier_node._classify` to return
`"baseline_core"` — `encode_pdf_async` still runs (real PDF bytes are computed but ignored
by the mock). Hierarchy is mocked by patching `src.nodes.hierarchy_node._call_api` with
`AsyncMock(return_value=_make_relation_response([]))` (empty `relations` list — import
`_make_relation_response` from `tests/integration/_compare.py`). All blocks fall through to the existing orphan-fallback branch
and receive `parent_id = null`; orphan warnings are emitted but not asserted in C tests.
Deduplication and sort still run. One PDF per block type.

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
> misclassification. Before committing, run each once against the real model — if the
> target type label is not returned on that first run, remove the fixture immediately
> (see Risk 1). Do not invest in a multi-run failure-rate study for an unvalidated
> fixture.
>
> C7 asserts only presence; structured `table_data` validation is in D1 where the
> invoice schema enforces structure. In C7 with `baseline_core`, metadata is open
> and the schema won't catch malformed table_data.
>
> C8 is a text-presence test, not a figure-detection test. It passes if the model
> returns ANY block that mentions "Figure 1:" — even if it classifies the grey rectangle
> as a `paragraph`. This is intentional: detecting `figure` type reliably on synthetic
> content is unreliable (see C5/C6 note). C8 only confirms the content is not silently
> dropped.
>
> C9 replaces H2 (long paragraph), which is a C extension, not a distinct concern.

---

### Group D — Schema-specific metadata (1–2 Claude calls per test)

Node under test: `window_parser_node` + schema validation in `pioneer_validation_route`.
Classifier is mocked by patching `src.nodes.classifier_node._classify` to return
the target doc type (see Group C for rationale). Hierarchy is mocked by patching
`src.nodes.hierarchy_node._call_api` with `AsyncMock(return_value=_make_relation_response([]))`
(empty relations — see Group C for rationale). 1-page PDFs.

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
Classifier is mocked by patching `src.nodes.classifier_node._classify` to return
`"baseline_core"` (see Group C for rationale). Hierarchy is mocked by patching
`src.nodes.hierarchy_node._call_api` with `AsyncMock(return_value=_make_relation_response([]))`
(empty relations — see Group C for rationale). `src.nodes.worker_node._call_api` is **NOT mocked** — pioneer and all burst workers
make real LLM calls, producing blocks with correct `bbox.page_number` values. This is
what makes E different from B (which mocks the worker to isolate the classifier).
Deduplication and sort still run, so the `block_id` uniqueness assertion reflects real
pioneer/worker output after merge and dedup.

| ID | PDF | Assertions |
|---|---|---|
| E1 | 2-page doc (1 paragraph per page, distinct text per page) | At least one block with `bbox.page_number == 1` AND at least one with `bbox.page_number == 2`; no duplicate `block_id` values |
| E2 | 5-page doc (1 paragraph per page) | For each page 1–5: at least one block with `bbox.page_number == page` present; no duplicate `block_id` |

> `len(blocks) == N` is not asserted (model may split or merge content across pages).
> The assertion is "every page contributed at least one block."
>
> Because hierarchy is mocked with empty relations, every block receives `parent_id = null`
> via the orphan-fallback branch, generating one warning per block. E tests do not assert
> `extraction_warnings`; the orphan noise is expected and harmless.
>
> E3 (`is_continued`) is **suspended** until the extraction prompt explicitly instructs
> the model to set `is_continued`. The current prompt has no such instruction; the field
> defaults to `false` and E3 would always fail.

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
| F2 | `[heading, paragraph, paragraph, table]` | paragraphs + table under heading | all three blocks' `parent_id` → heading's `block_id`; use `assert_hierarchy_structure` with rules `[HierarchyRule("paragraph", "heading"), HierarchyRule("table", "heading")]` |
| F3 | `[title, heading, paragraph]` | title at root; heading at root; paragraph under heading | `assert_hierarchy_structure(blocks, [HierarchyRule("title", None), HierarchyRule("heading", None), HierarchyRule("paragraph", "heading")])` |
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
>
> **F4 does not assert heading `parent_id` values** — that heading-A and heading-B are
> root-level is not checked by `assert_nearest_heading_parent`. This is acceptable:
> the heading-root rule is already asserted in F1 (heading.parent_id == null) and F3
> (HierarchyRule("heading", None)). F4's distinct value is paragraph disambiguation.

---

### Group G — Layout / reading order (1 Claude call)

Node under test: `window_parser_node` (extraction quality on multi-column layout).
`geometric_pre_sorter` is already deterministically unit-tested. What G tests is whether
the extractor assigns `xmin` values that correctly distinguish columns, allowing the
sorter to order them correctly. G2 is dropped (duplicates existing sorter unit tests).

Classifier is mocked by patching `src.nodes.classifier_node._classify` to return
`"baseline_core"` (see Group C for rationale). Hierarchy is mocked by patching
`src.nodes.hierarchy_node._call_api` with `AsyncMock(return_value=_make_relation_response([]))`
(same pattern as C and E). G1 is 1-page so burst does not fire.

Tests import `COLUMN_BUCKET_PX` from `src.config` and document the column placement
calculation explicitly.

| ID | PDF content | Assertions |
|---|---|---|
| G1 | 2-column A4 (left column at x_mm ≈ 12.7 mm → Claude xmin ≈ 36 → bucket 0; right column at x_mm ≈ 111 mm → Claude xmin ≈ 315 → bucket 6, assuming COORD_SCALE ≈ 2.835): left has "L1", "L2", "L3"; right has "R1", "R2", "R3" | (1) All blocks with `xmin // COLUMN_BUCKET_PX == 0` appear before all blocks with `xmin // COLUMN_BUCKET_PX >= 1` in `structured_payload`; `COLUMN_BUCKET_PX` imported from `src.config`; (2) "L1", "L2", "L3" texts are each in some block; (3) "R1", "R2", "R3" texts are each in some block |

> **Why `bbox.xmin`, not text prefix:** using text-prefix to identify column membership
> is circular — it can't detect bleed. Position-based assertion (xmin bucket) is
> independent of text content. If the model bleeds L-text into an R-xmin block,
> assertion (1) catches the ordering failure. Assertions (2) and (3) confirm no
> content was lost.
>
> **Why buckets, not `page_width/2`:** `xmin < page_width/2` requires knowing `page_width`
> in Claude's coordinate space, which is only available post-calibration. Bucket membership
> (`xmin // COLUMN_BUCKET_PX`) uses the same arithmetic as `geometric_pre_sorter` itself
> and requires no scale factor. The two columns are separated by ≈ 279 pt — even with ±20%
> coordinate variance, the left column (≈ 36 pt) stays in bucket 0 and the right column
> (≈ 315 pt) stays in bucket ≥ 5. G1 works regardless of whether `BBOX_ASSERTIONS_VIABLE`
> is set.

---

### Group H — Graceful degradation (1 Claude call)

Reduced to H1 only. H2 (long paragraph) moved to C9.

Classifier is mocked by patching `src.nodes.classifier_node._classify` to return
`"baseline_core"` (see Group C for rationale). Hierarchy is mocked by patching
`src.nodes.hierarchy_node._call_api` with `AsyncMock(return_value=_make_relation_response([]))`.
H1 is a smoke test for the full pipeline path; mocking classifier and hierarchy keeps the
focus on whether the pipeline handles blank input without crashing.

| ID | PDF content | Assertions |
|---|---|---|
| H1 | 1 blank white page (no text, no objects) | Pipeline completes without exception; `len(blocks) <= 1`; if a block exists, `len(block["text"].strip()) < 30` |

> H1 is explicitly a smoke test: it checks the pipeline doesn't crash on degenerate
> input. It does not assert meaningful extraction quality.

---

## Phased delivery

### Phase 0 — Calibration (prerequisite, no tests written yet)

- Implement `_common.py` and C1 generator only; add `tests/fixtures/pdfs/` to `.gitignore`
- Patch `src.nodes.classifier_node._classify` → `"baseline_core"` and `src.nodes.hierarchy_node._call_api` → `AsyncMock(return_value=_make_relation_response([]))`; run only pioneer_parser on C1 PDF — 3 times
- Record returned `coordinates` each run; derive `COORD_SCALE` or flag as non-viable
- Commit `calibration_notes.md` with raw numbers and decision
- Set `COORD_SCALE = <k>` or `BBOX_ASSERTIONS_VIABLE = False` in `_common.py`
- Once D1 and G1 fixtures exist (Development Phase 4), repeat the cross-content-type scale check; if inconsistent, override to `BBOX_ASSERTIONS_VIABLE = False` and run `make fixtures` to update all Phase 2 golden files — their `meta.coord_scale` must be changed from the numeric value to `false`

### Phase 1 — Foundation: Groups A, B, C + infrastructure

- `tests/fixtures/` directory structure; `tests/fixtures/pdfs/` in `.gitignore`
- `generate_all.py` CLI: hash-check function compares generator SHA-256 against `manifest.json`; regenerates PDFs on missing file or hash mismatch; updates manifest entry. The session-scoped autouse fixture that invokes this function must be defined in `tests/integration/conftest.py` — pytest does not auto-discover fixtures from non-conftest files in `generators/`
- `_common.py` fpdf2 helpers: `make_pdf()` factory (FPDF subclass with pinned creation date and A4 defaults), `draw_text()`, `draw_table()`, `draw_figure_rect()` helpers; `COORD_SCALE` / `BBOX_ASSERTIONS_VIABLE` constants
- Generators and golden files for A1–A3, B1–B2, C1–C9
- `tests/integration/_compare.py`: mock factories `_make_tool_use_response`, `_valid_block`,
  `_make_relation_response`; assertion helpers `assert_blocks_match` (`normalize_text=True` default),
  `assert_table_data`
- Integration tests for groups A, B, C
- `make fixtures [GRP=x]` target; `make test-e2e` shortcut; update existing `make test` command to add `-m "not e2e"` so synthetic tests are excluded from the default run
- **`tests/conftest.py`**: change `os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake"` to `os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")` — without this, any real key in the shell is overwritten and all B–H API calls fail with authentication errors
- **Register all pytest markers in `pyproject.toml`**:
  `e2e`, `grp_a`, `grp_b`, `grp_c`, `grp_d`, `grp_e`, `grp_f`, `grp_g`, `grp_h`,
  `integration_chain`
- **API key skip guard in `tests/integration/conftest.py`**: add a **function-scoped**
  autouse fixture (no `scope=` argument, so it runs once per test) that calls
  `pytest.skip(...)` if `ANTHROPIC_API_KEY` is unset or equals `"sk-test-fake"` —
  but only when the current test is marked with a group B–H marker. Check via
  `request.node.get_closest_marker("grp_b") or ... request.node.get_closest_marker("grp_h")`.
  Do NOT skip on `@pytest.mark.e2e` alone; Group A carries that marker but makes
  no API calls. A session-scoped fixture cannot skip individual tests and must not
  be used here.

### Phase 2 — Schema metadata: Group D

**Prerequisite (Risk 2):** confirm the extraction prompt has been updated to explicitly
request optional scientific_paper subfields (`bibliographic`, `section`, `reference`,
`figure_table`) and that a single test run confirms at least one subfield is populated.
Do not begin Phase 2 without this confirmation.

- Generators and golden files for D1–D5
- No new shared helper needed for optional metadata — D2–D5 use inline conditional checks: `if block.get("metadata", {}).get("<subfield>"): assert ...; else: assert "<expected text>" in some_block["text"]`
- Integration tests for group D

### Phase 3 — Pipeline behavior: Groups E and F

- Multi-page generators (E1, E2); E3 remains suspended pending prompt update
- Hierarchy tests (F1–F4) as **narrow function calls** (no PDF; pre-built state)
- `HierarchyRule` NamedTuple, `assert_hierarchy_structure`, and `assert_nearest_heading_parent` added to `_compare.py`
- Integration tests for group E; narrow tests for group F

### Phase 4 — Layout, edge cases, and full-chain

- Two-column generator (G1); edge-case generator (H1)
- Integration tests for groups G and H
- **Full-chain integration test** (`tests/integration/test_full_chain.py`):
  no mocks, reuses the B1 PDF (1-page invoice), all nodes real, asserts:
  `result["hierarchical_document_tree"]["document_type"] == "invoice"`;
  at least one block in `result["hierarchical_document_tree"]["structured_payload"]`
  with `type=="table"` and `metadata.table_data` populated;
  `not any("failed schema validation" in w for w in result["hierarchical_document_tree"]["extraction_warnings"])`
  (tolerates benign orphan warnings; catches schema degradation; see Risk 8 if `table_data` is unreliable)
- Update README with `make test-e2e GRP=x` usage

---

## Remaining open questions / risks

The following risks remain open.

1. **C5 and C6: validate with a real model call before committing golden files.** The
   multi-signal redesign assumes the visual patterns (7 pt font + horizontal rule +
   superscript for C5; grey background + narrow column for C6) trigger the target block
   type labels on `claude-sonnet-4-6`. There is no evidence in the codebase that they do.
   Before committing Phase 1, run C5 and C6 once against the real model and confirm the
   target type label is returned. Only then write golden files and commit. If the target
   label is not returned on that first run, remove the fixture immediately — do not invest
   in a 10-run failure-rate study. Any test expected to fail 1 run in 5 does not belong
   in the suite.

2. **D-group optional metadata: prompt update is a Phase 2 prerequisite, not an
   afterthought.** The scientific_paper schema's optional subfields (`bibliographic`,
   `section`, `reference`, `figure_table`) will not be populated unless the extraction
   prompt explicitly requests them. This is the expected outcome with the current prompt —
   not a low-probability risk. If D2–D5 are built before the prompt is updated, they will
   consistently degrade to text-presence assertions (C-level coverage under a D-level name),
   wasting the phase. **Phase 2 should not begin until the extraction prompt has been
   updated to request these subfields and the change confirmed on a single D-group test run.**

3. **E3 permanently untested.** `is_continued` is a named field in the block schema with
   no e2e test coverage and no scheduled prompt fix. The practical status is: this field
   is permanently dark in this test suite. This is a known coverage gap, not a deferred
   task with a timeline.

4. **F4 flakiness: remove rather than loosen.** If F4 fails > 30% across 10 runs, remove
   it entirely and document it as evidence that the hierarchy prompt needs refinement for
   multi-heading disambiguation. Do not retain it with the loosened assertion "paragraph
   has SOME parent_id" — that assertion passes even if every paragraph is assigned to the
   wrong heading. A test with near-zero signal occupies a test slot and provides false
   assurance.

5. **Golden file staleness: `manifest.json` does not detect prompt changes.** The manifest
   tracks generator script hashes and detects stale PDFs. It does not track the extraction
   prompt, hierarchy prompt, or Pydantic schemas. A prompt change that degrades model output
   will not trigger any manifest warning. Developers must manually run `make fixtures` after
   any prompt or schema change. Additionally, the diff review criterion "semantically
   reasonable diff means the change is safe" is not actionable — the review should ask:
   does every changed field change in the expected direction? Any unexpected regression
   (e.g., `type: "heading"` → `type: "paragraph"`) fails the review regardless of diff size.

6. **Cost.** Expected API calls per full suite run: A: 0, B: 2, C: 9, D: 5,
   E: 7 (classifier mocked; E1 = pioneer + 1 burst worker = 2; E2 = pioneer + 4 burst
   workers = 5), F: 4 (narrow, no PDF), G: 1, H: 1, full-chain: 3 = **32 calls**.
   Retry overhead ≈ 0–2 (retries fire on schema validation failures; synthetic clean PDFs
   should not trigger them). Phase 0 calibration adds 3 calls (one-time). Cost-per-call
   varies significantly: classifier calls (~2 K tokens) are much cheaper than pioneer/worker
   calls (~10–15 K tokens with full schema in tools definition). At rough average ~$0.02/call:
   ~$0.64 per run, but token-count variance could shift this 2–3× in either direction.
   Nightly CI is appropriate; `pytest -m "e2e and not (grp_d or grp_e)"` for cheaper smoke
   runs.

7. **Model version drift.** Golden files are written against `claude-sonnet-4-6` (from
   `src/config.py`). When `MODEL` is updated, golden diffs will be widespread. Any `MODEL`
   change must be followed immediately by `make fixtures` and a full golden diff review
   before merging. The golden file `meta` block has a `model_version` field set at
   generation time from `src.config.MODEL`; when `MODEL` changes, Phase 0 calibration
   must re-run before any other golden file work begins.

8. **B1 PDF adequacy for the full-chain `table_data` assertion.** B1 is a simple 1-page
   invoice with a billing table. If the model does not reliably populate `table_data` on
   this PDF, the full-chain test fails non-deterministically. If this happens: either (a)
   update B1's generator to use a more explicit multi-row table with a distinct header row,
   or (b) fall back to the weaker "table block present" assertion and note the limitation.

---

## Running the test suite

```bash
# Regenerate all fixture PDFs and golden files from scratch
make fixtures

# Regenerate only one group
make fixtures GRP=c

# Run only the synthetic e2e tests (requires ANTHROPIC_API_KEY)
pytest tests/integration/ -m e2e -v

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
_v7 — 2026-06-02 20:00 — generator library switched from reportlab to fpdf2: Design Principle 1 updated (fpdf2, determinism via set_creation_date); _common.py spec updated (make_pdf factory, draw_text, draw_table, draw_figure_rect); coordinate section rewritten — axis-flip formula eliminated, fpdf2 top-left matches Claude convention, calibration simplified to COORD_SCALE × mm; D/A calibration sub-section updated (top-left concern resolved, stale formula removed, three-fixture-in-Phase-0 contradiction fixed); binary-PDF storage resolved as approach 3 (regenerate + manifest hash): manifest.json added to committed artifacts, directory layout and Phase 1 checklist updated, generate_all.py spec updated with hash-check logic; G1 column position labels corrected (mm generator coords shown, "pt" label removed)_  
_v8 — 2026-06-02 20:30 — D/A section removed (all 24 entries fully applied to plan body); open questions updated: stale F4/F5 reference fixed (F4 figure-caption removed, F5 → F4 multi-heading), §D/A reference removed, manifest.json added to golden-file review step; cost estimate F:5 → F:4; v5 restored to header_  
_v9 — 2026-06-02 21:00 — pass 4 D/A: A3 classifier-mock assertion removed (inapplicable in direct-call context); C and E hierarchy mocks clarified to empty-relations pattern (avoids dynamic block_id requirement; existing _make_relation_response helper reused); E classifier mock documented explicitly; G1 column assertion rewritten to bucket-based (no calibration dependency; works when BBOX_ASSERTIONS_VIABLE=False); G1 note explains why buckets beat page_width/2; assert_hierarchy_structure "all blocks" semantics added; grp_f excluded from manifest.json (no PDF output); integration-gap section aligned with Phase 4 (reuses B1, softer warnings check); full-chain table_data assertion resolved (stronger); pytest "run all e2e" command fixed (test_full_chain.py was excluded by glob); all 6 risks rewritten; 2 new risks added (model version drift; B1 PDF adequacy)_  
_v10 — 2026-06-02 21:30 — pass 5 (automated /refine-plan): 8 MEDIUM resolved: "tests fallback path" wording corrected to "cannot test baseline_core"; e2e marker clarified as API-key-required not no-mocks; A and F removed from positional-matching group (A has no blocks, F uses structural assertions); _make_relation_response moved to _compare.py spec with shared-helper note; model_version field added to golden file format + meta note; Group B mock setup fully specified (NOT mock classifier encode_pdf_async, DO mock worker AsyncAnthropic and hierarchy); C5/C6 note updated to match Risk 1 run-once-first guidance; Group D hierarchy mock specified as _make_relation_response([]); Group E orphan-warning note added; Phase 0 classifier mock return value specified; Phase 2 prompt prerequisite gate added; H1 text-length threshold 10→30; C8 text-presence intent explicitly documented_  
_v11 — 2026-06-02 21:45 — pass 6 (automated /refine-plan): 1 MEDIUM + 1 LOW: Group C stale reference to test_graph_pipeline.py corrected (import from _compare.py); Group G mock setup added (classifier + hierarchy mocked, same pattern as C/E)_  
_v12 — 2026-06-02 22:00 — pass 7 (automated /refine-plan): 2 MEDIUM + 2 LOW: _make_tool_use_response and _valid_block added to _compare.py spec (same shared-import problem as _make_relation_response); Group H mock setup added; HierarchyRule defined as NamedTuple in _compare.py spec; F2 assertion now explicitly lists both HierarchyRule entries (paragraph + table)_  
_v13 — 2026-06-02 22:30 — pass 8 (automated /refine-plan): 1 HIGH + 3 MEDIUM + 2 LOW: conftest fake-key overwrite documented as Phase 1 change (setdefault fix); generate_all.py session fixture must live in tests/integration/conftest.py; e2e marker semantics clarified (excluded-from-make-test, not always requires-key; Group A exception documented); assert_table_data extended with expected_values param; F state spec annotated with required block fields; assert_nearest_heading_parent edge case specified_  
_v14 — 2026-06-02 22:45 — pass 9 (automated /refine-plan): 1 MEDIUM + 1 LOW: directory layout comment updated (generate_all.py is CLI + hash-check function; fixture lives in conftest); directory prose updated to say conftest invokes generate_all.py; HierarchyRule None case documented_  
_v15 — 2026-06-02 23:00 — pass 10 (automated /refine-plan): 1 LOW: tests/integration/conftest.py added to directory layout_  
_v16 — 2026-06-03 — remaining LOWs resolved: F3 uses assert_hierarchy_structure with HierarchyRule(None) (exercises the None case); Phase 2 optional-metadata helpers clarified as inline conditional checks; make test updated with -m "not e2e" in Phase 1 checklist_  
_v17 — 2026-06-03 — pass 11 (automated /refine-plan): 1 MEDIUM: "Phase 1" calibration label renamed "Development Phase 4" in both calibration prose and Phase 0 checklist to avoid naming collision with development phases_  
_v18 — 2026-06-03 — coherence review pass 1: 3 MEDIUM + 5 LOW fixed: structured_payload access path added (pipeline output section + F state spec + full-chain assertions); E mock setup now explicitly states worker_node is NOT mocked; Phase 3 checklist adds assert_hierarchy_structure alongside assert_nearest_heading_parent; is_continued rule 2 added to Documented Rules (suspended pending E3); B1/B2 page count column added; Phase 1 _compare.py checklist lists all 5 helpers incl. mock factories; Phase 0 bbox-invalidation rollback note for meta.coord_scale; F state spec explains is_continued default behaviour; B removed from positional-matching list; integration-gap assertion cross-references Phase 4; pipeline output comment clarified_  
_v19 — 2026-06-03 — coherence review pass 2 (ambiguity + determinism): 3 MEDIUM fixed: classifier mock changed from AsyncAnthropic-class patch (3-level mock chain, unspecified) to `_classify` function patch (unambiguous, consistent across C/D/E/G/H); C test matching strategy clarified as scan-based (not positional) due to variable block count — D/E/H remain positional; golden file creation workflow section added (design-intent pre-written, not model-captured; first-run failures expected)_  
_v20 — 2026-06-03 — coherence review pass 3 (coverage + missing parts): 4 LOW fixed: stale AsyncAnthropic reference in narrow-tests "identity problem" paragraph corrected to _classify; _valid_block docstring extended with schema-compatibility requirement; assert_table_data docstring clarified (expected_rows = total rows incl. headers); F4 note added (heading parent_ids not asserted by design — covered by F1/F3); Phase 1 API key skip-guard approach specified_  
_v21 — 2026-06-03 — coherence review pass 4 (implicit assumptions + explicit instructions): 5 MEDIUM + 4 LOW fixed: H removed from positional-matching group (H1 never uses positional matching); worker/hierarchy mocks changed from AsyncAnthropic class patch (3-level chain, unspecified) to _call_api function patch throughout (B, C, D, E, G, H); HierarchyRule NamedTuple added as standalone class definition in _compare.py spec with valid Python syntax; API key skip guard corrected from session-scoped to function-scoped with explicit request.node.get_closest_marker check; Group B document_type access path added to pipeline output section; Phase 0 calibration mock targets made explicit; B hierarchy mock no-op behaviour documented (single-block optimisation); _compare.py directory comment updated to list mock factories_  
_v22 — 2026-06-03 — coherence review pass 5 (final cleanup): 3 LOW fixed: duplicate H1 matching description removed; Phase 3 checklist adds HierarchyRule NamedTuple; H1 assertion table corrected to block["text"] (dict); Risk 7 stale language corrected (model_version field already in spec; calibration re-run ordering made explicit)_  
