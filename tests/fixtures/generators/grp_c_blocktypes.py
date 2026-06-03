"""Group C fixtures: block-type extraction.

C1 — paragraph
C2 — title
C3 — heading
C4 — list_items (3 bullet points)
C5 — footnote (7pt font + horizontal rule + superscript marker)
C6 — margin_element (grey background rect, narrow column)
C7 — table (3×4)
C8 — figure (grey rect + caption)
C9 — long paragraph (500 words)
"""

import json
from pathlib import Path

from tests.fixtures.generators._common import (
    draw_filled_rect,
    draw_hline,
    draw_multiline,
    draw_table,
    draw_text,
    golden_meta,
    make_pdf,
    save_pdf,
)

_GOLDEN_DIR = Path(__file__).parent.parent / "golden"

_LONG_PARA = (
    "The study of synthetic document generation has gained considerable attention in recent "
    "years as researchers seek to build evaluation benchmarks that are both controllable and "
    "freely distributable. Unlike real-world document collections, which often contain "
    "sensitive personal information or proprietary business content, synthetic fixtures allow "
    "precise control over every structural element while maintaining the visual appearance of "
    "genuine documents. This makes them particularly valuable for training and evaluating "
    "document understanding systems that must generalize across diverse layouts and content "
    "types. The approach presented here leverages the fpdf2 library to programmatically "
    "construct PDFs with known ground-truth annotations, enabling repeatable comparison of "
    "extraction model outputs against design intent. Each fixture is parameterized by its "
    "structural features: font size and style encode semantic role, position encodes reading "
    "order, and visual elements such as borders and background fills encode special regions "
    "like tables and figures. By fixing the creation date and all rendering parameters, the "
    "generator produces byte-for-byte identical PDFs on every invocation, ensuring that "
    "manifest-based hash checks reliably detect when content has changed. The evaluation "
    "framework built on top of these fixtures adopts a tiered approach: simple block-type "
    "presence tests run first, followed by metadata quality checks, multi-page pipeline "
    "tests, and finally hierarchy assignment verification. This layered structure means that "
    "when a higher-level test fails, the lower-level tests that passed already constrain the "
    "root cause to the specific pipeline stage under scrutiny, dramatically reducing the "
    "diagnostic burden on the developer. The long paragraph fixture specifically tests "
    "whether the extraction model correctly identifies extended prose as a single semantic "
    "unit rather than splitting it at arbitrary boundaries."
)


def _make_c1_paragraph():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "The quick brown fox jumps over the lazy dog.", 20, 50, size=12)
    return pdf


def _make_c2_title():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "Synthetic Document Analysis", 20, 50, size=24, style="B", align="C", w=170)
    return pdf


def _make_c3_heading():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "1. Introduction", 20, 50, size=14, style="B")
    return pdf


def _make_c4_list_items():
    pdf = make_pdf()
    pdf.add_page()
    items = ["First list item content", "Second list item content", "Third list item content"]
    y = 50
    for item in items:
        draw_text(pdf, f"-  {item}", 20, y, size=12)
        y += 12
    return pdf


def _make_c5_footnote():
    pdf = make_pdf()
    pdf.add_page()
    # Body text with superscript marker (rendered as plain text indicator)
    draw_text(pdf, "This claim requires a citation.[1]", 20, 50, size=12)
    draw_text(pdf, "Further analysis supports the main hypothesis presented above.[2]", 20, 62, size=12)
    # Horizontal rule separator
    draw_hline(pdf, 20, 200, 60)
    # Footnote text: 7pt font
    draw_text(pdf, "[1] Smith et al., Proceedings of the Annual Conference, 2025.", 20, 204, size=7)
    draw_text(pdf, "[2] Jones and Lee, Journal of Synthetic Documents, 2026.", 20, 211, size=7)
    return pdf


def _make_c6_margin_element():
    pdf = make_pdf()
    pdf.add_page()
    # Main body text
    draw_multiline(pdf, "This is the main body text of the document. It contains the primary "
                   "narrative content that spans the full readable width of the page and "
                   "continues for several lines to establish a clear visual distinction "
                   "from the sidebar element on the right.", 20, 50, size=12, w=110)
    # Margin sidebar: grey background + narrow column (< 25% page width = < 52mm; use 45mm)
    draw_filled_rect(pdf, 160, 45, 30, 55, fill_color=(220, 220, 220))
    draw_text(pdf, "Key Point", 162, 48, size=8, style="B", w=26)
    draw_text(pdf, "Sidebar note with additional context for readers.", 162, 57, size=7, w=26)
    return pdf


