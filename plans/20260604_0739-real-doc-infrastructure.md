# Real-Document Infrastructure — Downloader, Ground Truth, and Test Runner

_Created: 2026-06-04 07:39_
_Updated: 2026-06-04 · all PDFs download-only (no commit); SP-1 and BC-3 moved to NEEDS SELECTION; evaluator output changed to JSON with datetime-prefix filename_
_Updated: 2026-06-04 · fix stale "conversion flags" / "convert" text; fix result key doc_type→document_type; add null-URL skip to C1; add schema_version+raw_block_counts to golden schema; add _assert_metadata_required/_assert_table_dimensions specs; introduce shared _golden.py; fix Phase 3 wording; replace redundant DA-3_
_Updated: 2026-06-04 · fix requests→httpx; add pyproject.toml grp_r marker requirement; specify _golden.py API; specify _run_pipeline; add min_blocks_override to manifest schema_
_Updated: 2026-06-04 · fix C2 metadata fields (year/journal_or_venue not in schema); specify manifest as JSON array; fix C1 null-sha logic; specify C1 write-back timing; clarify C2-C1 coupling; add --all/--dry-run to C2 CLI; specify spot_check_fragments selection; fill parametrize list; remove dead _load_manifest fixture; fix _load_golden naming; add empty-golden skip guard; add schema_version check; define _log_metadata_deferred; fix _assert_metadata_required spec; fix C4 assertion wrapping; fix Phase 4 verify condition_
_Updated: 2026-06-04 · implementation findings added for Phases 0–4 and 6_
_Updated: 2026-06-04 · plan review fixes: correct min_blocks formula, table-dims algo, threshold formulas, classification_unstable semantics, CURRENT_SCHEMA_VERSION single source of truth, Phase 6 verify note, DA-5, golden format example_

## Goal

Complement `20260603_1540-real-doc-test-corpus.md` with a concrete implementation plan
covering:

1. A **fixture downloader** that fetches the 15 real PDFs at test time — no PDF binary
   ever committed to the repository.
2. A **manifest** that records source URLs and checksums for every document.
3. A **ground-truth generator** that runs the pipeline N times and derives stable
   assertions from the consensus, then commits those golden files.
4. A **test runner** (`test_real_docs.py`, marker `grp_r`) that compares live pipeline
   output against the committed golden files.
5. An **offline evaluator** that produces a JSON regression report without spinning up
   pytest.

---

## Component overview

```
scripts/
  download_real_fixtures.py      # C1 — fetch / checksum
  generate_real_ground_truth.py  # C2 — multi-run consensus → golden JSON
  evaluate_real_docs.py          # C4 — offline diff report

tests/
  fixtures/
    real_manifest.json           # authoritative source-of-truth for all 15 slots
    _golden.py                   # shared golden loader; imported by C3 and C4
    real_golden/                 # committed golden files (one per slot)
      sp-1.json
      sp-2.json
      ...
      bc-4.json
  integration/
    test_real_docs.py            # C3 — grp_r pytest suite

docs/
  real_doc_workflow.md           # runbook for adding/updating corpus entries
```

All generated PDFs land in `tests/fixtures/pdfs/real/` which is already gitignored.

---

## C0 — Manifest (`real_manifest.json`)

Extends the selection criteria in the corpus plan with runtime fields needed by C1–C4.

### Schema

```jsonc
{
  "slot_id": "sp-1",              // matches golden file name and test parameterisation
  "doc_type": "scientific_paper", // classifier expected value
  "label": "...",
  "url": "https://arxiv.org/pdf/...",
  "fallback_url": null,           // secondary URL if primary returns 403/404
  "pdf_sha256": null,             // null until first successful download; filled by C1
  "size_bytes": null,             // filled by C1
  "license": "CC-BY-4.0",
  "memorisation_risk": null,      // null | "low" | "high"; informational only
  "min_blocks_override": null,    // integer; overrides percentile_80 floor for flaky slots
  "notes": ""
}
```

`pdf_sha256` is the SHA-256 of the downloaded binary.  It is written back by C1 the
first time a document is fetched and used by C1 on subsequent runs to detect upstream
changes.

The file is a **JSON array** of these objects:
```json
[
  {"slot_id": "sp-1", "doc_type": "scientific_paper", "url": "...", ...},
  {"slot_id": "inv-1", "doc_type": "invoice", "url": "...", ...}
]
```
C1 reads the full array, updates entries in-memory, and writes the array back atomically
at the end of the run.  Entries are looked up by `slot_id`.

