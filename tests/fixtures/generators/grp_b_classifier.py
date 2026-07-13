"""Group B fixtures: classifier accuracy.

B1 — 1-page invoice (expected: document_type == "invoice")
B2 — 1-page scientific paper (expected: document_type == "scientific_paper")
"""

import json
from pathlib import Path

from tests.fixtures.generators._common import (
    draw_table,
    draw_text,
    golden_meta,
    make_pdf,
    save_pdf,
)

_GOLDEN_DIR = Path(__file__).parent.parent / "golden"


def _make_b1_invoice() -> object:
    """Invoice PDF: company header, INVOICE #001, 4-column line items table."""
    pdf = make_pdf()
    pdf.add_page()

    draw_text(pdf, "ACME Corporation", 20, 25, font="Helvetica", size=16, style="B")
    draw_text(pdf, "123 Business Street, New York, NY 10001", 20, 35, size=10)
    draw_text(pdf, "Tel: (555) 123-4567  |  billing@acme.example", 20, 42, size=10)

    draw_text(pdf, "INVOICE #001", 20, 58, size=20, style="B")
    draw_text(pdf, "Date: 2026-06-01", 20, 70, size=11)
    draw_text(pdf, "Bill To: Contoso Ltd, 456 Client Ave, Chicago, IL 60601", 20, 78, size=11)

    draw_table(
        pdf,
        x_mm=20,
        y_mm=92,
        headers=["Description", "Qty", "Unit Price", "Total"],
        rows=[
            ["Widget Type A", "10", "$25.00", "$250.00"],
            ["Widget Type B", "5", "$40.00", "$200.00"],
            ["Service Fee", "1", "$75.00", "$75.00"],
        ],
        col_width=42.5,
        row_height=9,
    )

    draw_text(pdf, "Subtotal: $525.00", 120, 140, size=11)
    draw_text(pdf, "Tax (8%): $42.00", 120, 150, size=11)
    draw_text(pdf, "Total Due: $567.00", 120, 160, size=12, style="B")

    return pdf


def _make_b2_scientific_paper() -> object:
    """Scientific paper PDF: title, authors, Abstract heading, body, DOI."""
    pdf = make_pdf()
    pdf.add_page()

    draw_text(
        pdf,
        "Neural Approaches to Synthetic Document Analysis",
        20,
        25,
        size=16,
        style="B",
        align="C",
        w=170,
    )
    draw_text(pdf, "Alice Smith, Bob Jones, Carol Lee", 20, 40, size=11, align="C", w=170)
    draw_text(
        pdf, "Department of Computer Science, State University", 20, 48, size=10, align="C", w=170
    )

    draw_text(pdf, "Abstract", 20, 63, size=13, style="B")
    draw_text(
        pdf,
        (
            "This paper presents a novel approach to document analysis using synthetic "
            "fixtures and neural language models. We demonstrate that controlled PDF "
            "generation enables repeatable evaluation of extraction pipelines without "
            "relying on real-world document collections, which often contain sensitive "
            "or proprietary information."
        ),
        20,
        73,
        size=11,
        w=170,
    )

    draw_text(pdf, "1. Introduction", 20, 120, size=12, style="B")
    draw_text(
        pdf,
        (
            "Document understanding systems must handle a wide variety of layouts and "
            "content types. Existing benchmarks rely on real documents that cannot be "
            "freely distributed. We propose a synthetic generation approach that allows "
            "full control over document structure while remaining realistic."
        ),
        20,
        130,
        size=11,
        w=170,
    )

    draw_text(pdf, "DOI: 10.1234/synthpdf.2026.001", 20, 185, size=10)

    return pdf


def _write_golden_b(name: str, doc_type: str) -> None:
    golden = {
        "meta": golden_meta(name),
        "expected": {
            "document_type": doc_type,
            "blocks": [],
        },
    }
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (_GOLDEN_DIR / f"{name}.json").write_text(json.dumps(golden, indent=2))


