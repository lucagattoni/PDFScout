# Real-Document Infrastructure — Downloader, Ground Truth, and Test Runner

_Created: 2026-06-04 07:39_
_Updated: 2026-06-04 · all PDFs download-only (no commit); SP-1 and BC-3 moved to NEEDS SELECTION; evaluator output changed to JSON with datetime-prefix filename_
_Updated: 2026-06-04 · fix stale "conversion flags" / "convert" text; fix result key doc_type→document_type; add null-URL skip to C1; add schema_version+raw_block_counts to golden schema; add _assert_metadata_required/_assert_table_dimensions specs; introduce shared _golden.py; fix Phase 3 wording; replace redundant DA-3_
_Updated: 2026-06-04 · fix requests→httpx; add pyproject.toml grp_r marker requirement; specify _golden.py API; specify _run_pipeline; add min_blocks_override to manifest schema_

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
5. An **offline evaluator** that produces a human-readable regression report without
   spinning up pytest.

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
   - If `pdf_sha256` in manifest is non-null and matches → skip (already fresh).
   - If it does not match → warn and re-download (upstream PDF changed).
5. Download from `url`; if HTTP 4xx/5xx, retry `fallback_url` if set.
6. Write back `pdf_sha256` and `size_bytes` into the manifest entry if they were null.
7. Exit 1 if any entry with a non-null URL could not be fetched.

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
    if url is null: log "slot <id>: no URL set — skipping" and continue
    ensure pdf exists (call C1 if needed); if still missing, log and continue
    run pipeline N times (default N=5) collecting all block lists
    derive golden assertions (see below)
    write tests/fixtures/real_golden/<slot_id>.json
```

### Deriving stable assertions

**Block count:** `min_blocks = floor(percentile_80(block_counts_across_runs))`
This sets a floor: at least this many blocks must appear.  Using 80th percentile rather
than the minimum avoids a single bad run dragging the threshold down.

**Classification:** unanimous across all N runs, else mark as `classification_unstable`
(informational flag, no assertion generated).

**Metadata fields (scientific_paper only):** for each subfield
(`title`, `authors`, `year`, `doi`, `abstract`, `journal_or_venue`):
- If the field value is identical across ≥4/5 runs: emit as `metadata_required`.
- If 3/5: emit as `metadata_deferred` (soft assertion, not enforced in CI).
- If <3/5: omit entirely.

**Spot-check text:** For each run, collect `text` values of all blocks of type
`heading` and `paragraph`.  A text fragment F is included in `spot_check_fragments` if
F (after `_normalize`) appears in ≥4/5 runs somewhere in the block list.

**Table dimensions (invoice only):** `table_data.total_rows` / `total_cols` are included
if identical across ≥4/5 runs.

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
  "min_blocks": 43,                // floor(percentile_80(raw_block_counts))
  "classification": "scientific_paper",
  "classification_unstable": false,
  "metadata_required": {           // assert ≥1 block contains each field
    "title": "<paper title>",
    "year": 2024
  },
  "metadata_deferred": {           // log-only; never fails the test
    "journal_or_venue": "<venue>"
  },
  "spot_check_fragments": [        // each must appear in ≥1 block's text
    "<section heading fragment>",
    "<body text fragment>"
  ],
  "table_assertions": [],          // [{min_rows, min_cols}] for invoice docs
  "stability_notes": ""
}
```

### CLI

```
python scripts/generate_real_ground_truth.py [--slot sp-1] [--runs 5] [--force]
```

`--force` regenerates even when a golden file already exists and the checksum matches.
Without `--force`, exits early if `pdf_sha256` in the golden file matches the current
file on disk (PDF unchanged → skip expensive re-run).

---

## C3 — Test runner (`test_real_docs.py`)

### Structure

