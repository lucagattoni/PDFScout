"""Group B — Classifier accuracy (1 real Claude call per test).

Node under test: classifier_node.
Worker and hierarchy are mocked so only the classifier makes a real API call.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration._compare import _make_relation_response, _make_tool_use_response, _valid_block

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"
_GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


def _load_golden(name: str) -> dict:
    return json.loads((_GOLDEN / f"{name}.json").read_text())


async def _run_b_test(pdf_path: str) -> dict:
    from src.graph import build_app

    app = build_app(checkpointer=None)
    with (
        patch(
            "src.nodes.worker_node._call_api",
            new=AsyncMock(return_value=_make_tool_use_response([_valid_block(1)])),
        ),
        patch(
            "src.nodes.hierarchy_node._call_api",
            new=AsyncMock(return_value=_make_relation_response([])),
        ),
    ):
        result = await app.ainvoke({"file_path": pdf_path})
    return result


@pytest.mark.e2e
@pytest.mark.grp_b
class TestGroupB:
    async def test_b1_invoice(self):
        golden = _load_golden("grp_b_invoice")
        result = await _run_b_test(str(_PDFS / "grp_b_invoice.pdf"))
        doc_type = result["hierarchical_document_tree"]["document_type"]
        assert doc_type == golden["expected"]["document_type"], (
            f"Expected document_type={golden['expected']['document_type']!r}, got {doc_type!r}"
        )

    async def test_b2_scientific_paper(self):
        golden = _load_golden("grp_b_scientific_paper")
        result = await _run_b_test(str(_PDFS / "grp_b_scientific_paper.pdf"))
        doc_type = result["hierarchical_document_tree"]["document_type"]
        assert doc_type == golden["expected"]["document_type"], (
            f"Expected document_type={golden['expected']['document_type']!r}, got {doc_type!r}"
        )