def _make_b3_contract() -> object:
    """Contract PDF: SERVICE AGREEMENT with parties, recitals, clauses, signature block."""
    pdf = make_pdf()
    pdf.add_page()

    draw_text(pdf, "SERVICE AGREEMENT", 20, 25, size=18, style="B", align="C", w=170)
    draw_text(pdf, "Effective Date: January 1, 2026", 20, 38, size=10, align="C", w=170)

    draw_text(
        pdf,
        (
            "THIS AGREEMENT is entered into as of the date above by and between "
            'Alpha Corp, a Delaware corporation ("Client"), and Beta LLC, a New York '
            'limited liability company ("Service Provider").'
        ),
        20,
        52,
        size=10,
        w=170,
    )

    draw_text(pdf, "RECITALS", 20, 78, size=12, style="B")
    draw_text(
        pdf,
        "WHEREAS, Client wishes to obtain professional services from Service Provider;",
        20,
        88,
        size=10,
        w=170,
    )
    draw_text(
        pdf,
        (
            "NOW, THEREFORE, in consideration of the mutual covenants herein, "
            "the parties agree as follows:"
        ),
        20,
        98,
        size=10,
        w=170,
    )

    draw_text(pdf, "1. SERVICES", 20, 114, size=11, style="B")
    draw_text(
        pdf,
        (
            "Service Provider shall perform software development and consulting services "
            "as specified in Exhibit A attached hereto and incorporated by reference."
        ),
        20,
        124,
        size=10,
        w=170,
    )

    draw_text(pdf, "2. PAYMENT TERMS", 20, 140, size=11, style="B")
    draw_text(
        pdf,
        (
            "Client shall pay Service Provider a monthly retainer of $10,000 due within "
            "30 days of invoice. Late payments accrue interest at 1.5% per month."
        ),
        20,
        150,
        size=10,
        w=170,
    )

    draw_text(pdf, "3. GOVERNING LAW", 20, 166, size=11, style="B")
    draw_text(
        pdf,
        "This Agreement shall be governed by the laws of the State of New York.",
        20,
        176,
        size=10,
        w=170,
    )

    draw_text(
        pdf, "IN WITNESS WHEREOF, the parties have executed this Agreement.", 20, 196, size=10
    )

    draw_text(pdf, "CLIENT:", 20, 210, size=10, style="B")
    draw_text(pdf, "Alpha Corp", 20, 218, size=10)
    draw_text(pdf, "Signature: _______________________", 20, 226, size=10)
    draw_text(pdf, "Name: ___________________________", 20, 234, size=10)
    draw_text(pdf, "Date: ___________________________", 20, 242, size=10)

    draw_text(pdf, "SERVICE PROVIDER:", 110, 210, size=10, style="B")
    draw_text(pdf, "Beta LLC", 110, 218, size=10)
    draw_text(pdf, "Signature: _______________________", 110, 226, size=10)
    draw_text(pdf, "Name: ___________________________", 110, 234, size=10)
    draw_text(pdf, "Date: ___________________________", 110, 242, size=10)

    return pdf


def _make_b4_invoice_legal() -> object:
    """Vendor invoice with a 'Terms and Conditions' footer (adversarial: legal language but is an invoice)."""
    pdf = make_pdf()
    pdf.add_page()

    draw_text(pdf, "INVOICE #099", 20, 25, size=20, style="B")
    draw_text(pdf, "Date: 2026-06-01", 20, 38, size=11)
    draw_text(pdf, "From: Globex Supplies Inc, 789 Vendor Road, Austin, TX 78701", 20, 46, size=10)
    draw_text(pdf, "Bill To: Initech Ltd, 321 Client Blvd, Seattle, WA 98101", 20, 54, size=10)

    draw_table(
        pdf,
        x_mm=20,
        y_mm=68,
        headers=["Description", "Qty", "Unit Price", "Amount"],
        rows=[
            ["Office Supplies", "50", "$4.00", "$200.00"],
            ["Printer Cartridges", "10", "$22.00", "$220.00"],
            ["Shipping & Handling", "1", "$15.00", "$15.00"],
        ],
        col_width=42.5,
        row_height=9,
    )

    draw_text(pdf, "Subtotal: $435.00", 120, 118, size=11)
    draw_text(pdf, "Tax (9%): $39.15", 120, 128, size=11)
    draw_text(pdf, "Total Due: $474.15", 120, 138, size=12, style="B")
    draw_text(pdf, "Payment Due: 2026-07-01", 120, 148, size=10)

    draw_text(pdf, "TERMS AND CONDITIONS", 20, 170, size=10, style="B")
    draw_text(
        pdf,
        (
            "Payment is due within 30 days of invoice date. This invoice is governed by "
            "the laws of the State of Texas. Disputes shall be resolved by binding "
            "arbitration. No warranty is implied. Seller retains title to goods until "
            "payment is received in full."
        ),
        20,
        180,
        size=9,
        w=170,
    )

    return pdf


def generate(out_dir: Path) -> list[Path]:
    paths = []
    paths.append(save_pdf(_make_b1_invoice(), out_dir, "grp_b_invoice.pdf"))
    paths.append(save_pdf(_make_b2_scientific_paper(), out_dir, "grp_b_scientific_paper.pdf"))
    paths.append(save_pdf(_make_b3_contract(), out_dir, "grp_b_contract.pdf"))
    paths.append(save_pdf(_make_b4_invoice_legal(), out_dir, "grp_b_invoice_legal.pdf"))

    _write_golden_b("grp_b_invoice", "invoice")
    _write_golden_b("grp_b_scientific_paper", "scientific_paper")
    _write_golden_b("grp_b_contract", "contract")
    _write_golden_b("grp_b_invoice_legal", "invoice")

    return paths


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "pdfs"
    for p in generate(out):
        print(p)