### Initial entries

Derived from the corpus plan.  `pdf_sha256` and `size_bytes` left null until first run.

| slot_id | notes |
|---------|-------|
| sp-1    | NEEDS SELECTION: non-landmark arXiv paper, ≥13 pp, two-column, figures, numbered refs |
| sp-2    | NEEDS SELECTION: total PDF ≤4 pp; PRL preprint or 2-page workshop abstract |
| sp-3    | conditional on file size ≤5 MB |
| sp-4    | conditional on file size ≤5 MB |
| sp-5    | memorisation risk HIGH |
| sp-6    | conditional on file size ≤5 MB; scanned-quality axis |
| inv-1   | strzibny/invoice_printer, 20 KB |
| inv-2   | strzibny/invoice_printer, 24 KB |
| inv-3   | strzibny/invoice_printer, 72 KB |
| inv-4   | strzibny/invoice_printer, 175 KB |
| inv-5   | strzibny/invoice_printer, 48 KB |
| bc-1    | needs access verification |
| bc-2    | govinfo.gov mirror |
| bc-3    | NEEDS SELECTION: native PDF of public-domain text (no conversion) |
| bc-4    | govinfo.gov mirror |

---

## C1 — Downloader (`download_real_fixtures.py`)

### Responsibilities

1. Read `real_manifest.json`.
2. For each entry: if `url` is null, log `slot <id>: no URL set — NEEDS SELECTION` and
   skip gracefully (not an error; do NOT exit 1).
3. Resolve the target path `tests/fixtures/pdfs/real/<slot_id>.pdf`.
4. If the file exists on disk (gitignored), compute its SHA-256:
   - If `pdf_sha256` in manifest is **null** → record the computed SHA and size; skip
     download (file is already present; null just means it was never recorded).
   - If `pdf_sha256` **matches** computed SHA → skip (already fresh).
   - If `pdf_sha256` **does not match** → warn and re-download (upstream PDF changed).
5. Download from `url`; if HTTP 4xx/5xx, retry `fallback_url` if set.
6. Update `pdf_sha256` and `size_bytes` in the in-memory manifest entry.
7. After processing all entries, write the updated manifest array back to disk atomically
   (write to a temp file, then rename).  If C1 crashes before this point, unrecorded
   sha fields will be re-computed on the next run.
8. Exit 1 if any entry with a non-null URL could not be fetched.

### CLI

```
python scripts/download_real_fixtures.py [--slot sp-1,sp-2] [--force] [--dry-run]
```

`--force` re-downloads even if the checksum matches.
`--slot` restricts to a comma-separated list of slot IDs.

---

## C2 — Ground-truth generator (`generate_real_ground_truth.py`)

### When to run

Run manually — never in CI automatically.  The generator makes real API calls (≈7 calls
per document per run × 15 docs × 5 runs = 525 calls, ~$7–$15 at current pricing).
Output is committed and reviewed before merging.

### Algorithm

```
for each slot_id in manifest:
    if url is null: log "slot <id>: no URL — NEEDS SELECTION; skipping" and continue
    if pdf file does not exist: log "slot <id>: PDF missing — run download_real_fixtures.py; skipping" and continue
    run pipeline N times (default N=5) collecting all block lists
    derive golden assertions (see below)
    write tests/fixtures/real_golden/<slot_id>.json
```

C2 does **not** invoke C1.  It checks file existence only.  Run C1 before C2.

### Deriving stable assertions

**Block count:** `min_blocks = max(1, floor(percentile_80(block_counts_across_runs) × 0.85))`
This sets a floor: at least this many blocks must appear.  Using 80th percentile rather
than the minimum avoids a single bad run dragging the threshold down.  The 15% safety
margin absorbs LLM non-determinism (±10–20% block-count variance observed in practice).
If the manifest entry has a non-null `min_blocks_override`, use that value instead of
the computed floor and record it in the golden file.

**Classification:** C3 always asserts `result["document_type"] == golden["doc_type"]`.
`classification_unstable` is an informational flag stored in the golden file for human
review — it does NOT suppress the assertion.  If classification is genuinely unstable for
a slot, investigate the document (it may be ambiguous) or replace it; do not weaken C3.

**Metadata fields (scientific_paper only):** for each subfield of `metadata.bibliographic`
that the schema supports (`title`, `authors`, `abstract`, `doi`):

