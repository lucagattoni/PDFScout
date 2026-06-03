"""Group D fixtures: schema-specific metadata.

D1 — invoice  — 4-col line-items table → table_data
D2 — sci paper — title + 3 authors + Abstract → bibliographic
D3 — sci paper — "2. Methodology" heading + 2 paragraphs → section
D4 — sci paper — 3 numbered references → reference
D5 — sci paper — grey rect + "Figure 1: Caption text" caption → figure_table
"""

import json
from pathlib import Path

from tests.fixtures.generators._common import (
    draw_filled_rect,
    draw_multiline,
    draw_table,
    draw_text,
    golden_meta,
    make_pdf,
    save_pdf,
)

_GOLDEN_DIR = Path(__file__).parent.parent / "golden"


def _make_d1_invoice_table():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "INVOICE #002 - Line Items", 20, 25, size=14, style="B")
    draw_table(
        pdf,
        x_mm=20,
        y_mm=40,
        headers=["Description", "Qty", "Unit Price", "Total"],
        rows=[
            ["Premium Widget", "3", "$100.00", "$300.00"],
            ["Standard Widget", "7", "$50.00", "$350.00"],
            ["Installation", "1", "$200.00", "$200.00"],
        ],
        col_width=42.5,
        row_height=9,
    )
    draw_text(pdf, "Grand Total: $850.00", 120, 90, size=12, style="B")
    return pdf


def _make_d2_bibliographic():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "Advances in Neural Document Parsing", 20, 25, size=16, style="B", align="C", w=170)
    draw_text(pdf, "Dr. Alice Johnson, Prof. Bob Martinez, Carol Chen", 20, 40, size=11, align="C", w=170)
    draw_text(pdf, "Abstract", 20, 58, size=13, style="B")
    draw_multiline(
        pdf,
        "We introduce a framework for evaluating document extraction models on controlled "
        "synthetic inputs. The framework measures precision and recall across block types "
        "without requiring access to proprietary document collections.",
        20, 68, size=11, w=170,
    )
    draw_text(pdf, "DOI: 10.9876/ndp.2026.042", 20, 130, size=10)
    return pdf


def _make_d3_section():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "2. Methodology", 20, 40, size=13, style="B")
    draw_multiline(
        pdf,
        "Our methodology combines synthetic PDF generation with automated assertion "
        "checking. We generate documents with known structure and compare the model "
        "output against the design intent.",
        20, 55, size=11, w=170,
    )
    draw_multiline(
        pdf,
        "The evaluation proceeds in four phases: calibration, block-type detection, "
        "metadata quality assessment, and hierarchy verification.",
        20, 90, size=11, w=170,
    )
    return pdf


def _make_d4_references():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "References", 20, 30, size=13, style="B")
    refs = [
        "[1] Smith, A., Jones, B. (2024). Document Layout Analysis Survey. CVPR 2024.",
        "[2] Lee, C., Wang, D. (2025). Transformer Models for PDF Parsing. ICCV 2025.",
        "[3] Brown, E., Taylor, F. (2026). Synthetic Benchmarks for NLP. ACL 2026.",
    ]
    y = 45
    for ref in refs:
        draw_text(pdf, ref, 20, y, size=10)
        y += 14
    return pdf


def _make_d5_figure():
    pdf = make_pdf()
    pdf.add_page()
    draw_filled_rect(pdf, 20, 35, 120, 70, fill_color=(210, 210, 210))
    draw_text(pdf, "[Figure Area]", 68, 68, size=10, style="I", w=30, align="C")
    draw_text(pdf, "Figure 1: Distribution of block types across document corpus.", 20, 113, size=10)
    return pdf


def _write_golden_d(name: str, doc_type: str, blocks: list) -> None:
    golden = {
        "meta": golden_meta(name),
        "expected": {"document_type": doc_type, "blocks": blocks},
    }
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (_GOLDEN_DIR / f"{name}.json").write_text(json.dumps(golden, indent=2))


def generate(out_dir: Path) -> list[Path]:
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    paths = []

    # D1: invoice table — expected table block; metadata assertions done inline in test
    _write_golden_d("grp_d_table_data", "invoice", [
        {"type": "table", "text": "Description", "metadata": {}},
    ])
    paths.append(save_pdf(_make_d1_invoice_table(), out_dir, "grp_d_table_data.pdf"))

    # D2: bibliographic — 3 author names in text; metadata is optional
    _write_golden_d("grp_d_bibliographic", "scientific_paper", [
        {
            "type": "title",
            "text": "Advances in Neural Document Parsing",
            "metadata": {},
            "_authors": ["Dr. Alice Johnson", "Prof. Bob Martinez", "Carol Chen"],
        },
    ])
    paths.append(save_pdf(_make_d2_bibliographic(), out_dir, "grp_d_bibliographic.pdf"))

    # D3: section — expected heading with section metadata
    _write_golden_d("grp_d_section", "scientific_paper", [
        {
            "type": "heading",
            "text": "2. Methodology",
            "metadata": {},
            "_section_number": "2",
            "_section_title": "Methodology",
        },
    ])
    paths.append(save_pdf(_make_d3_section(), out_dir, "grp_d_section.pdf"))

    # D4: references — 3 reference entries with years
    _write_golden_d("grp_d_reference", "scientific_paper", [
        {"type": "paragraph", "text": "[1]", "metadata": {}, "_year_present": True},
        {"type": "paragraph", "text": "[2]", "metadata": {}, "_year_present": True},
        {"type": "paragraph", "text": "[3]", "metadata": {}, "_year_present": True},
    ])
    paths.append(save_pdf(_make_d4_references(), out_dir, "grp_d_reference.pdf"))

    # D5: figure_table — figure with label and caption
    _write_golden_d("grp_d_figure_table", "scientific_paper", [
        {
            "type": "figure",
            "text": "Figure 1",
            "metadata": {},
            "_label": "Figure 1",
            "_caption": "Distribution of block types across document corpus.",
        },
    ])
    paths.append(save_pdf(_make_d5_figure(), out_dir, "grp_d_figure_table.pdf"))

    return paths


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
