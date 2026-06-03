"""Group G fixtures: layout / reading order.

G1 — 2-column A4 layout
     Left column at x ≈ 12.7 mm (→ Claude xmin ≈ 55, bucket 1 with COLUMN_BUCKET_PX=50)
     Right column at x ≈ 111 mm (→ Claude xmin ≈ 310, bucket 6 with COLUMN_BUCKET_PX=50)

G2 — 3-column A4 layout
     Col-1 at x = 20 mm (→ Claude xmin ≈ 74, bucket 1 with COLUMN_BUCKET_PX=50)
     Col-2 at x = 78 mm (→ Claude xmin ≈ 225, bucket 4 with COLUMN_BUCKET_PX=50)
     Col-3 at x = 136 mm (→ Claude xmin ≈ 376, bucket 7 with COLUMN_BUCKET_PX=50)
     Positions chosen so each column sits near its bucket centre (≥24 units from boundaries).
"""

import json
from pathlib import Path

from tests.fixtures.generators._common import draw_text, golden_meta, make_pdf, save_pdf

_GOLDEN_DIR = Path(__file__).parent.parent / "golden"

# G1 column x positions in mm
_LEFT_X = 12.7
_RIGHT_X = 111.0
_COL_W = 85.0

# G2 column x positions in mm — chosen to target bucket centres at ~74, ~225, ~376 Claude units
_COL1_X = 20.0
_COL2_X = 78.0
_COL3_X = 136.0
_COL_W_3 = 50.0


def _make_g1_two_column():
    pdf = make_pdf()
    pdf.add_page()

    y_positions = [40, 70, 100]
    labels_left = ["L1", "L2", "L3"]
    labels_right = ["R1", "R2", "R3"]

    for label, y in zip(labels_left, y_positions):
        draw_text(
            pdf, f"{label}: Left column content for item {label}.", _LEFT_X, y, size=11, w=_COL_W
        )

    for label, y in zip(labels_right, y_positions):
        draw_text(
            pdf, f"{label}: Right column content for item {label}.", _RIGHT_X, y, size=11, w=_COL_W
        )

    return pdf


def _make_g2_three_column():
    pdf = make_pdf()
    pdf.add_page()

    y_positions = [40, 70, 100]
    row_labels = ["A", "B", "C"]
    columns = [("C1", _COL1_X), ("C2", _COL2_X), ("C3", _COL3_X)]

    for col_label, x in columns:
        for row_label, y in zip(row_labels, y_positions):
            label = f"{col_label}{row_label}"
            draw_text(
                pdf,
                f"{label}: Column {col_label} row {row_label}.",
                x,
                y,
                size=11,
                w=_COL_W_3,
            )

    return pdf


def generate(out_dir: Path) -> list[Path]:
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    g1_golden = {
        "meta": golden_meta("grp_g_two_column"),
        "expected": {
            "document_type": "baseline_core",
            "texts": ["L1:", "L2:", "L3:", "R1:", "R2:", "R3:"],
        },
    }
    (_GOLDEN_DIR / "grp_g_two_column.json").write_text(json.dumps(g1_golden, indent=2))

    g2_golden = {
        "meta": golden_meta("grp_g_three_column"),
        "expected": {
            "document_type": "baseline_core",
            "texts": ["C1A:", "C1B:", "C1C:", "C2A:", "C2B:", "C2C:", "C3A:", "C3B:", "C3C:"],
        },
    }
    (_GOLDEN_DIR / "grp_g_three_column.json").write_text(json.dumps(g2_golden, indent=2))

    return [
        save_pdf(_make_g1_two_column(), out_dir, "grp_g_two_column.pdf"),
        save_pdf(_make_g2_three_column(), out_dir, "grp_g_three_column.pdf"),
    ]


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
