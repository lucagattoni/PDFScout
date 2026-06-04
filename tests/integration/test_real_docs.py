"""Group R — Real-document corpus tests."""
import hashlib
from pathlib import Path

import pytest

from tests.fixtures._golden import load_golden
from tests.integration._compare import _text_in_some, assert_valid_bbox_fields

_REAL_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs" / "real"
CURRENT_SCHEMA_VERSION = 1


async def _run_pipeline(pdf_path: Path) -> dict:
    from src.graph import build_app
    app = build_app(checkpointer=None)
    return await app.ainvoke({"file_path": str(pdf_path)})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_metadata_required(blocks: list[dict], golden: dict) -> None:
    for key, expected in golden["metadata_required"].items():
        found = any(
            b.get("metadata", {}).get("bibliographic", {}).get(key) == expected
            for b in blocks
        )
        assert found, f"metadata_required[{key!r}]={expected!r} not found in any block"


def _log_metadata_deferred(blocks: list[dict], golden: dict) -> None:
    for key, expected in golden.get("metadata_deferred", {}).items():
        found = any(
            b.get("metadata", {}).get("bibliographic", {}).get(key) == expected
            for b in blocks
        )
        if not found:
            print(f"[grp_r deferred] {key!r}: expected {expected!r} not found in any block")


def _assert_table_dimensions(blocks: list[dict], ta: dict) -> None:
    for b in blocks:
        td = b.get("metadata", {}).get("table_data")
        if td and td["total_rows"] >= ta["min_rows"] and td["total_cols"] >= ta["min_cols"]:
            return
    raise AssertionError(
        f"No table block found with ≥{ta['min_rows']} rows and ≥{ta['min_cols']} cols"
    )


@pytest.mark.e2e
@pytest.mark.grp_r
class TestRealDocs:
    @pytest.mark.parametrize("slot_id", [
        "sp-1", "sp-2", "sp-3", "sp-4", "sp-5", "sp-6",
        "inv-1", "inv-2", "inv-3", "inv-4", "inv-5",
        "bc-1", "bc-2", "bc-3", "bc-4",
    ])
    async def test_real_doc(self, slot_id):
        golden = load_golden(slot_id)
        if not golden:
            pytest.skip(f"{slot_id}: no golden file — run generate_real_ground_truth.py first")

        assert golden.get("schema_version") == CURRENT_SCHEMA_VERSION, (
            f"{slot_id}: golden schema_version mismatch — re-run generate_real_ground_truth.py"
        )

        pdf_path = _REAL_PDFS / f"{slot_id}.pdf"
        if not pdf_path.exists():
            pytest.skip(f"{slot_id}: PDF not present — run download_real_fixtures.py first")

        actual_sha = _sha256(pdf_path)
        if golden["pdf_sha256"] and actual_sha != golden["pdf_sha256"]:
            pytest.fail(
                f"{slot_id}: PDF checksum mismatch — "
                "re-run generate_real_ground_truth.py after download"
            )

        result = await _run_pipeline(pdf_path)
        blocks = result["hierarchical_document_tree"]["structured_payload"]

        for b in blocks:
            assert "block_id" in b and "type" in b and "bbox" in b
        assert_valid_bbox_fields(blocks)

        assert result["document_type"] == golden["doc_type"], (
            f"{slot_id}: expected doc_type={golden['doc_type']!r}, got {result['document_type']!r}"
        )

        assert len(blocks) >= golden["min_blocks"], (
            f"Got {len(blocks)} blocks, expected ≥{golden['min_blocks']}"
        )

        for fragment in golden["spot_check_fragments"]:
            assert _text_in_some(fragment, blocks), (
                f"Fragment {fragment!r} not found in any block"
            )

        if golden.get("metadata_required"):
            _assert_metadata_required(blocks, golden)
        if golden.get("metadata_deferred"):
            _log_metadata_deferred(blocks, golden)
        for ta in golden.get("table_assertions", []):
            _assert_table_dimensions(blocks, ta)
