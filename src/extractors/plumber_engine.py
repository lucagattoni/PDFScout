import pdfplumber
from src.extractors.base import BaseNativeExtractor, NativePageMetadata, NativeWord


class PlumberExtractor(BaseNativeExtractor):
    def extract_document(self, file_path: str) -> list[NativePageMetadata]:
        document_metadata = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                native_words = []
                for word in (page.extract_words() or []):
                    # Map pdfplumber coordinates (x0, top, x1, bottom) to [ymin, xmin, ymax, xmax]
                    bbox = [float(word["top"]), float(word["x0"]), float(word["bottom"]), float(word["x1"])]
                    native_words.append(NativeWord(text=word["text"], bbox=bbox))
                document_metadata.append(NativePageMetadata(
                    page_number=page_num,
                    raw_text=raw_text,
                    words=native_words,
                    dimensions=[float(page.width), float(page.height)]
                ))
        return document_metadata
