"""Group A fixtures: native extraction (no LLM).

A1 — valid 1-page PDF
A2 — valid 10-page PDF
A3 — encrypted PDF (pypdf-generated)
"""

from pathlib import Path

from pypdf import PdfWriter

from tests.fixtures.generators._common import make_pdf


def _make_blank_pdf(n_pages: int) -> bytes:
    """Return bytes of an n-page blank fpdf2 PDF."""
    pdf = make_pdf()
    for _ in range(n_pages):
        pdf.add_page()
    from io import BytesIO
    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def _make_encrypted_pdf() -> bytes:
    """Return bytes of a 1-page pypdf-encrypted PDF."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("password123")
    from io import BytesIO
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def generate(out_dir: Path) -> list[Path]:
    paths = []
    paths.append(save_pdf_bytes(_make_blank_pdf(1), out_dir, "grp_a_valid_1page.pdf"))
    paths.append(save_pdf_bytes(_make_blank_pdf(10), out_dir, "grp_a_valid_10page.pdf"))
    paths.append(save_pdf_bytes(_make_encrypted_pdf(), out_dir, "grp_a_encrypted.pdf"))
    return paths


def save_pdf_bytes(data: bytes, out_dir: Path, filename: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(data)
    return path


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
