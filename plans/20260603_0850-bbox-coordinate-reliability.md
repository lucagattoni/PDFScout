# Bbox Coordinate Reliability — Plan

_Created: 2026-06-03 08:50_
_Updated: 2026-06-03 15:30 · v2: linear-fit decision criteria, Phase 1 calibration snippet, generator placement, G1 adds-to not replaces, check_xmax signature, COORD_OFFSET_X, concrete Risk-6 threshold, Risk-7 y-axis single-point_
_Updated: 2026-06-03 16:00 · Phase 1 executed and failed — plan closed; see calibration_notes.md §Phase 1_

**Plan status: CLOSED** — Phase 1 failed. No further phases executed. `BBOX_ASSERTIONS_VIABLE = False` unchanged.

---

## Goal

Enable reliable bounding box assertions in the synthetic test suite by:
1. Characterising Claude's actual coordinate system empirically (Phase 1)
2. Reducing `xmax` ambiguity via prompt and schema description changes (Phase 2)
3. Conditionally enabling bbox assertions based on empirical outcomes (Phase 3)

The existing 28/28 e2e tests must continue to pass throughout. Any change that causes a
regression is reverted, not worked around.

---

## Problem statement

Phase 0 calibration (`calibration_notes.md`) measured a single text block ("The quick
brown fox...") placed at `x_mm=20, y_mm=50, w_mm=170, h_mm=8` and got:

```
Returned coordinates: [ymin=107, xmin=71, ymax=124, xmax=312]
```

Scale ratios against declared mm positions:
- y-axis: `ymin/50 = 2.14`, `ymax/58 = 2.138` → **consistent, k_y ≈ 2.14**
- x-axis: `xmin/20 = 3.55`, `xmax/190 = 1.642` → **inconsistent**

Two distinct problems are conflated in the existing analysis:

**Problem A — Dual-scale system**: `k_x ≈ 3.55` and `k_y ≈ 2.14` are different. Even
if `xmax` were fixed, a single `COORD_SCALE` constant cannot convert mm positions to
Claude coordinates for both axes. The calibration note concludes "BBOX_ASSERTIONS_VIABLE =
False" partly based on this, but it was measured at only one point. We don't know whether
`k_x = 3.55` is consistent across all x positions, or whether it varies. We also don't
know whether there is a non-zero offset on either axis: a zero-offset model fits the Phase 0
data exactly (`20 × 3.55 = 71.0`), but a single point cannot distinguish zero-offset from
any other linear model.

**Problem B — Glyph-extent xmax**: `xmax = 312` is the right edge of the last glyph in
the text ("...lazy dog."), not the right edge of the declared 190 mm cell. This makes
`xmax` content-dependent and unpredictable from layout alone.

Problem A and Problem B need separate answers before any assertions can be enabled.

---

## Root-cause analysis

### Why k_x ≠ k_y?

Three hypotheses, in decreasing plausibility:

**H1 — Non-uniform rendering**: Claude renders the PDF page into a pixel buffer where
height and width are scaled by different DPI-equivalent factors. For A4:
- y: 297 mm × k_y/mm → k_y ≈ 2.14, so height ≈ 635 px
- x: 210 mm × k_x/mm → k_x ≈ 3.55, so width ≈ 746 px

This produces a non-square pixel-per-mm density, which is unusual but possible if the
viewer letterboxes or crops the page into a rectangular viewport.

**H2 — Tight glyph bounds on both axes**: `xmin=71` is not the cell left edge but the
glyph left edge of the letter 'T'. If Helvetica 12pt has a small left bearing, the first
pixel starts slightly to the right of the declared cell origin — but this would only
account for a 1–3 unit offset, not the ~28 unit discrepancy (71 vs expected 43 if using
k_y=2.14 for x as well).

**H3 — Coordinate origin offset**: Claude's coordinate origin is not the top-left corner
of the PDF page but some other reference point (e.g., the content area after applying the
page margins). Under this hypothesis, declared position x=20mm is already the offset from
page left, and Claude adds an additional margin offset. This would shift all x coordinates
by a fixed amount but doesn't explain why k_x ≠ k_y.

**Working assumption**: H1 is most plausible. Phase 1 treats k_x and k_y as potentially
independent constants, and separately checks for a non-zero intercept (constant offset)
using a linear regression over three distinct data points.

### Why is xmax glyph-bound?

Neither the prompt ("Coordinates must follow [ymin, xmin, ymax, xmax] order.") nor the
schema description ("Bounding box as [ymin, xmin, ymax, xmax] integers in page coordinate
space.") says anything about what the bounding box should represent — visual block
region, glyph extent, or cell boundary. In the absence of instruction, Claude defaults
to the visible extent of the text glyphs, which is the most visually obvious choice.

For elements with visible borders (tables, figure rects), the border IS the block
boundary, so the distinction doesn't arise. For unstyled text blocks (paragraphs,
headings), there is no visual cue for the intended cell width, so Claude estimates tight.

---

## What is NOT in scope

- Changing the architecture of coordinate storage (coordinates stay as 4 integers in
  `[ymin, xmin, ymax, xmax]` order)
- Fixing `is_continued` or any other unrelated schema field
- Changes to the hierarchy node or geometric pre-sorter (they work correctly with
  current coordinates)
- Cross-document-type calibration at this stage (invoice tables vs. paragraphs vs.
  figures) — that is a follow-up after single-type viability is confirmed

---

## Approach

Three sequential phases with a concrete go/no-go decision after each.

### Phase 1 — Multi-point x-axis calibration

**Goal**: Determine whether k_x is a consistent linear function of declared x position,
independent of text content, and whether there is a non-zero constant offset on either axis.

**Calibration PDF**: Create `tests/fixtures/pdfs/grp_calibration_multipoint.pdf` containing
three short text blocks on page 1:
- Block A: `x_mm=20, y_mm=50, w_mm=60` — text "Block A." in Helvetica 12pt
- Block B: `x_mm=60, y_mm=80, w_mm=60` — text "Block B." in Helvetica 12pt
- Block C: `x_mm=100, y_mm=110, w_mm=60` — text "Block C." in Helvetica 12pt

All three blocks must use Helvetica 12pt — the same font and size as the Phase 0
calibration block. Using a different font or size would change glyph metrics and make
the comparison invalid. Each block uses the same-length text string to minimise glyph
count variance between blocks.

Block A is placed at the same declared position as the Phase 0 block (x=20, y=50). Its
returned xmin can be compared to the Phase 0 result (xmin=71) as a session-to-session
stability check. If Phase 1 Block A xmin ≠ 71, use the Phase 1 data as the authoritative
source (all three blocks come from the same session, eliminating session-to-session variance
as a confound), and record the discrepancy in `calibration_notes.md`.

**Generator**: `tests/fixtures/generators/grp_calibration_multipoint.py` — a standalone
script that follows the same `generate(output_dir: Path) -> list[Path]` pattern as other
generator modules but is **not** registered in `generate_all.py`'s `_GENERATOR_MAP` and
is **not** tracked in `manifest.json`. It is a calibration artifact, not a test fixture.
Generate the PDF once with:
```
python -m tests.fixtures.generators.grp_calibration_multipoint
```
Commit the generated PDF to `tests/fixtures/pdfs/`.

**Running the calibration**: Run the fixture 3 times through the pioneer parser (same
mock setup as Phase 0). The following snippet is also added to `calibration_notes.md`:

```python
import asyncio
from unittest.mock import AsyncMock, patch
from src.graph import build_app
from tests.integration._compare import _make_relation_response

async def calibrate():
    app = build_app(checkpointer=None)
    for run in range(3):
        with (
            patch("src.nodes.classifier_node._classify",
                  new=AsyncMock(return_value="baseline_core")),
            patch("src.nodes.hierarchy_node._call_api",
                  new=AsyncMock(return_value=_make_relation_response([]))),
        ):
            result = await app.ainvoke({
                "file_path": "tests/fixtures/pdfs/grp_calibration_multipoint.pdf"
            })
        blocks = result["hierarchical_document_tree"]["structured_payload"]
        print(f"Run {run+1}:")
        for b in sorted(blocks, key=lambda b: b["bbox"]["coordinates"][0]):
            print(f"  '{b['text']}': {b['bbox']['coordinates']}")

asyncio.run(calibrate())
```

Record all 3 × 3 coordinate sets (3 runs × 3 blocks). If all 3 runs return identical
coordinates (consistent with Phase 0 determinism), one run is sufficient for analysis.

**Decision criteria — x-axis**:

Collect the three `(x_mm, xmin_returned)` pairs: `(20, xA), (60, xB), (100, xC)`. Fit a
linear model `xmin = a + b × x_mm` to the three points (by computing the least-squares
line or checking all pairwise slopes for consistency).

- **If all three residuals are within ±5 units** of the fitted line: k_x is linear.
  Record:
  - `COORD_SCALE_X = b` (fitted slope)
  - `COORD_OFFSET_X = a` (fitted intercept; if `|a| ≤ 5`, treat as zero and omit the
    constant from `_common.py`)
  → Proceed to Phase 2.
- **If any residual exceeds ±5 units**: k_x is not reliably linear → `BBOX_ASSERTIONS_VIABLE`
  stays False. Stop. Update `calibration_notes.md` with the findings.

> **Why ±5 units?** At k_x ≈ 3.55, five coordinate units correspond to ~1.4 mm. This is
> below the block height (8 mm) and represents a plausible noise floor for glyph-start
> detection. A larger deviation would indicate a genuinely non-linear mapping or a
> significant offset that a proportional model cannot explain.

**Decision criteria — y-axis (implicit check)**:

Phase 1 also yields three `(y_mm, ymin_returned)` pairs: `(50, yA), (80, yB), (110, yC)`.
Apply the same linear fit check. If any y residual exceeds ±5 units, the Phase 0
conclusion that k_y ≈ 2.14 is universal must be revised — record and stop before Phase 2,
since the y-axis anchor for all subsequent assertions would be unreliable.

> **Why a separate calibration fixture instead of re-using C1?** C1 only has one text
> block. A single point cannot distinguish slope from intercept in a linear model; fitting
> a line requires at least two independent measurements. Three points allow residual
> checking.

### Phase 2 — Prompt and schema description update

**Goal**: Reduce xmax ambiguity by giving Claude explicit instruction about what
bounding box coordinates represent.

**Changes**:

1. **`schemas/*.json` — `coordinates` field description**: Change from:
   ```
   "Bounding box as [ymin, xmin, ymax, xmax] integers in page coordinate space."
   ```
   to:
   ```
   "Bounding box as [ymin, xmin, ymax, xmax] integers. Report the full visual region
   of the block — not just text glyph extents. For text blocks, extend ymin/ymax to
   the line height and xmin/xmax to the containing text column's declared margins,
   not the glyph boundary."
   ```
   This change applies to all three schemas (baseline_core, invoice, scientific_paper).

2. **`worker_node.py` — extraction prompt**: After "Coordinates must follow
   [ymin, xmin, ymax, xmax] order.", add:
   ```
   "Report the full visual block extent, not text glyph bounds — for a paragraph
   reaching from the left margin to the right margin, xmax = right margin position."
   ```

**After the prompt change**:
- Run all 28 existing e2e tests. If any test regresses, **revert the prompt change
  and document why** — do not adapt tests to compensate.
- If tests pass, re-run the Phase 1 calibration fixture 3 times to measure whether
  xmax now reflects the declared cell right edge. The expected right edge for each block
  in Claude coordinates (using Phase 1's fitted constants):
  - Block A: `COORD_OFFSET_X + COORD_SCALE_X × (x_mm + w_mm)` = offset + scale × 80
  - Block B: `COORD_OFFSET_X + COORD_SCALE_X × 120`
  - Block C: `COORD_OFFSET_X + COORD_SCALE_X × 160`

**Decision criteria**:
- If returned xmax for each block is within 10% of its expected right edge: Problem B
  is resolved. Proceed to Phase 3 with full 4-coordinate assertions.
- If returned xmax < 70% of expected right edge for any block (still glyph-bound): the
  prompt change did not fix xmax for unstyled text. Document; `BBOX_ASSERTIONS_VIABLE`
  stays False for xmax. Proceed to Phase 3 with partial assertions (y-axis + xmin only).

### Phase 3 — Conditional test update

**Outcomes from Phases 1–2 and corresponding actions**:

| Phase 1 result | Phase 2 result | Action |
|---|---|---|
| k_x inconsistent | — | Stop. No code changes. Update `calibration_notes.md`. |
| k_x consistent | xmax fixed | Enable full 4-coordinate assertions. Set `COORD_SCALE_X`, `COORD_SCALE_Y` (and `COORD_OFFSET_X`, `COORD_OFFSET_Y` if non-zero) in `_common.py`; set `BBOX_ASSERTIONS_VIABLE = True`. |
| k_x consistent | xmax still glyph-bound | Enable 3-coordinate assertions (ymin, xmin, ymax). Add scale/offset constants to `_common.py`; set `BBOX_ASSERTIONS_VIABLE = True`. Use `check_xmax=False` in all enabled tests. |
| — | Prompt regresses tests | Revert prompt change. Enable y-axis-only assertions (ymin, ymax) if that adds regression value. |

**If assertions are enabled**, update `_compare.py:assert_blocks_match`:

Full updated signature:
```python
def assert_blocks_match(
    expected: list[dict],
    actual: list[dict],
    *,
    check_bbox: bool = False,
    check_xmax: bool = False,   # only meaningful when check_bbox=True
    bbox_tolerance_pct: float = 0.05,
    normalize_text: bool = True,
) -> None:
```

Behaviour:
- `check_bbox=False` → skip all bbox checks (existing behaviour, no change).
- `check_bbox=True, check_xmax=False` → assert `coordinates[0]`, `[1]`, `[2]`
  (ymin, xmin, ymax); skip `coordinates[3]` (xmax).
- `check_bbox=True, check_xmax=True` → assert all four coordinates.

The existing `_assert_bbox` helper receives the same `check_xmax` flag and skips the
fourth coordinate when it is False.

**Golden file updates**: Update actual measured coordinates (from Phase 1/2 calibration
runs, not computed from mm × scale, since we use empirical values) for C1, D1, and G1
only. Do not update all 28 test golden files blindly.

**Which tests benefit from bbox assertions**:
- **C1**: Paragraph at known position — ymin/xmin/ymax assertions verify the block is in
  the expected vertical band; xmax optional.
- **D1**: Table block — all four corners are visible (bordered cells), so full 4-coord
  assertion is the most reliable case after the prompt fix.
- **G1**: Two-column layout — xmin assertions on left and right column blocks verify
  Claude returns different x positions for the two columns. This **adds to** (does not
  replace) the existing dynamic-bucket heuristic; both checks remain active.

---

## Open questions / risks

1. **Prompt change regresses existing tests.** The extraction prompt wording affects
   all block types across all document types. A change that improves xmax for paragraphs
   may cause Claude to over-extend bboxes for other block types (e.g., a heading that
   spans only half the page width might get xmax extended to the full page right edge,
   breaking the column detection bucket logic).
   _Mitigation_: Run all 28 tests immediately after the prompt change. Revert on any
   regression.

2. **k_x and k_y vary by document, font size, or page zoom.** The calibration fixture
   uses Helvetica 12pt on A4, matching Phase 0 exactly. If Claude's rendering DPI changes
   with content complexity or page size, k_x and k_y are not universal constants.
   _Mitigation_: Phase 1 explicitly pins Helvetica 12pt for all three blocks, matching
   Phase 0. Add a note in `calibration_notes.md` that calibration must be re-verified on
   model upgrade.

3. **The "full visual block region" instruction is ambiguous for unstyled paragraphs.**
   A paragraph with no visible borders gives Claude no clear visual cue for the column
   boundary. The instruction may cause Claude to invent a "reasonable" column width
   that varies by run, making xmax LESS consistent, not more.
   _Mitigation_: Phase 2's 3-run re-calibration catches this — if xmax varies across
   runs for any block, the prompt change is reverted.

4. **Enabling bbox assertions adds fragility proportional to model non-determinism.**
   Even with a fixed prompt, Claude's bbox estimates may vary slightly run-to-run
   (unlike the 3/3 identical runs in Phase 0, which may reflect temperature=0 determinism
   on simple inputs). Any assertion enabled must tolerate ±5% of block dimension (already
   in `assert_blocks_match`).

5. **Separate COORD_SCALE_X, COORD_SCALE_Y (and potentially COORD_OFFSET_X, COORD_OFFSET_Y)
   in `_common.py` requires all golden file coordinate computations to use axis-specific
   scales and offsets.** The existing single-scale design must be updated. This is a
   mechanical change but touches every golden file that includes coordinates.

6. **Value of bbox assertions.** The 28 existing tests cover all pipeline concerns
   without bbox. Adding bbox assertions catches "wrong region of the page" regressions.
   **Stop criterion**: if, after Phase 1 and Phase 2 re-calibration, run-to-run xmax
   variance exceeds the ±5% tolerance for all 3 target blocks (indicating unstable
   estimates even after the prompt change), and the only viable assertions (y-axis + xmin)
   would duplicate what the existing text/type/ordering checks already catch for C1, D1,
   and G1, close the plan without enabling any bbox assertions.

7. **y-axis linearity assumed from two measurements in the same block.** Phase 0 measured
   ymin=107 and ymax=124 for a block spanning y=50–58 mm, giving k_y≈2.14 at both
   endpoints. These two measurements are only 8 mm apart and come from a single block, not
   independent data points for a linear fit. Phase 1 implicitly verifies y-axis linearity
   across three independent y positions (50, 80, 110 mm) as a byproduct of placing three
   blocks at different heights.
   _Mitigation_: If Phase 1's y-axis fit fails, revise the Phase 0 k_y conclusion and
   stop before Phase 2.

---

## Phased delivery

| Phase | Deliverable | Entry condition |
|---|---|---|
| 1 | Calibration PDF + generator script + measurements in `calibration_notes.md` | `ANTHROPIC_API_KEY` available |
| 2 | Prompt + schema description update | Phase 1 confirms k_x linear and y-axis fit holds |
| 3 | Updated `_common.py` constants + conditional assertion enablement | Phase 2 decision reached |

If Phase 1 fails (k_x non-linear or y-axis fit fails): close the plan. No code changes
beyond updating `calibration_notes.md` with the new findings.

If Phase 1 passes but Phase 2 fails (prompt regresses tests): revert prompt change,
enable y-axis-only assertions, close.

If all phases succeed: full 4-axis bbox assertions enabled for C1, D1, G1.

---

## Files that will change

| File | Change | Phase |
|---|---|---|
| `tests/fixtures/generators/calibration_notes.md` | Add Phase 1 calibration snippet + multi-point results | 1 |
| `tests/fixtures/generators/grp_calibration_multipoint.py` | New standalone calibration PDF generator (not in `_GENERATOR_MAP`) | 1 |
| `tests/fixtures/pdfs/grp_calibration_multipoint.pdf` | Generated by the generator script; not committed (`pdfs/` is gitignored) | 1 |
| `tests/fixtures/generators/_common.py` | Add `COORD_SCALE_X`, `COORD_SCALE_Y`; add `COORD_OFFSET_X`, `COORD_OFFSET_Y` if intercept > 5 units (values measured in Phase 1, written here in Phase 3) | 3 |
| `schemas/*.json` | Update `coordinates` description | 2 |
| `src/nodes/worker_node.py` | Add block-boundary instruction to prompt | 2 |
| `tests/integration/_compare.py` | Add `check_xmax` param; update `_assert_bbox` to honour it | 3 |
| `tests/fixtures/golden/grp_c_paragraph.json` et al. | Add coordinate entries | 3 |
| `tests/integration/test_synthetic_grp_c.py` | Enable `check_bbox=True` for C1 | 3 |
| `tests/integration/test_synthetic_grp_d.py` | Enable `check_bbox=True` for D1 | 3 |
| `tests/integration/test_synthetic_grp_g.py` | Add xmin coordinate assertions alongside existing bucket check | 3 |

---

## What this plan does NOT propose

- Changing `COLUMN_BUCKET_PX` or the `geometric_pre_sorter` logic (works correctly today)
- Normalizing coordinates in the pipeline output (would change the public API shape)
- Patching Claude's coordinate output in `window_parser_node` (would hide the raw data)
- Asserting bbox on all 28 tests (only where bbox adds diagnostic value)
- Adding `grp_calibration_multipoint` to `generate_all.py`'s `_GENERATOR_MAP` or `manifest.json`
