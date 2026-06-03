"""Group H fixtures: graceful degradation.

H1 — 1 blank white page (no text, no objects)
"""

from pathlib import Path

from tests.fixtures.generators._common import make_pdf, save_pdf


def _make_h1_blank():
    pdf = make_pdf()
    pdf.add_page()
    return pdf


def generate(out_dir: Path) -> list[Path]:
    return [save_pdf(_make_h1_blank(), out_dir, "grp_h_blank.pdf")]


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
