"""Group H fixtures: graceful degradation.

H1 — 1 blank white page (no text, no objects)
H2 — 1 page with 4pt (sub-legibility) text only
"""

from pathlib import Path

from tests.fixtures.generators._common import draw_text, make_pdf, save_pdf


def _make_h1_blank():
    pdf = make_pdf()
    pdf.add_page()
    return pdf


def _make_h2_tiny_text():
    pdf = make_pdf()
    pdf.add_page()
    draw_text(pdf, "This text is printed at four points and may be unreadable.", 20, 50, size=4)
    return pdf


def generate(out_dir: Path) -> list[Path]:
    return [
        save_pdf(_make_h1_blank(), out_dir, "grp_h_blank.pdf"),
        save_pdf(_make_h2_tiny_text(), out_dir, "grp_h_tiny.pdf"),
    ]


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
