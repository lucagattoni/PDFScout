"""Group R — Real-document corpus tests."""

import hashlib
import json
from pathlib import Path

import pytest

from tests.fixtures._golden import CURRENT_SCHEMA_VERSION, load_golden
from tests.integration._compare import _normalize, _text_in_some, assert_valid_bbox_fields


def _norm_eq(a, b) -> bool:
    """Whitespace/case-insensitive equality for model-extracted strings.

    Byte equality is over-brittle for LLM-extracted metadata: the same title
    can come back as 'Physics-Informed' vs 'Physics-informed' between runs or
    model versions. The assertion's intent is 'the value was captured', so
    compare normalized. Lists compare element-wise under the same rule."""
    if isinstance(a, str) and isinstance(b, str):
        na, nb = _normalize(a).lower(), _normalize(b).lower()
        # Hyphenation at PDF line breaks is read inconsistently between runs
        # ('task-specific' vs 'taskspecific') — canonicalize both sides.
        return na == nb or na.replace("-", "") == nb.replace("-", "")
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_norm_eq(x, y) for x, y in zip(a, b))
    return a == b


_REAL_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs" / "real"
_MANIFEST = Path(__file__).parent.parent / "fixtures" / "real_manifest.json"


def _manifest_skip_reason(slot_id: str) -> str | None:
    """Slots can opt out of routine e2e runs via `skip_e2e_reason` in the
    manifest (e.g. large documents whose runs are deferred for cost)."""
    for entry in json.loads(_MANIFEST.read_text()):
        if entry.get("slot_id") == slot_id:
            return entry.get("skip_e2e_reason")
    return None


async def _run_pipeline(pdf_path: Path) -> dict:
    from src.graph import build_app

    app = build_app(checkpointer=None)
    return await app.ainvoke({"file_path": str(pdf_path)})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_metadata_required(blocks: list[dict], golden: dict) -> None:
    for key, expected in golden["metadata_required"].items():
        found = any(
            _norm_eq(b.get("metadata", {}).get("bibliographic", {}).get(key), expected)
            for b in blocks
        )
        assert found, f"metadata_required[{key!r}]={expected!r} not found in any block"


def _log_metadata_deferred(blocks: list[dict], golden: dict) -> None:
    for key, expected in golden.get("metadata_deferred", {}).items():
        found = any(
            b.get("metadata", {}).get("bibliographic", {}).get(key) == expected for b in blocks
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
    @pytest.mark.parametrize(
        "slot_id",
        [
            "sp-1",
            "sp-2",
            "sp-3",
            "sp-4",
            "sp-5",
            "sp-6",
            "inv-1",
            "inv-2",
            "inv-3",
            "inv-4",
            "inv-5",
            "bc-1",
            "bc-2",
            "bc-3",
            "bc-4",
        ],
    )
    async def test_real_doc(self, slot_id):
        skip_reason = _manifest_skip_reason(slot_id)
        if skip_reason:
            pytest.skip(f"{slot_id}: {skip_reason}")

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
            assert _text_in_some(fragment, blocks), f"Fragment {fragment!r} not found in any block"

        if golden.get("metadata_required"):
            _assert_metadata_required(blocks, golden)
        if golden.get("metadata_deferred"):
            _log_metadata_deferred(blocks, golden)
        for ta in golden.get("table_assertions", []):
            _assert_table_dimensions(blocks, ta)
