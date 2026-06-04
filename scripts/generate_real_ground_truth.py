"""C2 — Generate golden ground-truth files from multi-run pipeline consensus.

Usage:
    python scripts/generate_real_ground_truth.py (--slot inv-1,inv-2 | --all) \
        [--runs 5] [--force] [--dry-run]

Does NOT invoke C1.  Run download_real_fixtures.py before this script.
"""
import argparse
import asyncio
import json
import logging
import math
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_MANIFEST_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "real_manifest.json"
_GOLDEN_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "real_golden"
_PDF_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "pdfs" / "real"

from tests.fixtures._golden import CURRENT_SCHEMA_VERSION  # noqa: E402

# httpx / anyio fire cleanup coroutines after asyncio.run() closes its loop; suppress the
# resulting "Event loop is closed" noise — it doesn't affect correctness.
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


def _percentile_80(values: list[int]) -> int:
    s = sorted(values)
    idx = round((len(s) - 1) * 0.8)
    return s[idx]


def _normalize(text: str) -> str:
    import re
    import unicodedata
    text = unicodedata.normalize("NFKC", text)
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    return text


async def _run_all_for_slot(pdf_path: Path, n_runs: int) -> list[tuple[int, dict]]:
    """Run the pipeline n_runs times sequentially in a single event loop."""
    from src.graph import build_app
    results = []
    for i in range(n_runs):
        app = build_app(checkpointer=None)
        result = await app.ainvoke({"file_path": str(pdf_path)})
        block_count = len(result["hierarchical_document_tree"]["structured_payload"])
        results.append((block_count, result))
    return results


def _derive_golden(slot_id: str, doc_type: str, runs_results: list[dict], pdf_sha256: str | None, n_runs: int, min_blocks_override: int | None) -> dict:
    block_lists = [r["hierarchical_document_tree"]["structured_payload"] for r in runs_results]
    classifications = [r["document_type"] for r in runs_results]
    raw_block_counts = [len(bl) for bl in block_lists]

    if min_blocks_override is not None:
        min_blocks = min_blocks_override
    else:
        # Apply a 15% safety margin so the floor tolerates runs slightly below the
        # 80th-percentile observation (LLM output varies ±10–20% on block count).
        min_blocks = max(1, int(_percentile_80(raw_block_counts) * 0.85))

    classification_counter = Counter(classifications)
    top_class, top_count = classification_counter.most_common(1)[0]
    classification_unstable = top_count < n_runs
    classification = top_class

    required_threshold = math.ceil(0.8 * n_runs)
    deferred_threshold = math.ceil(0.6 * n_runs)

    metadata_required: dict = {}
    metadata_deferred: dict = {}

    if doc_type == "scientific_paper":
        for key in ("title", "authors", "abstract", "doi"):
            values = []
            for bl in block_lists:
                found = None
                for b in bl:
                    val = b.get("metadata", {}).get("bibliographic", {}).get(key)
                    if val:
                        found = val
                        break
                values.append(found)
            non_null = [v for v in values if v is not None]
            if not non_null:
                continue
            value_counter = Counter(str(v) for v in non_null)
            best_val_str, best_count = value_counter.most_common(1)[0]
            # Recover the original typed value
            best_val = next(v for v in non_null if str(v) == best_val_str)
            if best_count >= required_threshold:
                metadata_required[key] = best_val
            elif best_count >= deferred_threshold:
                metadata_deferred[key] = best_val

    heading_texts: Counter = Counter()
    for bl in block_lists:
        seen_in_run = set()
        for b in bl:
            if b.get("type") == "heading":
                norm = _normalize(b.get("text", ""))
                if norm and norm not in seen_in_run:
                    heading_texts[norm] += 1
                    seen_in_run.add(norm)

    spot_check_fragments = [
        h for h, count in heading_texts.most_common()
        if count >= required_threshold
    ][:10]

    table_assertions: list[dict] = []
    if doc_type == "invoice":
        # Collect (rows, cols) tuples from table blocks, one entry per run
        run_table_dims: list[list[tuple]] = []
        for bl in block_lists:
            dims = []
            for b in bl:
                td = b.get("metadata", {}).get("table_data")
                if td:
                    dims.append((td["total_rows"], td["total_cols"]))
            run_table_dims.append(dims)

        # Find dimension pairs that appear (in some table block) in ≥required_threshold runs
        dim_presence: Counter = Counter()
        for run_dims in run_table_dims:
            for d in set(run_dims):
                dim_presence[d] += 1

        candidates = [
            {"min_rows": rows, "min_cols": cols}
            for (rows, cols), count in dim_presence.items()
            if count >= required_threshold
        ]
        # Only keep the assertion with the highest area to avoid flakiness from
        # smaller auxiliary blocks whose dimensions vary between runs.
        # Apply a 40% safety margin to min_rows: column count is stable (reflects
        # table structure), row count varies as LLM groups line items differently.
        if candidates:
            best = max(candidates, key=lambda ta: ta["min_rows"] * ta["min_cols"])
            table_assertions = [{
                "min_rows": max(2, int(best["min_rows"] * 0.6)),
                "min_cols": best["min_cols"],
            }]

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "slot_id": slot_id,
        "doc_type": doc_type,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pdf_sha256": pdf_sha256,
        "n_runs": n_runs,
        "raw_block_counts": raw_block_counts,
        "min_blocks": min_blocks,
        "classification": classification,
        "classification_unstable": classification_unstable,
        "metadata_required": metadata_required,
        "metadata_deferred": metadata_deferred,
        "spot_check_fragments": spot_check_fragments,
        "table_assertions": table_assertions,
        "stability_notes": "",
    }