```python
@pytest.mark.e2e
@pytest.mark.grp_r
class TestRealDocs:
    @pytest.fixture(autouse=True)
    def _load_manifest(self): ...

    @pytest.mark.parametrize("slot_id", [...])
    async def test_real_doc(self, slot_id):
        golden = _load_golden(slot_id)
        pdf_path = _REAL_PDFS / f"{slot_id}.pdf"
        if not pdf_path.exists():
            pytest.skip(f"PDF not present: run download_real_fixtures.py first")

        # checksum guard
        actual_sha = sha256(pdf_path)
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

`_assert_metadata_required(blocks, golden)` — for each `(key, expected)` pair in
`golden["metadata_required"]`, searches all blocks for a block whose
`metadata.bibliographic` (scientific_paper) or `metadata.table_data` (invoice) contains
a field matching `key` with value equal to `expected`.  Fails if none found.

`_assert_table_dimensions(blocks, ta)` — finds at least one block where
`metadata.table_data.total_rows >= ta["min_rows"]` and
`metadata.table_data.total_cols >= ta["min_cols"]`.  Fails if no such block exists.

Both helpers are private to `test_real_docs.py`.  They are NOT added to `_compare.py`
(too real-doc-specific to be general).

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
      "metadata_deferred_mismatches": ["journal_or_venue"],
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
golden), `FAIL` (required assertion failed).

The evaluator imports assertion helpers from `_compare.py` and the golden loader from
`tests/fixtures/_golden.py`.  It does NOT import from `test_real_docs.py` — pytest test
modules cannot be safely imported outside of a pytest session (fixtures do not
initialise).  The shared `_golden.py` module is also imported by C3, ensuring both
consumers use identical loading logic.

---

## Dependency additions

The project uses `pyproject.toml` (no `requirements.txt`).  The HTTP client in use is
`httpx` (already a dependency).  C1 must use `httpx`, not `requests`.

No new packages are required.

---

## Implementation phases

### Phase 0 — Manifest skeleton (no API calls)
1. Create `tests/fixtures/real_manifest.json` with all 15 entries, `pdf_sha256=null`.
2. Create `tests/fixtures/real_golden/` directory (empty, add `.gitkeep`).
   → verify: JSON parses; directory exists.

### Phase 1 — Downloader (C1)
1. Implement `scripts/download_real_fixtures.py`.
2. Run with `--dry-run` to verify URL resolution logic without writing files.
3. Run live for the 5 invoice entries (INV-1 to INV-5); verify checksums land in manifest.
   → verify: PDFs present on disk (gitignored); SHA-256 written to manifest.

### Phase 2 — conftest.py + `_compare.py` + `pyproject.toml` additions
1. Add `"grp_r: Group R — real-document corpus"` to the `markers` list in `pyproject.toml`
   (alongside `grp_a` through `grp_i`).
2. Add `"grp_r"` to `require_real_api_key` in `conftest.py`.
3. Add `_text_in_some` to `_compare.py`.
4. Create `tests/fixtures/_golden.py` (see spec below).
   → verify: no existing tests broken (`pytest tests/integration/ -x --ignore=tests/integration/test_real_docs.py`).

### Phase 3 — Ground-truth generator (C2) + golden files
1. Implement `scripts/generate_real_ground_truth.py`.
2. Run for the invoice PDFs first (INV-1–5 are small, download fast, and have no
   CONDITIONAL status).
3. Commit the resulting `tests/fixtures/real_golden/inv-*.json` files.
   → verify: golden files pass JSON schema validation; checksums match manifest.

### Phase 4 — Test runner skeleton (C3)
1. Implement `tests/integration/test_real_docs.py` with skip-on-missing logic.
2. Run `pytest tests/integration/test_real_docs.py -m grp_r` with no PDFs present;
   all 15 tests should skip gracefully.
   → verify: zero failures, all SKIPs.

### Phase 5 — Remaining PDFs + golden files
1. Finalise NEEDS SELECTION candidates (SP-1, SP-2, BC-3) and verify access to
   CONDITIONAL candidates (SP-3, SP-4, SP-6, BC-1, BC-2, BC-4).
2. Run downloader for each confirmed entry.
3. Run ground-truth generator; commit golden files.
4. Run full `grp_r` suite; confirm all 15 tests pass (or SKIP for still-pending slots).
   → verify: ≥10/15 PASS on first run; remaining are SKIP with clear reason.

### Phase 6 — Offline evaluator (C4)
1. Implement `scripts/evaluate_real_docs.py`.
2. Run against committed golden files; verify report matches pytest results.
   → verify: PASS/WARN/SKIP labels agree with pytest output for all present slots.

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
80th-percentile floor over 5 runs means a single run with 20% fewer blocks sets the
floor.  For long documents with genuine LLM non-determinism, this floor may be too high.  
_Mitigation:_ The generator stores all 5 block counts in the golden file under
`raw_block_counts`.  If a test fails the `min_blocks` assertion, the developer can
inspect whether the variance is systematic or a one-off.  For known-flaky slots, allow
a per-slot `min_blocks_override` in the manifest.

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
