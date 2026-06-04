# Real-Document Corpus — Workflow Runbook

Describes the day-to-day operations for the real-document test corpus.
Components are numbered C0–C4 as in `plans/20260604_0739-real-doc-infrastructure.md`.

---

## Roles

**Corpus maintainer** — the person responsible for adding slots, keeping URLs fresh,
and re-generating golden files when the pipeline changes.  Run C2 only as a corpus
maintainer; it makes real API calls (~$7–$15 per full regeneration).

**Developer** — runs C1 (downloader) before tests, runs C3 (pytest) to check
regressions.  Never runs C2 unless specifically maintaining the corpus.

---

## Adding a new slot

1. Pick a document that satisfies the selection criteria in
   `plans/20260603_1540-real-doc-test-corpus.md`.
2. Assign the next available `slot_id` in the appropriate category
   (e.g. `sp-7`, `inv-6`, `bc-5`).
3. Add the entry to `tests/fixtures/real_manifest.json` with all fields filled
   (`url`, `license`, `memorisation_risk`).  Leave `pdf_sha256` and `size_bytes`
   null — C1 will fill them.
4. Run C1 to download the PDF and record the checksum:
   ```
   python scripts/download_real_fixtures.py --slot <slot_id>
   ```
5. Run C2 to generate the golden file:
   ```
   python scripts/generate_real_ground_truth.py --slot <slot_id> --runs 5
   ```
6. Inspect the generated `tests/fixtures/real_golden/<slot_id>.json`.  Verify
   `min_blocks`, `spot_check_fragments`, and `table_assertions` look reasonable.
   If the golden is too tight or too loose, adjust `min_blocks_override` in the
   manifest entry and re-run C2 with `--force`.
7. Add the new `slot_id` to the `@pytest.mark.parametrize` list in
   `tests/integration/test_real_docs.py`.
8. Run C3 to confirm the new slot passes:
   ```
   pytest tests/integration/test_real_docs.py -m grp_r -k <slot_id>
   ```
9. Commit `real_manifest.json` and `real_golden/<slot_id>.json`.
   Do **not** commit the PDF binary (`tests/fixtures/pdfs/real/` is gitignored).

---

## Updating a slot (pipeline logic changed)

When pipeline logic changes (new block types, renamed fields, schema bump):

1. If the golden format itself changed, bump `CURRENT_SCHEMA_VERSION` in
   `tests/fixtures/_golden.py` (single source of truth — C2 and C3 import it).
2. Re-run C2 for affected slots:
   ```
   python scripts/generate_real_ground_truth.py --slot <slot_id> --runs 5 --force
   ```
3. Review the diff to the golden file before committing.  The diff is the paper
   trail that a pipeline change actually propagated correctly.

---

## Updating a slot (upstream PDF changed)

If a URL returns a different PDF (checksum mismatch in C1 or C3):

1. Re-run C1 with `--force` to download the new PDF and update the manifest sha:
   ```
   python scripts/download_real_fixtures.py --slot <slot_id> --force
   ```
2. Re-run C2 to regenerate the golden against the new PDF:
   ```
   python scripts/generate_real_ground_truth.py --slot <slot_id> --runs 5 --force
   ```
3. If the upstream PDF changed significantly, reconsider whether the slot still
   satisfies its selection criteria.  Replace if necessary.

---

## Running the offline evaluator (C4)

C4 produces a JSON regression report without pytest overhead.  Use it for
iterative development before committing golden files.

```
python scripts/evaluate_real_docs.py [--slot sp-1,inv-2] [--output-dir reports/]
```

C4 checks PDF checksums and reports FAIL for mismatches.  Its PASS/WARN/SKIP/FAIL
verdicts should agree with C3 for all present slots.  If they diverge (e.g. C3
fails on checksum but C4 also flags sha mismatch), re-run C1 and C2 before
investigating further.

---

## Checking corpus health

```
python scripts/evaluate_real_docs.py --output-dir reports/
```

Review the summary line.  Any FAIL warrants investigation before merging.
WARN means a deferred-metadata field regressed — track but do not block.
SKIP means the PDF or golden file is missing for that slot.
