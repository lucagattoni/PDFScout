"""Group G fixtures: layout / reading order.

G1 — 2-column A4 layout: columns at x ≈ 12.7 mm and ≈ 111 mm — the gutter far
     exceeds COLUMN_BUCKET_FRAC x span, so each column gets its own bucket.

G2 — 3-column A4 layout: columns at x = 20 / 78 / 136 mm, likewise separated
     by more than one span-relative bucket width each.

G3 — label-sidebar layout (distilled from a real Italian utility invoice p3):
     narrow bold label column left (x = 12.7 mm), full-width text blocks right
     (x = 45 mm, w = 150 mm → width ≥ BAND_FULL_WIDTH_FRAC of the x-span, so
     each row starts a band). Human order: label before its own text, row by row.
     Regression for the "every label sorted after its text" inversion.

G4 — heading directly above a full-width table, with a right sidebar
     (distilled from real utility bills p1/p2): the heading must stay adjacent
     to its table (pull-down into the table's band), not stranded before the
     sidebar content. Regression for the heading↔table band split.
"""

import json
from pathlib import Path

from tests.fixtures.generators._common import (
    draw_multiline,
    draw_table,
    draw_text,
    golden_meta,
    make_pdf,
    save_pdf,
)

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


def _make_g3_label_sidebar():
    pdf = make_pdf()
    pdf.add_page()

    rows = [
        ("LBL1", "Online Discount", "TXT1: This invoice includes a discount of one euro for the "
                                    "online billing service you activated last year."),
        ("LBL2", "Energy Cost", "TXT2: The average unit cost in this invoice is calculated as "
                                "the ratio of the amount due to the kilowatt hours billed."),
        ("LBL3", "Contact Us", "TXT3: You can amend or cancel your contract through the toll "
                               "free number available every day of the week."),
    ]
    y = 40
    for _, label, text in rows:
        draw_text(pdf, label, 12.7, y, size=11, style="B", w=28)
        draw_multiline(pdf, text, 45.0, y, w=150.0, size=10)
        y += 45

    return pdf


def _make_g4_heading_table_sidebar():
    pdf = make_pdf()
    pdf.add_page()

    draw_text(pdf, "INTRO: Summary of your account for the current period.", 12.7, 40, size=11, w=90)
    draw_multiline(
        pdf,
        "SIDEBAR: Questions about this document? Visit our help centre or call "
        "the freephone support number weekdays.",
        130.0,
        40,
        w=65.0,
        size=10,
    )
    draw_text(pdf, "CHARGE DETAILS", 12.7, 94, size=13, style="B", w=80)
    draw_table(
        pdf,
        12.7,
        102,
        headers=["Item", "Quantity", "Amount"],
        rows=[
            ["Standing charge", "62 days", "39.08"],
            ["Consumption", "208 kWh", "64.23"],
            ["Levy", "1", "2.92"],
        ],
        col_width=58.0,
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

    g3_golden = {
        "meta": golden_meta("grp_g_label_sidebar"),
        "expected": {
            "document_type": "baseline_core",
            # Interleaved by row, label before its own text
            "order": ["Online Discount", "TXT1", "Energy Cost", "TXT2", "Contact Us", "TXT3"],
        },
    }
    (_GOLDEN_DIR / "grp_g_label_sidebar.json").write_text(json.dumps(g3_golden, indent=2))

    g4_golden = {
        "meta": golden_meta("grp_g_heading_table_sidebar"),
        "expected": {
            "document_type": "baseline_core",
            # Heading adjacent to (immediately before) its table; sidebar earlier
            "order": ["INTRO", "SIDEBAR", "CHARGE DETAILS", "Standing charge"],
            "adjacent": ["CHARGE DETAILS", "Standing charge"],
        },
    }
    (_GOLDEN_DIR / "grp_g_heading_table_sidebar.json").write_text(json.dumps(g4_golden, indent=2))

    return [
        save_pdf(_make_g1_two_column(), out_dir, "grp_g_two_column.pdf"),
        save_pdf(_make_g2_three_column(), out_dir, "grp_g_three_column.pdf"),
        save_pdf(_make_g3_label_sidebar(), out_dir, "grp_g_label_sidebar.pdf"),
        save_pdf(_make_g4_heading_table_sidebar(), out_dir, "grp_g_heading_table_sidebar.pdf"),
    ]


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
