import asyncio
import base64
import hashlib


def hash_file(file_path: str) -> str:
    """Chunked SHA-256 — avoids loading the entire file into memory."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def encode_pdf_async(file_path: str) -> str:
    """Base64-encodes a PDF file without blocking the event loop."""

    def _read() -> str:
        with open(file_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    return await asyncio.to_thread(_read)
