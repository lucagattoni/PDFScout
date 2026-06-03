# Phase 0 Calibration Notes

**Status: COMPLETE — BBOX_ASSERTIONS_VIABLE = False**

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