def _make_c7_table():
    pdf = make_pdf()
    pdf.add_page()
    draw_table(
        pdf,
        x_mm=20,
        y_mm=50,
        headers=["Column A", "Column B", "Column C"],
        rows=[
            ["Alpha", "Beta", "Gamma"],
            ["Delta", "Epsilon", "Zeta"],
            ["Eta", "Theta", "Iota"],
            ["Kappa", "Lambda", "Mu"],
        ],
        col_width=45,
        row_height=9,
    )
    return pdf


def _make_c8_figure():
    pdf = make_pdf()
    pdf.add_page()
    # Grey rectangle representing a chart/figure
    draw_filled_rect(pdf, 20, 40, 120, 80, fill_color=(210, 210, 210))
    draw_text(pdf, "[Synthetic Chart Area]", 55, 78, size=10, style="I", w=50, align="C")
    # Caption below the figure
    draw_text(pdf, "Figure 1: Synthetic chart showing example data distribution.", 20, 128, size=10)
    return pdf


def _make_c9_long_paragraph():
    pdf = make_pdf()
    pdf.add_page()
    draw_multiline(pdf, _LONG_PARA, 20, 25, size=11, w=170, h=6)
    return pdf


def _write_golden_c(name: str, doc_type: str, blocks: list) -> None:
    golden = {
        "meta": golden_meta(name),
        "expected": {"document_type": doc_type, "blocks": blocks},
    }
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (_GOLDEN_DIR / f"{name}.json").write_text(json.dumps(golden, indent=2))


def generate(out_dir: Path) -> list[Path]:
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    paths = []

    fixtures = [
        ("grp_c_paragraph", _make_c1_paragraph, "baseline_core",
         [{"type": "paragraph", "text": "The quick brown fox jumps over the lazy dog.", "metadata": {}}]),
        ("grp_c_title", _make_c2_title, "baseline_core",
         [{"type": "title", "text": "Synthetic Document Analysis", "metadata": {}}]),
        ("grp_c_heading", _make_c3_heading, "baseline_core",
         [{"type": "heading", "text": "1. Introduction", "metadata": {}}]),
        ("grp_c_list_items", _make_c4_list_items, "baseline_core",
         [
             {"type": "list_item", "text": "First list item content", "metadata": {}},
             {"type": "list_item", "text": "Second list item content", "metadata": {}},
             {"type": "list_item", "text": "Third list item content", "metadata": {}},
         ]),
        ("grp_c_footnote", _make_c5_footnote, "baseline_core",
         [{"type": "footnote", "text": "[1]", "metadata": {}}]),
        ("grp_c_margin_element", _make_c6_margin_element, "baseline_core",
         [{"type": "margin_element", "text": "Key Point", "metadata": {}}]),
        ("grp_c_table", _make_c7_table, "baseline_core",
         [{"type": "table", "text": "Column A", "metadata": {}}]),
        ("grp_c_figure", _make_c8_figure, "baseline_core",
         [{"type": "paragraph", "text": "Figure 1:", "metadata": {}}]),
        ("grp_c_long_paragraph", _make_c9_long_paragraph, "baseline_core",
         [{"type": "paragraph", "text": "The study of synthetic document generation", "metadata": {}}]),
    ]

    pdf_names = [
        "grp_c_paragraph.pdf", "grp_c_title.pdf", "grp_c_heading.pdf",
        "grp_c_list_items.pdf", "grp_c_footnote.pdf", "grp_c_margin_element.pdf",
        "grp_c_table.pdf", "grp_c_figure.pdf", "grp_c_long_paragraph.pdf",
    ]

    for (name, make_fn, doc_type, blocks), pdf_name in zip(fixtures, pdf_names):
        paths.append(save_pdf(make_fn(), out_dir, pdf_name))
        _write_golden_c(name, doc_type, blocks)

    return paths


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