def _write_json(data: dict, path: Path) -> None:
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


def _process_slot(entry: dict, n_runs: int, force: bool, dry_run: bool) -> None:
    slot_id = entry["slot_id"]
    doc_type = entry["doc_type"]

    if entry.get("url") is None:
        print(f"  {slot_id}: no URL — NEEDS SELECTION; skipping")
        return

    pdf_path = _PDF_DIR / f"{slot_id}.pdf"
    if not pdf_path.exists():
        print(f"  {slot_id}: PDF missing — run download_real_fixtures.py first; skipping")
        return

    with open(pdf_path, "rb") as _f:
        _header = _f.read(5)
    if not _header.startswith(b"%PDF"):
        print(
            f"  {slot_id}: {pdf_path.name} is not a valid PDF (header={_header!r}) — "
            f"the server likely returned HTML; re-run: "
            f"download_real_fixtures.py --slot {slot_id} --force; skipping"
        )
        return

    golden_path = _GOLDEN_DIR / f"{slot_id}.json"
    if golden_path.exists() and not force:
        existing = json.loads(golden_path.read_text())
        recorded_sha = entry.get("pdf_sha256")
        if recorded_sha and existing.get("pdf_sha256") == recorded_sha:
            print(f"  {slot_id}: golden up-to-date (checksum matches), skipping (use --force to regenerate)")
            return

    if dry_run:
        print(f"  {slot_id}: [dry-run] would run {n_runs} pipeline runs")
        return

    print(f"  {slot_id}: running pipeline {n_runs} time(s)…")
    run_pairs = asyncio.run(_run_all_for_slot(pdf_path, n_runs))
    runs_results = []
    for i, (block_count, result) in enumerate(run_pairs):
        print(f"    run {i + 1}/{n_runs}: {block_count} blocks")
        runs_results.append(result)

    golden = _derive_golden(
        slot_id=slot_id,
        doc_type=doc_type,
        runs_results=runs_results,
        pdf_sha256=entry.get("pdf_sha256"),
        n_runs=n_runs,
        min_blocks_override=entry.get("min_blocks_override"),
    )

    _write_json(golden, golden_path)
    print(f"  {slot_id}: golden written → {golden_path.name} "
          f"(min_blocks={golden['min_blocks']}, "
          f"fragments={len(golden['spot_check_fragments'])}, "
          f"table_assertions={len(golden['table_assertions'])})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate real-document golden files")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slot", help="Comma-separated slot IDs to process")
    group.add_argument("--all", action="store_true", help="Process all slots with non-null URLs")
    parser.add_argument("--runs", type=int, default=5, help="Number of pipeline runs per slot (default: 5)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if golden file exists and checksum matches")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without making API calls")
    args = parser.parse_args()

    manifest: list = json.loads(_MANIFEST_PATH.read_text())

    if args.slot:
        selected = set(args.slot.split(","))
        entries = [e for e in manifest if e["slot_id"] in selected]
        if not entries:
            print("No entries matched the --slot filter.")
            return 0
    else:
        entries = manifest

    print(f"Processing {len(entries)} slot(s) with {args.runs} run(s) each…")
    for entry in entries:
        _process_slot(entry, n_runs=args.runs, force=args.force, dry_run=args.dry_run)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