Let `required_threshold = ceil(0.8 × n_runs)` and `deferred_threshold = ceil(0.6 × n_runs)`.
For the default `--runs 5`: required=4, deferred=3.

- If the field value appears with the same string representation in ≥`required_threshold`
  runs: emit as `metadata_required`.
- If ≥`deferred_threshold` but < `required_threshold`: emit as `metadata_deferred`
  (soft assertion, log-only; never fails C3 or C4).
- Otherwise: omit entirely.

(`year` and `journal_or_venue` are NOT subfields of `metadata.bibliographic` in the
scientific_paper schema and must not be asserted here.)

**Spot-check text:** For each run, collect the full normalized `text` of all blocks
with `type == "heading"`.  A heading text H is included in `spot_check_fragments` if H
(after `_normalize`) appears in ≥`required_threshold` runs (ceil(0.8 × n_runs)) in a
block of type `heading`.  Cap at 10 fragments per document.  Paragraph body text is
excluded — headings are more stable across runs.  Invoices often produce zero fragments
(unstable or absent headings); this is expected and means no text-content assertion is
generated for those slots.

**Table dimensions (invoice only):** Collect `(total_rows, total_cols)` pairs from all
table blocks across runs.  A pair present in ≥`required_threshold` runs is a candidate.
Keep only the candidate with the largest area (rows × cols) to avoid flakiness from small
auxiliary blocks.  Apply a 40% safety margin to min_rows only:
`min_rows = max(2, floor(best_rows × 0.6))`.  Column count is stable and is left exact.
For multi-page invoices the pipeline splits table rows per page — assert column count only
(set `min_rows: 2`).

### Golden file format

```jsonc
{
  "schema_version": 1,             // bump manually when golden format changes
  "slot_id": "sp-1",
  "doc_type": "scientific_paper",
  "generated_at": "2026-06-04T12:00:00Z",
  "pdf_sha256": "abc123...",       // must match manifest at assert time
  "n_runs": 5,
  "raw_block_counts": [42, 45, 44, 43, 46],  // one entry per run; aids debugging
  "min_blocks": 43,                // max(1, floor(percentile_80(raw_block_counts) × 0.85))
  "classification": "scientific_paper",
  "classification_unstable": false,
  "metadata_required": {           // assert ≥1 block has metadata.bibliographic[key] == value
    "title": "<paper title>",
    "doi": "10.xxxx/..."
  },
  "metadata_deferred": {           // log-only; never fails the test
    "abstract": "<first sentence of abstract>"
  },
  "spot_check_fragments": [        // each must appear in ≥1 block's text (heading-only)
    "<section heading fragment>",
    "<another heading fragment>"
  ],
  "table_assertions": [],          // [{min_rows, min_cols}] for invoice docs
  "stability_notes": ""
}
```

### CLI

```
python scripts/generate_real_ground_truth.py (--slot sp-1,sp-2 | --all) [--runs 5] [--force] [--dry-run]
```

`--slot` / `--all` are mutually exclusive and one is required (no implicit "run all").
`--force` regenerates even when a golden file already exists and the checksum matches.
`--dry-run` prints which slots would be processed without making any API calls.
Without `--force`, skips a slot if its golden file exists and `pdf_sha256` matches.

---

## C3 — Test runner (`test_real_docs.py`)

### Structure

```python
from tests.fixtures._golden import CURRENT_SCHEMA_VERSION, load_golden
from tests.integration._compare import _text_in_some, assert_valid_bbox_fields

_REAL_PDFS = Path(__file__).parent.parent / "fixtures" / "pdfs" / "real"

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

        # checksum guard
        actual_sha = _sha256(pdf_path)
        if golden["pdf_sha256"] and actual_sha != golden["pdf_sha256"]:
            pytest.fail(
                f"{slot_id}: PDF checksum mismatch — "
                "re-run generate_real_ground_truth.py after download"
            )

        result = await _run_pipeline(pdf_path)
        blocks = result["hierarchical_document_tree"]["structured_payload"]

        # Tier 1 — schema
        for b in blocks:
            assert "block_id" in b and "type" in b and "bbox" in b
        assert_valid_bbox_fields(blocks)

        # Tier 2 — classification
        assert result["document_type"] == golden["doc_type"]

        # Tier 3 — completeness
        assert len(blocks) >= golden["min_blocks"], (
            f"Got {len(blocks)} blocks, expected ≥{golden['min_blocks']}"
        )

        # Tier 4 — spot-check text
        for fragment in golden["spot_check_fragments"]:
            assert _text_in_some(fragment, blocks), (
                f"Fragment {fragment!r} not found in any block"
            )

        # Tier 5 — metadata (scientific_paper and invoice only)
        if golden["metadata_required"]:
            _assert_metadata_required(blocks, golden)
        if golden["metadata_deferred"]:
            _log_metadata_deferred(blocks, golden)  # never fails
        for ta in golden.get("table_assertions", []):
            _assert_table_dimensions(blocks, ta)
```

