"""C1 — Download real PDF fixtures and record checksums in real_manifest.json.

Usage:
    python scripts/download_real_fixtures.py [--slot inv-1,inv-2] [--force] [--dry-run]
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx

_PROJECT_ROOT = Path(__file__).parent.parent
_MANIFEST_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "real_manifest.json"
_PDF_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "pdfs" / "real"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _download(url: str, dest: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        fd, tmp = tempfile.mkstemp(dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=65536):
                    f.write(chunk)
            Path(tmp).rename(dest)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _fetch_entry(entry: dict, force: bool, dry_run: bool) -> bool:
    """Process one manifest entry. Returns True on success, False on fetch failure."""
    slot_id = entry["slot_id"]
    url = entry.get("url")

    if url is None:
        print(f"  {slot_id}: no URL set — NEEDS SELECTION (skipping)")
        return True

    dest = _PDF_DIR / f"{slot_id}.pdf"

    if dest.exists() and not force:
        computed = _sha256_file(dest)
        recorded = entry.get("pdf_sha256")
        if recorded is None:
            print(f"  {slot_id}: file present, recording sha256 (no download needed)")
            if not dry_run:
                entry["pdf_sha256"] = computed
                entry["size_bytes"] = dest.stat().st_size
            return True
        if computed == recorded:
            print(f"  {slot_id}: up-to-date (checksum matches)")
            return True
        print(f"  {slot_id}: WARNING — checksum mismatch; re-downloading")

    print(f"  {slot_id}: downloading from {url}")
    if dry_run:
        print(f"  {slot_id}: [dry-run] would download {url}")
        return True

    _PDF_DIR.mkdir(parents=True, exist_ok=True)
    urls_to_try = [url]
    if entry.get("fallback_url"):
        urls_to_try.append(entry["fallback_url"])

    for attempt_url in urls_to_try:
        try:
            _download(attempt_url, dest)
            computed = _sha256_file(dest)
            entry["pdf_sha256"] = computed
            entry["size_bytes"] = dest.stat().st_size
            print(f"  {slot_id}: OK ({entry['size_bytes']} bytes, sha256={computed[:16]}…)")
            return True
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if attempt_url == urls_to_try[-1]:
                print(f"  {slot_id}: ERROR — HTTP {status} from {attempt_url}")
                return False
            print(f"  {slot_id}: HTTP {status} from primary; trying fallback")
        except Exception as exc:
            if attempt_url == urls_to_try[-1]:
                print(f"  {slot_id}: ERROR — {exc}")
                return False
            print(f"  {slot_id}: {exc} from primary; trying fallback")

    return False


def _write_manifest(manifest: list, path: Path) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
        Path(tmp).rename(path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Download real PDF fixtures")
    parser.add_argument("--slot", help="Comma-separated slot IDs to process")
    parser.add_argument("--force", action="store_true", help="Re-download even if checksum matches")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without downloading")
    args = parser.parse_args()

    manifest: list = json.loads(_MANIFEST_PATH.read_text())

    selected = set(args.slot.split(",")) if args.slot else None

    entries_to_process = [e for e in manifest if selected is None or e["slot_id"] in selected]

    if not entries_to_process:
        print("No entries matched the --slot filter.")
        return 0

    print(f"Processing {len(entries_to_process)} slot(s)…")
    failures = []
    for entry in entries_to_process:
        ok = _fetch_entry(entry, force=args.force, dry_run=args.dry_run)
        if not ok:
            failures.append(entry["slot_id"])

    if not args.dry_run:
        _write_manifest(manifest, _MANIFEST_PATH)
        print(f"\nManifest updated: {_MANIFEST_PATH}")

    if failures:
        print(f"\nFailed slots: {', '.join(failures)}")
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
