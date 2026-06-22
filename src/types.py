"""Core data types for the pipeline."""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class CharBox:
    """A detected character box with position, image, and metadata."""
    x: int
    y: int
    w: int
    h: int
    img: np.ndarray = field(default=None, repr=False)
    area: int = 0
    col_idx: int = 0
    row_idx: int = 0
    text: str = ""
    score: float = 0.0

    def __getitem__(self, idx):
        """Backwards-compatible tuple-style access for legacy consumers."""
        return (self.x, self.y, self.w, self.h, self.img, self.area,
                self.col_idx, self.row_idx, self.text, self.score)[idx]

    def to_dict(self) -> dict:
        return {
            'x': self.x, 'y': self.y, 'w': self.w, 'h': self.h,
            'col': self.col_idx + 1, 'row': self.row_idx + 1,
            'text': self.text, 'confidence': self.score,
        }


@dataclass
class OcrResult:
    """OCR recognition result for a single character."""
    x: int
    y: int
    w: int
    h: int
    col_idx: int
    row_idx: int
    original_text: str
    original_score: float
    ocr_text: str = ""
    ocr_score: float = 0.0
    expand_strategy: str = "none"

    def to_dict(self) -> dict:
        return {
            'x': self.x, 'y': self.y, 'w': self.w, 'h': self.h,
            'col': self.col_idx + 1, 'row': self.row_idx + 1,
            'text': self.ocr_text, 'confidence': self.ocr_score,
            'original_text': self.original_text,
            'original_score': self.original_score,
            'expand_strategy': self.expand_strategy,
        }


@dataclass
class Column:
    """A vertical (or horizontal) column of characters."""
    col_idx: int
    x_min: int
    x_max: int
    chars: list[CharBox] = field(default_factory=list)
