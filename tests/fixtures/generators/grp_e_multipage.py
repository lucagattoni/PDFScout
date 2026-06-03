"""Group E fixtures: multi-page pipeline / burst + merge.

E1 — 2-page doc (1 paragraph per page, distinct text)
E2 — 5-page doc (1 paragraph per page)
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


def generate(out_dir: Path) -> list[Path]:
    return [
        save_pdf(_make_multipage(2), out_dir, "grp_e_2page.pdf"),
        save_pdf(_make_multipage(5), out_dir, "grp_e_5page.pdf"),
    ]


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
