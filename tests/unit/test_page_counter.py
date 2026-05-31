import pytest
from io import BytesIO
from pypdf import PdfWriter

from src.extractors.page_counter import get_page_count


def _make_pdf(tmp_path, n_pages: int) -> str:
    writer = PdfWriter()
    for _ in range(n_pages):
        writer.add_blank_page(width=612, height=792)
    buf = BytesIO()
    writer.write(buf)
    path = tmp_path / f"{n_pages}page.pdf"
    path.write_bytes(buf.getvalue())
    return str(path)


def _make_encrypted_pdf(tmp_path) -> str:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    buf = BytesIO()
    writer.write(buf)
    path = tmp_path / "encrypted.pdf"
    path.write_bytes(buf.getvalue())
    return str(path)


class TestGetPageCount:
    def test_one_page(self, tmp_path):
        assert get_page_count(_make_pdf(tmp_path, 1)) == 1

    def test_three_pages(self, tmp_path):
        assert get_page_count(_make_pdf(tmp_path, 3)) == 3

    def test_encrypted_raises(self, tmp_path):
        path = _make_encrypted_pdf(tmp_path)
        with pytest.raises(ValueError, match="encrypted"):
            get_page_count(path)