### Private helpers in `test_real_docs.py`

```python
import hashlib

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _assert_metadata_required(blocks: list[dict], golden: dict) -> None:
    """For each (key, expected) in golden["metadata_required"], assert that at least
    one block has metadata.bibliographic[key] == expected.  scientific_paper only."""
    for key, expected in golden["metadata_required"].items():
        found = any(
            b.get("metadata", {}).get("bibliographic", {}).get(key) == expected
            for b in blocks
        )
        assert found, (
            f"metadata_required[{key!r}]={expected!r} not found in any block"
        )

def _log_metadata_deferred(blocks: list[dict], golden: dict) -> None:
    """Log deferred metadata mismatches to stdout.  Never raises."""
    for key, expected in golden.get("metadata_deferred", {}).items():
        found = any(
            b.get("metadata", {}).get("bibliographic", {}).get(key) == expected
            for b in blocks
        )
        if not found:
            print(f"[grp_r deferred] {key!r}: expected {expected!r} not found in any block")

def _assert_table_dimensions(blocks: list[dict], ta: dict) -> None:
    """Assert at least one block has table_data.total_rows >= min_rows and
    total_cols >= min_cols."""
    for b in blocks:
        td = b.get("metadata", {}).get("table_data")
        if td and td["total_rows"] >= ta["min_rows"] and td["total_cols"] >= ta["min_cols"]:
            return
    raise AssertionError(
        f"No table block found with ≥{ta['min_rows']} rows and ≥{ta['min_cols']} cols"
    )
```

These helpers are private to `test_real_docs.py`.  They are NOT added to `_compare.py`
(too real-doc-specific to be general).

### `CURRENT_SCHEMA_VERSION` — single source of truth

`CURRENT_SCHEMA_VERSION = 1` lives in `tests/fixtures/_golden.py` and is imported by
both C2 and C3.  It must never be re-declared in either file.  When bumping the schema
version, change the constant once in `_golden.py`, then re-run C2 to regenerate golden
files.

### Shared golden loader (`tests/fixtures/_golden.py`)

```python
import json
from pathlib import Path

_GOLDEN_DIR = Path(__file__).parent / "real_golden"

def load_golden(slot_id: str) -> dict:
    path = _GOLDEN_DIR / f"{slot_id}.json"
    if not path.exists():
        return {}          # caller treats empty dict as "no golden → SKIP"
    return json.loads(path.read_text())
```

Imported by both `test_real_docs.py` (C3) and `evaluate_real_docs.py` (C4).

### `_run_pipeline` helper in `test_real_docs.py`

```python
from src.graph import build_app

async def _run_pipeline(pdf_path: Path) -> dict:
    app = build_app(checkpointer=None)
    return await app.ainvoke({"file_path": str(pdf_path)})
```

The classifier is **not mocked** — grp_r tests the full pipeline end-to-end (unlike
grp_i which mocks only the classifier).  No `patch` context manager is used.

### Required changes to conftest.py

Add `"grp_r"` to the `api_groups` list in `require_real_api_key`:

```python
api_groups = [
    "grp_b", "grp_c", "grp_d", "grp_e",
    "grp_f", "grp_g", "grp_h", "grp_i", "grp_r",  # ← add grp_r
]
```

### Required addition to `_compare.py`

```python
def _text_in_some(fragment: str, blocks: list[dict]) -> bool:
    """Return True if the normalised fragment appears in any block's text."""
    norm_fragment = _normalize(fragment).lower()
    return any(
        norm_fragment in _normalize(b.get("text", "")).lower()
        for b in blocks
    )
```

---

## C4 — Offline evaluator (`evaluate_real_docs.py`)

Produces a JSON regression report without pytest overhead.  Useful for iterative
development and pre-commit sanity checks.

```
python scripts/evaluate_real_docs.py [--slot sp-1,inv-2] [--output-dir reports/]
```

