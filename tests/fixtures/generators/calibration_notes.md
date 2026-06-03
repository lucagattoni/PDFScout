# Phase 0 Calibration Notes

**Status: NOT YET RUN**

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

_Update this section after running calibration._

- `COORD_SCALE =` _(not set)_
- `BBOX_ASSERTIONS_VIABLE =` `False` _(current setting in `_common.py`)_

## Raw results

_Paste output of the 3 calibration runs here._
