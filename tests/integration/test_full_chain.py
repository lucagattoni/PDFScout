"""Full-chain integration test — no mocks, all nodes real.

Reuses the B1 invoice PDF. Verifies the entire classifier → extraction → hierarchy chain.
"""

from pathlib import Path

import pytest

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"


@pytest.mark.e2e
@pytest.mark.grp_b
@pytest.mark.integration_chain
class TestFullChain:
    async def test_invoice_full_pipeline(self):
        """End-to-end: invoice PDF → document_type='invoice', table block with table_data,
        no schema-validation warnings."""
        from src.graph import build_app

        app = build_app(checkpointer=None)
        result = await app.ainvoke({"file_path": str(_PDFS / "grp_b_invoice.pdf")})

        tree = result["hierarchical_document_tree"]
        assert tree["document_type"] == "invoice", (
            f"Expected document_type='invoice', got {tree['document_type']!r}"
        )

        blocks = tree["structured_payload"]
        table_blocks = [b for b in blocks if b["type"] == "table"]
        assert table_blocks, "Expected at least one table block in invoice output"

        table = table_blocks[0]
        assert table.get("metadata", {}).get("table_data") is not None, (
            "Expected metadata.table_data to be populated on invoice PDF (see Risk 8 if flaky)"
        )
        td = table["metadata"]["table_data"]
        assert td["total_rows"] >= 1
        assert td["total_cols"] >= 1

        # No schema-validation failures (orphan warnings are tolerated)
        warnings = tree["extraction_warnings"]
        schema_failures = [w for w in warnings if "failed schema validation" in w.lower()]
        assert not schema_failures, f"Schema validation failures: {schema_failures}"
