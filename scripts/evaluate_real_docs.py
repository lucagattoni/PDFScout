"""C4 — Offline regression evaluator for real-document corpus.

Runs the pipeline once per slot and compares against committed golden files.
Produces a JSON report without pytest overhead.

Usage:
    python scripts/evaluate_real_docs.py [--slot sp-1,inv-2] [--output-dir reports/]
"""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_MANIFEST_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "real_manifest.json"
_PDF_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "pdfs" / "real"


def _try_assert(fn, *args, **kwargs) -> tuple[bool, str]:
    try:
        fn(*args, **kwargs)
        return True, ""
    except AssertionError as e:
        return False, str(e)


async def _run_pipeline(pdf_path: Path) -> dict:
    from src.graph import build_app
    app = build_app(checkpointer=None)
    return await app.ainvoke({"file_path": str(pdf_path)})


def _text_in_some(fragment: str, blocks: list[dict]) -> bool:
    from tests.integration._compare import _text_in_some as _cmp_text_in_some
    return _cmp_text_in_some(fragment, blocks)


def _evaluate_slot(entry: dict, golden: dict) -> dict:
    from tests.integration._compare import assert_valid_bbox_fields

    slot_id = entry["slot_id"]
    doc_type = entry["doc_type"]

    pdf_path = _PDF_DIR / f"{slot_id}.pdf"
    if not pdf_path.exists():
        return {
            "slot_id": slot_id,
            "doc_type": doc_type,
            "blocks_actual": None,
            "blocks_min_required": None,
            "text_check": None,
            "metadata_required_pass": None,
            "metadata_deferred_mismatches": [],
            "table_assertions_pass": None,
            "verdict": "SKIP",
            "skip_reason": "PDF not present",
        }

    print(f"  {slot_id}: running pipeline…", end=" ", flush=True)
    result = asyncio.run(_run_pipeline(pdf_path))
    blocks = result["hierarchical_document_tree"]["structured_payload"]
    blocks_actual = len(blocks)
    print(f"{blocks_actual} blocks")

    errors = []

    # Schema validity
    ok, msg = _try_assert(assert_valid_bbox_fields, blocks)
    if not ok:
        errors.append(f"bbox: {msg}")
    for b in blocks:
        if not all(k in b for k in ("block_id", "type", "bbox")):
            errors.append("schema: block missing required field")
            break

    # Classification
    if result["document_type"] != golden["doc_type"]:
        errors.append(
            f"classification: expected {golden['doc_type']!r}, got {result['document_type']!r}"
        )

    # Block count
    blocks_min_required = golden.get("min_blocks")
    if blocks_min_required is not None and blocks_actual < blocks_min_required:
        errors.append(f"blocks: got {blocks_actual}, expected ≥{blocks_min_required}")

    # Spot-check text
    text_check = True
    for fragment in golden.get("spot_check_fragments", []):
        if not _text_in_some(fragment, blocks):
            text_check = False
            errors.append(f"text: {fragment!r} not found")

    # Metadata required
    metadata_required_pass = True
    for key, expected in golden.get("metadata_required", {}).items():
        found = any(
            b.get("metadata", {}).get("bibliographic", {}).get(key) == expected
            for b in blocks
        )
        if not found:
            metadata_required_pass = False
            errors.append(f"metadata_required[{key!r}]={expected!r} not found")

    # Metadata deferred (WARN only — never FAIL)
    metadata_deferred_mismatches = []
    for key, expected in golden.get("metadata_deferred", {}).items():
        found = any(
            b.get("metadata", {}).get("bibliographic", {}).get(key) == expected
            for b in blocks
        )
        if not found:
            metadata_deferred_mismatches.append(key)

    # Table assertions
    table_assertions_pass = True
    for ta in golden.get("table_assertions", []):
        found = any(
            (td := b.get("metadata", {}).get("table_data"))
            and td["total_rows"] >= ta["min_rows"]
            and td["total_cols"] >= ta["min_cols"]
            for b in blocks
        )
        if not found:
            table_assertions_pass = False
            errors.append(f"table: no block with ≥{ta['min_rows']}×{ta['min_cols']}")

    if errors:
        verdict = "FAIL"
    elif metadata_deferred_mismatches:
        verdict = "WARN"
    else:
        verdict = "PASS"

    record = {
        "slot_id": slot_id,
        "doc_type": doc_type,
        "blocks_actual": blocks_actual,
        "blocks_min_required": blocks_min_required,
        "text_check": text_check,
        "metadata_required_pass": metadata_required_pass,
        "metadata_deferred_mismatches": metadata_deferred_mismatches,
        "table_assertions_pass": table_assertions_pass,
        "verdict": verdict,
    }
    if errors:
        record["errors"] = errors
    return record


def _write_report(data: dict, path: Path) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        Path(tmp).rename(path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate real-document corpus against golden files")
    parser.add_argument("--slot", help="Comma-separated slot IDs to evaluate")
    parser.add_argument("--output-dir", default=".", help="Directory for the JSON report (default: cwd)")
    args = parser.parse_args()

    from tests.fixtures._golden import load_golden

    manifest: list = json.loads(_MANIFEST_PATH.read_text())
    selected = set(args.slot.split(",")) if args.slot else None
    entries = [e for e in manifest if selected is None or e["slot_id"] in selected]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = output_dir / f"{timestamp}-evaluation.json"

    print(f"Evaluating {len(entries)} slot(s)…")

    results = []
    for entry in entries:
        slot_id = entry["slot_id"]
        golden = load_golden(slot_id)
        if not golden:
            print(f"  {slot_id}: no golden file — SKIP")
            results.append({
                "slot_id": slot_id,
                "doc_type": entry["doc_type"],
                "blocks_actual": None,
                "blocks_min_required": None,
                "text_check": None,
                "metadata_required_pass": None,
                "metadata_deferred_mismatches": [],
                "table_assertions_pass": None,
                "verdict": "SKIP",
                "skip_reason": "no golden file",
            })
            continue

        if entry.get("url") is None:
            print(f"  {slot_id}: no URL set — SKIP")
            results.append({
                "slot_id": slot_id,
                "doc_type": entry["doc_type"],
                "blocks_actual": None,
                "blocks_min_required": None,
                "text_check": None,
                "metadata_required_pass": None,
                "metadata_deferred_mismatches": [],
                "table_assertions_pass": None,
                "verdict": "SKIP",
                "skip_reason": "no URL — NEEDS SELECTION",
            })
            continue

        result = _evaluate_slot(entry, golden)
        results.append(result)

    summary = {
        "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        "warn": sum(1 for r in results if r["verdict"] == "WARN"),
        "skip": sum(1 for r in results if r["verdict"] == "SKIP"),
        "fail": sum(1 for r in results if r["verdict"] == "FAIL"),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "slots_evaluated": len(results),
        "results": results,
        "summary": summary,
    }

    _write_report(report, report_path)
    print(f"\nReport written: {report_path}")
    print(f"Summary: PASS={summary['pass']} WARN={summary['warn']} SKIP={summary['skip']} FAIL={summary['fail']}")

    return 1 if summary["fail"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
