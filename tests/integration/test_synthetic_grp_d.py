"""Group D — Schema-specific metadata (1–2 real Claude calls per test).

Node under test: window_parser_node + pioneer_validation_route.
Classifier mocked to target doc type; hierarchy mocked.

Phase 2 prerequisite: the extraction prompt must explicitly request optional
scientific_paper subfields before these tests will produce metadata assertions.
Until then, tests degrade to text-presence checks (see plan §Phase 2).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration._compare import _make_relation_response, assert_table_data

_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs"


async def _run_d_test(pdf_path: str, doc_type: str) -> list[dict]:
    from src.graph import build_app

    app = build_app(checkpointer=None)
    with (
        patch("src.nodes.classifier_node._classify", new=AsyncMock(return_value=doc_type)),
        patch(
            "src.nodes.hierarchy_node._call_api",
            new=AsyncMock(return_value=_make_relation_response([])),
        ),
    ):
        result = await app.ainvoke({"file_path": pdf_path})
    return result["hierarchical_document_tree"]["structured_payload"]


def _text_in_some(text: str, blocks: list[dict]) -> bool:
    import re
    import unicodedata

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).strip()).lower()

    target = norm(text)
    return any(target in norm(b["text"]) for b in blocks)


@pytest.mark.e2e
@pytest.mark.grp_d
class TestGroupD:
    async def test_d1_table_data(self):
        """Invoice table with 1 header row + 3 data rows → table_data metadata."""
        blocks = await _run_d_test(str(_PDFS / "grp_d_table_data.pdf"), "invoice")
        table_blocks = [b for b in blocks if b["type"] == "table"]
        assert table_blocks, "No table block found in D1 output"
        table = table_blocks[0]
        if table.get("metadata", {}).get("table_data"):
            assert_table_data(
                table,
                expected_rows=4,  # 1 header + 3 data
                expected_cols=4,
                header_row_count=1,
                expected_values=["Premium Widget", "Standard Widget", "Installation"],
            )
        else:
            # Fallback: assert the table text contains the data
            for val in ["Premium Widget", "Standard Widget", "Installation"]:
                assert _text_in_some(val, blocks), f"Expected '{val}' in some block"

    async def test_d2_bibliographic(self):
        """Scientific paper title + 3 authors → bibliographic metadata."""
        blocks = await _run_d_test(str(_PDFS / "grp_d_bibliographic.pdf"), "scientific_paper")
        authors = ["Alice Johnson", "Bob Martinez", "Carol Chen"]
        # Check bibliographic subfield if populated
        for author in authors:
            bib_populated = any(
                author in str(b.get("metadata", {}).get("bibliographic", {}).get("authors", []))
                for b in blocks
            )
            if not bib_populated:
                assert _text_in_some(author, blocks), (
                    f"Author '{author}' not found in any block text or bibliographic metadata"
                )

    async def test_d3_section(self):
        """Section heading 2. Methodology → section metadata."""
        blocks = await _run_d_test(str(_PDFS / "grp_d_section.pdf"), "scientific_paper")
        heading_blocks = [b for b in blocks if b["type"] == "heading"]
        assert heading_blocks, "No heading block found in D3 output"
        heading = heading_blocks[0]
        section = heading.get("metadata", {}).get("section", {})
        if section:
            assert "2" in section.get("section_number", ""), (
                f"section_number should contain '2', got {section.get('section_number')!r}"
            )
            assert "Methodology" in section.get("section_title", ""), (
                f"section_title should contain 'Methodology', got {section.get('section_title')!r}"
            )
        else:
            assert _text_in_some("Methodology", blocks), "Expected 'Methodology' in some block"

    async def test_d4_reference(self):
        """3 numbered reference entries → reference metadata with year."""
        blocks = await _run_d_test(str(_PDFS / "grp_d_reference.pdf"), "scientific_paper")
        assert _text_in_some("[1]", blocks), "Reference [1] not found"
        assert _text_in_some("[2]", blocks), "Reference [2] not found"
        assert _text_in_some("[3]", blocks), "Reference [3] not found"
        for block in blocks:
            ref = block.get("metadata", {}).get("reference", {})
            if ref and "year" in ref:
                assert isinstance(ref["year"], int), (
                    f"reference.year should be an integer, got {type(ref['year'])}"
                )

    async def test_d5_figure_table(self):
        """Figure with 'Figure 1:' caption → figure_table metadata."""
        blocks = await _run_d_test(str(_PDFS / "grp_d_figure_table.pdf"), "scientific_paper")
        assert _text_in_some("Figure 1", blocks), "Expected 'Figure 1' in some block"
        for block in blocks:
            ft = block.get("metadata", {}).get("figure_table", {})
            if ft and "label" in ft:
                assert "Figure 1" in ft["label"], (
                    f"figure_table.label should contain 'Figure 1', got {ft['label']!r}"
                )
                caption = ft.get("caption", "")
                assert "Distribution of block types" in caption or _text_in_some(
                    "Distribution of block types", blocks
                ), (
                    "caption text 'Distribution of block types' not found in figure_table.caption or any block"
                )
                # referenced_block_id is not asserted (non-deterministic)
                break
