# Calibration Notes

**Status: COMPLETE — BBOX_ASSERTIONS_VIABLE = False (confirmed by Phase 1)**

Calibration must be performed before enabling bbox assertions.

## How to calibrate

1. Ensure a real `ANTHROPIC_API_KEY` is set.
2. Run the C1 fixture through the pioneer parser 3 times:

```python
import asyncio
from unittest.mock import AsyncMock, patch
from src.graph import build_app
from tests.integration._compare import _make_relation_response

async def calibrate():
    app = build_app(checkpointer=None)
    for run in range(3):
        with (
            patch("src.nodes.classifier_node._classify", new=AsyncMock(return_value="baseline_core")),
            patch("src.nodes.hierarchy_node._call_api",
                  new=AsyncMock(return_value=_make_relation_response([]))),
        ):
            result = await app.ainvoke({"file_path": "tests/fixtures/pdfs/grp_c_paragraph.pdf"})
        blocks = result["hierarchical_document_tree"]["structured_payload"]
        print(f"Run {run+1}: {blocks[0]['bbox']['coordinates']}")

asyncio.run(calibrate())
```

3. The generator places "The quick brown fox..." paragraph at fpdf2 position:
   - `x_mm = 20 mm`, `y_mm = 50 mm`, `w_mm = 170 mm`, `h_mm = 8 mm`
   - So expected bounding box in mm: `[ymin=50, xmin=20, ymax=58, xmax=190]`

4. Compare returned `coordinates` to mm values:
   - If `coordinates ≈ mm_values × k` consistently → set `COORD_SCALE = k`
   - If values vary widely across 3 runs → keep `BBOX_ASSERTIONS_VIABLE = False`

## Decision

- `COORD_SCALE =` _(not set — x-direction scale is not consistent, see analysis below)_
- `BBOX_ASSERTIONS_VIABLE =` `False` _(confirmed; setting unchanged in `_common.py`)_

## Raw results

All 3 runs returned identical coordinates — the model is deterministic:

```
Run 1: [107, 71, 124, 312]
Run 2: [107, 71, 124, 312]
Run 3: [107, 71, 124, 312]
```

## Analysis

Known placement (mm): `[ymin=50, xmin=20, ymax=58, xmax=190]`  
Returned coordinates: `[107, 71, 124, 312]`

Scale ratios:
- ymin: 107 / 50 = **2.14**
- ymax: 124 / 58 = **2.138** ← consistent with ymin ✓
- xmin: 71 / 20 = **3.55**
- xmax: 312 / 190 = **1.642** ← inconsistent with xmin ✗

The y-direction is stable and maps to a consistent scale (k ≈ 2.14). The x-direction does
not — because Claude returns **tight text bounding boxes** (actual glyph extent) rather than
the declared cell width. The text "The quick brown fox..." is ~241 units wide regardless of
the 170mm (481.9pt) cell that contains it, making xmax content-dependent and not a function
of the declared cell geometry.

Consequence: no single `COORD_SCALE` can convert mm positions to Claude coordinates for
xmax (and by extension, any right-edge or width assertion). Relative ordering assertions
(left column before right column, upper block before lower block) remain reliable and are
used in the grp_g test.

---

## Phase 1 — Multi-point x-axis calibration

**Status: COMPLETE — Phase 1 FAILED; plan closed**

Phase 1 goal: verify k_x is linear by running three text blocks at distinct x positions
(x_mm = 20, 60, 100) through the pioneer parser and fitting a linear model to the
returned xmin values. The plan required all residuals ≤ ±5 units to proceed to Phase 2.

### How to re-run

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

Fixture blocks (all Helvetica 12pt, w_mm=60):
- Block A: x_mm=20, y_mm=50  → declared right edge 80 mm
- Block B: x_mm=60, y_mm=80  → declared right edge 120 mm
- Block C: x_mm=100, y_mm=110 → declared right edge 160 mm

### Raw results

```
Run 1:
  'Block A.': [183, 97, 201, 152]
  'Block B.': [311, 222, 329, 288]
  'Block C.': [421, 320, 439, 392]
Run 2:
  'Block A.': [183, 97, 200, 152]
  'Block B.': [296, 189, 313, 252]
  'Block C.': [399, 224, 416, 291]
Run 3:
  'Block A.': [185, 97, 205, 157]
  'Block B.': [310, 185, 330, 265]
  'Block C.': [420, 220, 440, 310]
```

### Analysis

**Finding 1 — k_x is not linear.** Linear regression on the three (x_mm, xmin) pairs
within each run gives residuals well outside ±5 for every run:

| Run | fit | Block A residual | Block B residual | Block C residual | Pass? |
|-----|-----|-----------------|-----------------|-----------------|-------|
| 1 | xmin = 45.8 + 2.788·x | −4.5 | **+9.0** | −4.5 | **No** |
| 2 | xmin = 74.8 + 1.587·x | **−9.5** | **+19.0** | **−9.5** | **No** |
| 3 | xmin = 75.1 + 1.538·x | **−8.8** | **+17.7** | **−8.8** | **No** |

The fitted slope is not stable across runs (2.79 vs 1.59 vs 1.54), and the middle block
always carries a large positive residual — indicating the x-to-coordinate mapping is
non-linear (or the coordinate system changes between blocks in the same scene).

**Finding 2 — Coordinates are non-deterministic for multi-block pages.** Phase 0 was
fully deterministic (3/3 identical runs). Phase 1 with three blocks shows large
run-to-run variance:

| Block | xmin values | span | ymin values | span |
|-------|-------------|------|-------------|------|
| A | 97, 97, 97 | 0 | 183, 183, 185 | 2 |
| B | 222, 189, 185 | **37** | 311, 296, 310 | 15 |
| C | 320, 224, 220 | **100** | 421, 399, 420 | 22 |

Block A (at lower-left, same as Phase 0's single block) remains deterministic. Blocks B
and C — further right and lower on the page — vary widely. This suggests Claude's
coordinate estimation degrades as blocks are further from the top-left corner on
multi-block pages.

**Finding 3 — Scale factors are PDF-dependent.** Block A is at the same declared
position as Phase 0 (x=20, y=50), but gives different coordinates:

| | ymin | xmin | k_y | k_x |
|--|------|------|-----|-----|
| Phase 0 (C1 PDF, 1 block) | 107 | 71 | 2.14 | 3.55 |
| Phase 1 (3-block PDF) | 183–185 | 97 | 3.66–3.70 | 4.85 |

The same mm position maps to different Claude coordinates in different PDFs. Scale
factors are not universal constants — they vary with page content density.

### Decision

**Phase 1 FAILED** — k_x is non-linear in all 3 runs, and coordinates are
non-deterministic for blocks beyond the leftmost position. Per the plan:

> If Phase 1 fails: close the plan. No code changes beyond updating calibration_notes.md.

`BBOX_ASSERTIONS_VIABLE = False` remains unchanged in `_common.py`.

Phase 2 (prompt change) and Phase 3 (assertion enablement) are not executed.

**Note for future re-investigation**: The Phase 0 single-block determinism may reflect
a simpler rendering path for pages with minimal content. Any future calibration attempt
should verify both determinism AND linearity before enabling assertions, and should use
a multi-block fixture (not a single block) as the canonical calibration signal.