Output file: `<output-dir>/YYYYMMDD_HHMM-evaluation.json` (datetime prefix, same
convention as plan files).  Default output-dir is the current working directory.

Output format:

```jsonc
{
  "generated_at": "2026-06-04T12:00:00Z",
  "slots_evaluated": 15,
  "results": [
    {
      "slot_id": "sp-1",
      "doc_type": "scientific_paper",
      "blocks_actual": 51,
      "blocks_min_required": 42,
      "text_check": true,
      "metadata_required_pass": true,
      "metadata_deferred_mismatches": [],
      "verdict": "PASS"
    },
    {
      "slot_id": "sp-2",
      "doc_type": "scientific_paper",
      "blocks_actual": null,
      "blocks_min_required": null,
      "text_check": null,
      "metadata_required_pass": null,
      "metadata_deferred_mismatches": [],
      "verdict": "SKIP",
      "skip_reason": "PDF not present"
    },
    {
      "slot_id": "bc-2",
      "doc_type": "baseline_core",
      "blocks_actual": 18,
      "blocks_min_required": 15,
      "text_check": true,
      "metadata_required_pass": true,
      "metadata_deferred_mismatches": ["abstract"],
      "verdict": "WARN"
    }
  ],
  "summary": {
    "pass": 12,
    "warn": 1,
    "skip": 2,
    "fail": 0
  }
}
```

Verdict levels: `PASS`, `WARN` (deferred-metadata mismatch only), `SKIP` (no PDF or no
golden), `FAIL` (required assertion failed, including PDF checksum mismatch).

C4 performs the same PDF checksum guard as C3: if `golden["pdf_sha256"]` is set and does
not match the on-disk PDF, a `sha256: …` error is appended to `errors` and the verdict
is FAIL.  Unlike C3 (which stops at `pytest.fail`), C4 continues running the pipeline so
the report shows both the checksum error and the pipeline assertion results together.

The evaluator imports `_text_in_some` and `assert_valid_bbox_fields` from `_compare.py`,
and the golden loader from `tests/fixtures/_golden.py`.  Since assertion helpers raise
`AssertionError`, C4 wraps each call in a `_try_assert` helper to convert raise → bool:

```python
def _try_assert(fn, *args, **kwargs) -> tuple[bool, str]:
    try:
        fn(*args, **kwargs)
        return True, ""
    except AssertionError as e:
        return False, str(e)
```

C4 does NOT import from `test_real_docs.py` — pytest test modules cannot be safely
imported outside of a pytest session (fixtures do not initialise).

---

## Dependency additions

The project uses `pyproject.toml` (no `requirements.txt`).  The HTTP client in use is
`httpx` (already a dependency).  C1 must use `httpx`, not `requests`.

No new packages are required.

---

## Implementation phases

| Phase | Title | Status | Result |
|-------|-------|--------|--------|
| 0 | Manifest skeleton | **DONE** | 15-entry manifest committed; gitignore already covered real/ dir |
| 1 | Downloader (C1) | **DONE** | 5 invoice PDFs downloaded; sha256 + size_bytes recorded in manifest |
| 2 | Config additions | **DONE** | grp_r marker, conftest, _compare, _golden.py; 76 existing tests green |
| 3 | Generator (C2) + golden files | **DONE** | inv-1–5 golden files committed; 3 bugs found and fixed during generation |
| 4 | Test runner skeleton (C3) | **DONE** | 5 passed / 10 skipped; exit 0 confirmed |
| 5 | Remaining PDFs + golden files | **IN PROGRESS** | URL selection and verification in progress (this session) |
| 6 | Offline evaluator (C4) | **DONE — not live-tested** | Script implemented and syntax-checked; full run deferred until Phase 5 completes |

---

### Phase 0 — Manifest skeleton (no API calls) `[DONE]`
1. Create `tests/fixtures/real_manifest.json` with all 15 entries, `pdf_sha256=null`.
2. Create `tests/fixtures/real_golden/` directory (empty, add `.gitkeep`).
   → verify: JSON parses; directory exists.

**Implementation findings:**
- JSON parsed correctly: 15 entries, all fields present.
- `.gitignore` already had a rule for `tests/fixtures/pdfs/` which covers
  `tests/fixtures/pdfs/real/` — no new gitignore entry was needed.
