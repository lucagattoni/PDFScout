"""Group E fixtures: multi-page pipeline / burst + merge.

E1 — 2-page doc (1 paragraph per page, distinct text)
E2 — 5-page doc (1 paragraph per page)
E3 — 2-page doc with one cross-page paragraph split (is_continued fixture)
"""

from pathlib import Path

from tests.fixtures.generators._common import draw_text, make_pdf, save_pdf


def _make_multipage(n_pages: int) -> object:
    pdf = make_pdf()
    for page in range(1, n_pages + 1):
        pdf.add_page()
        draw_text(
            pdf,
            f"Page {page} content: This paragraph is exclusively on page {page}.",
            20, 50, size=12,
        )
    return pdf


def _make_continuation() -> object:
    """2-page PDF with one paragraph split across the page break.

    Page 1: fragment placed near the bottom (y=230mm on A4=297mm) — ends with
    "and" (no period) to signal the sentence is incomplete.
    Page 2: continuation placed at the top (y=20mm) — begins with lowercase
    "hierarchical" to make the split unambiguous to the extractor.
    """
    pdf = make_pdf()
    pdf.add_page()
    draw_text(
        pdf,
        "The pipeline handles documents through extraction, classification, parsing, and",
        20, 230, size=12,
    )
    pdf.add_page()
    draw_text(
        pdf,
        "hierarchical assembly, making it suitable for production workloads.",
        20, 20, size=12,
    )
    return pdf


def generate(out_dir: Path) -> list[Path]:
    return [
        save_pdf(_make_multipage(2), out_dir, "grp_e_2page.pdf"),
        save_pdf(_make_multipage(5), out_dir, "grp_e_5page.pdf"),
        save_pdf(_make_continuation(), out_dir, "grp_e_continuation.pdf"),
    ]


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
