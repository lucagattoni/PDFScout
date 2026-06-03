"""Phase 1 calibration fixture: three text blocks at distinct x positions.

Generates grp_calibration_multipoint.pdf — NOT a test fixture.
Not registered in generate_all.py or manifest.json.

Generate once with:
    python -m tests.fixtures.generators.grp_calibration_multipoint

Block layout (all Helvetica 12pt, w_mm=60):
    Block A: x=20, y=50   — "Block A."
    Block B: x=60, y=80   — "Block B."
    Block C: x=100, y=110 — "Block C."
"""

from pathlib import Path

from tests.fixtures.generators._common import draw_text, make_pdf, save_pdf

_OUT_DIR = Path(__file__).parent.parent / "pdfs"
_FILENAME = "grp_calibration_multipoint.pdf"

_BLOCKS = [
    {"text": "Block A.", "x_mm": 20.0, "y_mm": 50.0, "w_mm": 60.0},
    {"text": "Block B.", "x_mm": 60.0, "y_mm": 80.0, "w_mm": 60.0},
    {"text": "Block C.", "x_mm": 100.0, "y_mm": 110.0, "w_mm": 60.0},
]


def generate(output_dir: Path) -> list[Path]:
    pdf = make_pdf()
    pdf.add_page()
    for b in _BLOCKS:
        draw_text(pdf, b["text"], b["x_mm"], b["y_mm"], w=b["w_mm"])
    return [save_pdf(pdf, output_dir, _FILENAME)]


if __name__ == "__main__":
    paths = generate(_OUT_DIR)
    print(f"Generated: {paths[0]}")