- sp-1, sp-2, bc-3 set to `"url": null` (NEEDS SELECTION).
- sp-3, sp-4, sp-5, sp-6, bc-1, bc-2, bc-4 were given URLs at manifest creation time
  (not deferred to Phase 5); sp-5 (`memorisation_risk: "high"`) is the BERT paper.

### Phase 1 — Downloader (C1) `[DONE]`
1. Implement `scripts/download_real_fixtures.py`.
2. Run with `--dry-run` to verify URL resolution logic without writing files.
3. Run live for the 5 invoice entries (INV-1 to INV-5); verify checksums land in manifest.
   → verify: PDFs present on disk (gitignored); SHA-256 written to manifest.

**Implementation findings:**
- `httpx` confirmed as the correct HTTP client: `httpx-0.28.1` was already present in
  the venv; `requests` is not installed.  Used `httpx.stream("GET", url,
  follow_redirects=True, timeout=60)` with atomic temp-file write.
- All 5 invoice PDFs downloaded on first attempt with no redirect or 4xx/5xx errors.
  `pdf_sha256` and `size_bytes` written back to manifest atomically.
- Null-URL entries log `NEEDS SELECTION` and are skipped without setting exit 1 — the
  spec's intent was confirmed by this run (12 slots proceeded, 3 skipped).
- The "file exists + null sha → record sha without re-downloading" path was exercised on
  a second run and worked correctly.
- Manifest write-back uses `json.dump → .tmp → Path(tmp).rename(path)` (atomic); no
  partial-write risk even if the process is interrupted mid-manifest.

### Phase 2 — conftest.py + `_compare.py` + `pyproject.toml` additions `[DONE]`
1. Add `"grp_r: Group R — real-document corpus"` to the `markers` list in `pyproject.toml`
   (alongside `grp_a` through `grp_i`).
2. Add `"grp_r"` to `require_real_api_key` in `conftest.py`.
3. Add `_text_in_some` to `_compare.py`.
4. Create `tests/fixtures/_golden.py` (see spec in C3 section above).
   → verify: no existing tests broken (`pytest tests/integration/ -x --ignore=tests/integration/test_real_docs.py`).

**Implementation findings:**
- All 3 config edits were additive single-line changes with no risk of regressions.
- 76 existing integration tests passed after the changes — zero regressions.
- `_text_in_some` uses case-insensitive substring matching after `_normalize` (NFKC +
  whitespace collapse + smart-quote normalisation); the same `_normalize` used by the
  existing `assert_nearest_heading_parent` helper, so behaviour is consistent.
- `_golden.py` is a pure loader with no side effects at import time (DA-7 mitigation:
  files are loaded lazily inside each test call, not at module load).

### Phase 3 — Ground-truth generator (C2) + golden files `[DONE]`
1. Implement `scripts/generate_real_ground_truth.py`.
2. Run for the invoice PDFs first (INV-1–5 are small, download fast, and have no
   CONDITIONAL status).
3. Commit the resulting `tests/fixtures/real_golden/inv-*.json` files.
   → verify: golden files pass JSON schema validation; checksums match manifest.

**Implementation findings:**

*asyncio / event-loop noise:* The initial implementation called `asyncio.run()` once per
pipeline run inside a for-loop.  When each event loop closed, httpx's async cleanup
(`aclose()`) printed `RuntimeError: Event loop is closed` to stderr.  Fix: wrap all N
runs for a slot inside a single `asyncio.run(_run_all_for_slot(pdf_path, n_runs))` call
so the loop closes only once per slot.

*`--runs 3` leaves no headroom:* The first run used 3 runs.  Every invoice produced
identical block counts across all 3 runs (e.g. `[11, 11, 11]`), so
`percentile_80([11,11,11]) = 11 = min_blocks`.  A single-step variation in a real test
run produced 9 blocks → assertion failure "got 9, expected ≥11".  Fix: apply a 15%
safety margin — `min_blocks = max(1, int(percentile_80(raw_block_counts) * 0.85))` —
and re-run with `--runs 5 --force`.  Final floors: inv-1=9, inv-2=10, inv-3=6, inv-4=8,
inv-5=9.

*Multiple table assertions are fragile:* Initial algorithm emitted one assertion per
unique `(rows, cols)` pair that appeared in ≥4/5 runs.  inv-1 produced three assertions
(`{2,5}`, `{4,1}`, `{2,2}`); a test run had no table block with ≥4 rows, failing the
second assertion.  Fix: keep only the assertion with the highest area (max rows × cols)
to focus on the structural table and ignore auxiliary small blocks.

