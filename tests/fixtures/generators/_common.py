"""Shared fpdf2 helpers and constants for all fixture generators."""

from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF

from src.config import MODEL

# ---------------------------------------------------------------------------
# Calibration constant — set after running Phase 0 calibration
# ---------------------------------------------------------------------------
# COORD_SCALE = <k>          # enable when calibrated (float, Claude-units per mm)
BBOX_ASSERTIONS_VIABLE = False  # set True only after calibration confirms stability

# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------
PAGE_W_MM: float = 210.0
PAGE_H_MM: float = 297.0
PAGE_W_PTS: float = 595.28
PAGE_H_PTS: float = 841.89

_PINNED_DATE = datetime(2000, 1, 1, tzinfo=UTC)
_LEFT_MARGIN = 20.0
_RIGHT_MARGIN = 20.0
_TOP_MARGIN = 20.0


class _PDFBase(FPDF):
    """FPDF subclass that pins the creation date for byte-for-byte reproducibility."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_creation_date(_PINNED_DATE)


def make_pdf() -> _PDFBase:
    """Return an A4 portrait PDF with pinned creation date and standard margins."""
    pdf = _PDFBase(orientation="P", unit="mm", format="A4")
    pdf.set_margins(_LEFT_MARGIN, _TOP_MARGIN, _RIGHT_MARGIN)
    pdf.set_auto_page_break(auto=False)
    return pdf


def draw_text(
    pdf: _PDFBase,
    text: str,
    x_mm: float,
    y_mm: float,
    *,
    font: str = "Helvetica",
    size: float = 12,
    style: str = "",
    w: float | None = None,
    h: float = 8,
    align: str = "L",
    ln: bool = True,
) -> None:
    """Place a single-line text cell at (x_mm, y_mm)."""
    pdf.set_xy(x_mm, y_mm)
    pdf.set_font(font, style=style, size=size)
    if w is None:
        w = PAGE_W_MM - _LEFT_MARGIN - _RIGHT_MARGIN
    pdf.cell(
        w, h, text, align=align, new_x="LMARGIN" if ln else "RIGHT", new_y="NEXT" if ln else "TOP"
    )


def draw_multiline(
    pdf: _PDFBase,
    text: str,
    x_mm: float,
    y_mm: float,
    *,
    font: str = "Helvetica",
    size: float = 12,
    style: str = "",
    w: float | None = None,
    h: float = 7,
) -> None:
    """Place wrapped text starting at (x_mm, y_mm)."""
    pdf.set_xy(x_mm, y_mm)
    pdf.set_font(font, style=style, size=size)
    if w is None:
        w = PAGE_W_MM - x_mm - _RIGHT_MARGIN
    pdf.multi_cell(w, h, text)


def draw_hline(pdf: _PDFBase, x_mm: float, y_mm: float, w_mm: float) -> None:
    """Draw a horizontal rule."""
    pdf.line(x_mm, y_mm, x_mm + w_mm, y_mm)


def draw_filled_rect(
    pdf: _PDFBase,
    x_mm: float,
    y_mm: float,
    w_mm: float,
    h_mm: float,
    fill_color: tuple[int, int, int] = (200, 200, 200),
) -> None:
    """Draw a filled rectangle (default light grey)."""
    pdf.set_fill_color(*fill_color)
    pdf.rect(x_mm, y_mm, w_mm, h_mm, style="F")


def draw_table(
    pdf: _PDFBase,
    x_mm: float,
    y_mm: float,
    headers: list[str],
    rows: list[list[str]],
    *,
    col_width: float = 40.0,
    row_height: float = 8.0,
) -> None:
    """Draw a bordered table with a bold header row at (x_mm, y_mm)."""
    pdf.set_xy(x_mm, y_mm)
    pdf.set_font("Helvetica", style="B", size=10)
    for h in headers:
        pdf.cell(col_width, row_height, h, border=1, align="C", new_x="RIGHT", new_y="TOP")
    pdf.ln(row_height)

    pdf.set_font("Helvetica", size=10)
    for row in rows:
        pdf.set_x(x_mm)
        for cell_val in row:
            pdf.cell(
                col_width,
                row_height,
                str(cell_val),
                border=1,
                align="C",
                new_x="RIGHT",
                new_y="TOP",
            )
        pdf.ln(row_height)


def save_pdf(pdf: _PDFBase, out_dir: Path, filename: str) -> Path:
    """Write the PDF to out_dir/filename and return the Path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    pdf.output(str(path))
    return path


def golden_meta(generator: str) -> dict:
    """Return the standard meta block for a golden file."""
    return {
        "generator": generator,
        "page_size_pts": [PAGE_W_PTS, PAGE_H_PTS],
        "coord_scale": None,  # null = pre-calibration; false = not viable; float = scale factor
        "model_version": MODEL,
        "created": "2026-06-03",
    }
