from pypdf import PdfReader


def get_page_count(file_path: str) -> int:
    reader = PdfReader(file_path)
    if reader.is_encrypted:
        raise ValueError(
            f"PDF at '{file_path}' is encrypted. "
            "Claude PDF Chat does not support password-protected PDFs."
        )
    return len(reader.pages)