*Row count varies; column count is stable:* Even after keeping only the largest assertion,
the min_rows threshold was still too tight for multi-run variance.  Applied a 40% safety
margin to min_rows only: `min_rows = max(2, int(best_rows * 0.6))`.  Column count
reflects table structure and is left exact.

*inv-3 multi-page split:* inv-3 (`long_invoice.pdf`, 3 pages) had the largest-area
assertion at `{min_rows:12, min_cols:6}`.  Test runs' tables were split by page — no
single block had ≥12 rows.  Fix: manually patched inv-3 golden to `{min_rows:2,
min_cols:6}`.  For multi-page invoices the pipeline splits rows per page; asserting
column count is the only reliable structural check.

*Invoice headings are sparse:* `spot_check_fragments` was empty for inv-1, inv-3, inv-4
(no heading texts stable across ≥4/5 runs).  inv-2 and inv-5 each produced 1 fragment.
This is expected — invoice documents have few headings and their text varies by locale/
template.

### Phase 4 — Test runner skeleton (C3) `[DONE]`
1. Implement `tests/integration/test_real_docs.py` with skip-on-missing logic.
2. Run `pytest tests/integration/test_real_docs.py -m grp_r`.
   Expected outcome depends on what has been done in earlier phases:
   - inv-1–5: golden files exist (Phase 3) and PDFs are on disk (Phase 1) → **PASS**
   - All other slots: no golden file → **SKIP** ("no golden file")
   → verify: zero FAIL; inv-1–5 PASS; remaining 10 SKIP.

**Implementation findings:**
- Final result: `5 passed, 10 skipped in 295.24s (0:04:55)` — exit code 0.  Exactly
  matching the expected outcome.
- inv-1–5 PASS; sp-1–6 and bc-1–4 all SKIP with "no golden file — run
  generate_real_ground_truth.py first".
- The httpx event-loop noise (from Phase 3) appears in pytest's captured log output but
  does not affect test verdicts.
- The `_log_metadata_deferred` helper printed no warnings for the invoice slots
  (expected — invoices have no `metadata_deferred` entries in their golden files).

### Phase 5 — Remaining PDFs + golden files `[IN PROGRESS]`
1. Finalise NEEDS SELECTION candidates (SP-1, SP-2, BC-3) and verify access to
   CONDITIONAL candidates (SP-3, SP-4, SP-6, BC-1, BC-2, BC-4).
2. Run downloader for each confirmed entry.
3. Run ground-truth generator; commit golden files.
4. Run full `grp_r` suite; confirm all 15 tests pass (or SKIP for still-pending slots).
   → verify: ≥10/15 PASS on first run; remaining are SKIP with clear reason.

### Phase 6 — Offline evaluator (C4) `[DONE — not live-tested]`
1. Implement `scripts/evaluate_real_docs.py`.
2. Run against committed golden files; verify report matches pytest results.
   → verify: PASS/WARN/SKIP/FAIL labels agree with pytest output for all present slots.
   Note: C4 now performs the same PDF checksum guard as C3 — a mismatch adds a
   `sha256: …` error to the report and yields FAIL, matching C3's `pytest.fail` behavior.

**Implementation findings:**
- Script implemented and syntax-checked; not live-run against committed golden files
  (out of scope for this implementation phase — Phase 5 must add remaining golden files
  before a full cross-slot comparison is meaningful).
- `_try_assert` wrapper confirmed as the correct pattern: C4 imports
  `assert_valid_bbox_fields` (which raises `AssertionError`) from `_compare.py` rather
  than duplicating the logic.
- C4 does NOT import from `test_real_docs.py` to avoid pytest session coupling — all
  shared logic lives in `_compare.py` and `_golden.py`.
- Output filename uses `datetime.now().strftime("%Y%m%d_%H%M") + "-evaluation.json"`,
  matching the plan file convention.

---

## Devil's advocate review

**DA-1: Golden freshness — who triggers re-generation?**
The checksum guard in C2 and C3 gates re-generation on PDF changes, but if the pipeline
*logic* changes (new block types, renamed fields), the golden files silently pass with
stale data.  
_Mitigation:_ Add a `schema_version` field to golden files, bumped manually when golden
format changes.  The test runner asserts `golden["schema_version"] == CURRENT_SCHEMA_VERSION`.

