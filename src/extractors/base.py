from abc import ABC, abstractmethod
from typing import Annotated
from pydantic import BaseModel, Field


class NativeWord(BaseModel):
    text: str
    bbox: Annotated[list[float], Field(min_length=4, max_length=4)]  # [ymin, xmin, ymax, xmax]


class NativePageMetadata(BaseModel):
    page_number: int
    raw_text: str
    words: list[NativeWord]
    dimensions: list[float]  # [width, height]


class BaseNativeExtractor(ABC):
    @abstractmethod
    def extract_document(self, file_path: str) -> list[NativePageMetadata]:
        pass
