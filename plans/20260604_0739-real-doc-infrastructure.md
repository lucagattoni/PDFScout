# Real-Document Infrastructure — Downloader, Ground Truth, and Test Runner

_Created: 2026-06-04 07:39_
_Updated: 2026-06-04 · all PDFs download-only (no commit); SP-1 and BC-3 moved to NEEDS SELECTION; evaluator output changed to JSON with datetime-prefix filename_

## Goal

Complement `20260603_1540-real-doc-test-corpus.md` with a concrete implementation plan
covering:

1. A **fixture downloader** that fetches the 15 real PDFs at test time — no PDF binary
   ever committed to the repository.
2. A **manifest** that records source URLs, checksums, and conversion flags for every
   document.
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
  download_real_fixtures.py      # C1 — fetch / convert / checksum
  generate_real_ground_truth.py  # C2 — multi-run consensus → golden JSON
  evaluate_real_docs.py          # C4 — offline diff report

tests/
  fixtures/
    real_manifest.json           # authoritative source-of-truth for all 15 slots
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
2. For each entry, resolve the target path `tests/fixtures/pdfs/real/<slot_id>.pdf`.
3. If the file exists on disk (gitignored), compute its SHA-256:
   - If `pdf_sha256` in manifest is non-null and matches → skip (already fresh).
   - If it does not match → warn and re-download (upstream PDF changed).
4. Download from `url`; if HTTP 4xx/5xx, retry `fallback_url` if set.
5. Write back `pdf_sha256` and `size_bytes` into the manifest entry if they were null.
6. Exit 1 if any required entry could not be fetched.

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
    ensure pdf exists (call C1 if needed)
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
  "slot_id": "sp-1",
  "doc_type": "scientific_paper",
  "generated_at": "2026-06-04T12:00:00Z",
  "pdf_sha256": "abc123...",       // must match manifest at assert time
  "n_runs": 5,
  "min_blocks": 42,
  "classification": "scientific_paper",
  "classification_unstable": false,
  "metadata_required": {           // assert exact match in test
    "title": "Attention Is All You Need",
    "year": 2017
  },
  "metadata_deferred": {           // log-only in test; do not fail
    "journal_or_venue": "NeurIPS"
  },
  "spot_check_fragments": [        // each must appear in ≥1 block text
    "multi-head attention",
    "encoder-decoder"
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
        assert result["doc_type"] == golden["doc_type"]

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

The evaluator re-uses the exact same assertion helpers as `test_real_docs.py` by
importing from `_compare.py` and the golden loader from `test_real_docs.py`.

---

## Dependency additions

| Package | Reason | Where used |
|---------|--------|------------|
| `requests` (already present?) | HTTP download | C1 |

Verify `requests` is already a dependency before adding it.

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

### Phase 2 — conftest.py + `_compare.py` additions
1. Add `"grp_r"` to `require_real_api_key` in `conftest.py`.
2. Add `_text_in_some` to `_compare.py`.
   → verify: no existing tests broken (`pytest tests/integration/ -x --ignore=tests/integration/test_real_docs.py`).

### Phase 3 — Ground-truth generator (C2) + golden files
1. Implement `scripts/generate_real_ground_truth.py`.
2. Run for the committed invoice PDFs first (fastest; no download step).
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

**DA-3: BC-3 and SP-1 are still NEEDS SELECTION.**
Both slots will skip in the grp_r suite until a specific document is chosen.
_Mitigation:_ The skip count appears in the evaluator summary JSON and serves as a
visible reminder.  Neither slot blocks Phase 0–4.  Criteria are documented in the
manifest initial-entries table.

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

## Open questions (not blocking Phase 0–2)

1. **`requests` already a dependency?** Check `requirements.txt` before adding it.
2. **SP-1 candidate?** Awaiting manual selection (non-landmark, ≥13 pp, two-column).
3. **SP-2 candidate?** Awaiting manual selection (total PDF ≤4 pp).
4. **BC-3 candidate?** Awaiting manual selection (native public-domain PDF, literary axis).
5. **CONDITIONAL SP-3/SP-4/SP-6 file sizes?** Need live fetches to confirm ≤5 MB.