**DA-2: Checksum coupling creates a catch-22.**
If a PDF is updated upstream and the SHA changes, the test fails immediately with
"checksum mismatch — re-run generator."  But re-running the generator is expensive.
A developer fixing an unrelated bug gets a failing test they can't cheaply fix.  
_Mitigation:_ The checksum mismatch produces a `pytest.fail` with a clear remediation
message.  Document in the runbook that only corpus maintainers should re-run C2.  Treat
checksum mismatches as a corpus maintenance ticket, not a blocking CI failure.

**DA-3: NEEDS SELECTION entries have null URL — C1 must distinguish "no URL" from "fetch failed".**
If null URL is treated the same as a failed download, C1 exits 1 whenever any pending
slot exists, blocking all other downloads.  
_Mitigation:_ C1 step 2 explicitly skips null-URL entries with a warning; only non-null
URL fetch failures trigger exit 1.  This means 12 slots can be downloaded and tested
before the 3 pending slots are resolved.

**DA-4: Accidental re-generation cost.**
Running `generate_real_ground_truth.py` without `--slot` regenerates all 15 × 5 = 75
pipeline runs.  A typo or copy-paste error in CI config could run this and generate a
$15 bill.  
_Mitigation:_ The generator requires `--slot` or explicit `--all` flag; there is no
"run everything" default.  Add a `--dry-run` flag that prints what would run without
making API calls.

**DA-5: `min_blocks` floor can still flake.**
80th-percentile floor over N runs means a single low run drags the threshold down.
For long documents with genuine LLM non-determinism, the raw percentile may be too high.
_Mitigation (three layers):_
1. Run 5 times (not 3) so the 80th-percentile estimate is more stable.
2. Apply a 15% safety margin: `min_blocks = max(1, floor(percentile_80 × 0.85))`, so
   the test tolerates individual runs ~15% below the observed mode.
3. Store `raw_block_counts` in the golden file — if a test fails, the developer can
   inspect whether variance is systematic or a one-off.
For known-flaky slots, add a per-slot `min_blocks_override` in the manifest.

**DA-6: Link rot.**
arXiv, govinfo.gov, and GitHub raw URLs can change.  A 404 silently degrades to a SKIP,
masking a broken corpus.  
_Mitigation:_ C1 exits 1 on any non-recoverable fetch failure (after trying
`fallback_url`).  The CI job that runs `download_real_fixtures.py` should fail visibly,
not silently skip.

**DA-7: Test independence — shared golden loader state.**
If `test_real_docs.py` loads all golden files at module import time and one golden file
is malformed, all 15 tests fail with an import error rather than one test failing.  
_Mitigation:_ Load each golden file lazily inside the test function (or in a
per-test fixture), so a malformed golden only affects that slot.

**DA-8: `metadata_deferred` log-only assertions are invisible in CI.**
A regression in deferred metadata fields goes unnoticed indefinitely.  
_Mitigation:_ C4 (offline evaluator) flags deferred mismatches as WARN in its report.
Document that evaluator output should be reviewed before merging corpus changes.

**DA-9: Three slots (SP-1, SP-2, BC-3) are pending manual selection.**
All three produce SKIP verdicts until a specific document is chosen.  Acceptable as a
known gap at initial implementation.

- SP-1: non-landmark arXiv paper, ≥13 pp, two-column, figures, numbered references.
  Search in niche subfields (materials science, computational biology, civil engineering)
  to minimise memorisation risk.
- SP-2: total PDF ≤4 pp; best candidates are arXiv preprints of Physical Review Letters
  papers (exactly 4 typeset pages) or 2-page workshop extended abstracts.
- BC-3: native PDF of a public-domain text covering the "literary/mixed text" axis;
  Standard Ebooks (standardebooks.org) provides high-quality PDFs of public-domain books.
  No conversion required.

Once any slot is selected, populate the manifest entry and run the ground-truth generator
for that slot only.

---

## Open questions (not blocking Phase 0–4)

1. **SP-1 candidate?** Awaiting manual selection (non-landmark, ≥13 pp, two-column).
2. **SP-2 candidate?** Awaiting manual selection (total PDF ≤4 pp).
3. **BC-3 candidate?** Awaiting manual selection (native public-domain PDF, literary axis).
4. **CONDITIONAL SP-3/SP-4/SP-6 file sizes?** Need live fetches to confirm ≤5 MB.
5. **BC-1 access?** CBO PDF URL needs a live fetch to confirm it doesn't redirect or 403.
