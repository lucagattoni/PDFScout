import base64

from src.utils.pdf_utils import hash_file, encode_pdf_async


class TestHashFile:
    def test_returns_64_char_hex(self, minimal_pdf_path):
        digest = hash_file(minimal_pdf_path)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_deterministic(self, minimal_pdf_path):
        assert hash_file(minimal_pdf_path) == hash_file(minimal_pdf_path)

    def test_different_content_different_hash(self, tmp_path, minimal_pdf_bytes):
        path_a = tmp_path / "a.pdf"
        path_b = tmp_path / "b.pdf"
        path_a.write_bytes(minimal_pdf_bytes)
        path_b.write_bytes(minimal_pdf_bytes + b"\x00extra")
        assert hash_file(str(path_a)) != hash_file(str(path_b))


class TestEncodePdfAsync:
    async def test_returns_non_empty_string(self, minimal_pdf_path):
        result = await encode_pdf_async(minimal_pdf_path)
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_decoded_matches_original(self, minimal_pdf_path, minimal_pdf_bytes):
        result = await encode_pdf_async(minimal_pdf_path)
        assert base64.standard_b64decode(result) == minimal_pdf_bytes
