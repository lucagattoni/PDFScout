# Real-Document Test Corpus — Selection Guidelines and Plan

_Created: 2026-06-03 15:40_
_Updated: 2026-06-03 15:50 · DA review v1 — gitignore path bug fixed (pdfs/real/ not real/pdfs/), Phase 2 baseline lifted to 3 runs, skip-on-missing-fixture requirement added, Phase 3 stability threshold corrected to ≥4/5, author-year reference caveat added, concrete candidate examples added, cost estimate clarified_
_Updated: 2026-06-04 06:33 · Phase 1 candidate selection — replaced placeholder slots with specific named candidates, added source URLs, license, file-size data, and verification status for all 15 slots; INV-1–5 all sourced from strzibny/invoice_printer (MIT, all ≤200 KB); SP-2 deferred to manual selection; BC-3 requires PDF conversion; coverage gaps documented_

## Goal

Define principled criteria for selecting a real-document test corpus that complements
the 37 synthetic e2e tests. The synthetic suite controls inputs precisely but cannot
replicate the layout complexity, typography variety, and content density of real-world
PDFs. The corpus should:

- Surface extraction failures that only appear on real documents (complex layouts,
  unusual fonts, scanned pages, multi-column academic formatting).
- Validate the classifier's accuracy on genuine inputs.
- Stress-test the burst dispatcher on longer documents.
- Cover all three doc types (`invoice`, `scientific_paper`, `baseline_core`) with
  realistic variety.
- Remain maintainable: bounded cost per CI run, assertions that survive minor
  LLM-output variation.

**Out of scope for this plan:** Implementation of the test runner, fixture download
helpers, or golden-file infrastructure. This plan covers selection criteria, coverage
matrix, assertion strategy, and sourcing guidelines only.

---

## Gaps the synthetic suite does not cover

| Scenario | Synthetic coverage | Gap |
|---|---|---|
| Invoice with complex multi-table layout | D1 (1 table, controlled) | Real invoices have totals rows, subtotals, taxes, item codes |
| Scientific paper with real bibliographic metadata | D2–D5 (synthetic text) | Actual author name formats, DOI styles, journal abbreviations |
| Two-column academic layout with figures | G2 (three columns, no figures) | Real papers interleave figures mid-column; caption wrapping |
| 10–30 page burst | E2 (5 pages) | Longer burst reveals max_tokens pressure, block dedup edge cases |
| Scanned page in otherwise native PDF | H2 (fully tiny text, no scan) | Mixed-quality docs are common in real use |
| Classifier on ambiguous document | B-group only tests known types | Real docs sometimes straddle types (tech report, white paper) |
| Footnotes and margin elements at scale | C-group (1–2 blocks each) | Real academic papers have dense footnotes across many pages |

---

## Document selection criteria

### Criterion 1 — Type coverage

Select documents in this ratio:

| Doc type | Count | Rationale |
|---|---|---|
| `scientific_paper` | 6 | Richest schema; most metadata subfields to validate |
| `invoice` | 5 | Table extraction is the key risk; need format variety |
| `baseline_core` | 4 | Tests classifier rejection and graceful handling of mixed/ambiguous content |

Total: **15 documents** — enough to be representative, small enough for per-PR runs.

API cost estimate: 15 docs × (1 classifier + avg 5 page workers + 1 hierarchy) ≈ 105
Anthropic calls per full suite run. This is a lower bound — pioneer retries and longer
documents add calls. At `claude-sonnet-4-6` pricing this is roughly $1.50–$3 per full
run; the exact figure depends on document length and cache-hit rate.

### Criterion 2 — Structural diversity within each type

Each group must jointly cover all of the following axes. No single axis needs to appear
in every document — the group as a whole must cover each at least once.

**Scientific papers (6 docs):**

| Axis | Required values | Notes |
|---|---|---|
| Column layout | Single-column, two-column | Two-column is the most common gap |
| Page count | 1–4 pages, 5–12 pages, 13+ pages | Tests pioneer-only, burst-small, burst-large |
| Figure density | None/sparse, figure-heavy | Exercises `figure` block type and `figure_table` metadata |
| Reference style | Numbered `[1]`, author-year `(Smith 2020)` | Tests `reference` metadata extraction. **Caveat:** `citation_key` maps cleanly only for numbered refs; for author-year style, assert `reference.year` (integer) rather than `citation_key`. |
| Source quality | Native PDF, scanned or low-res | At least 1 scanned or mixed-quality doc |

**Invoices (5 docs):**

| Axis | Required values | Notes |
|---|---|---|
| Table structure | Single table, multiple tables | Tests multi-table `table_data` extraction |
| Page count | 1 page, 2–3 pages | Multi-page invoices have running totals and split line items |
| Layout style | Formal (grid), informal (mixed text+table) | Both are common in the wild |
| Language | English, at least 1 non-English | Tests classifier robustness; metadata extraction may degrade gracefully |

**Baseline_core (4 docs):**

| Axis | Required values | Notes |
|---|---|---|
| Content type | Letter/memo, technical report, ambiguous hybrid | Classifier must reject all as invoice/scientific_paper |
| Page count | 1 page, 3+ pages | |
| Layout | Prose-only, prose + list items | Exercises `list_item` and `heading` block types at scale |

### Criterion 3 — Anti-selection rules

**Do NOT select documents that:**
- Are generated by the same synthetic pipeline (circular coverage).
- Contain personally identifiable information (names, account numbers) not already
  in the public domain.
- Require per-use licensing or contain copyright-restricted content that cannot be
  committed to the repository.
- Are identical or near-identical in layout to an existing synthetic fixture.
- Are larger than 5 MB (above the API upload limit; also impractical for CI).
- Have more than 40 pages (burst cost becomes prohibitive in per-PR runs; use
  a separate nightly-only corpus for long documents).

### Criterion 4 — Verifiability requirement

Each document must have at least **three independently verifiable facts** that the
annotator can assert about the expected extraction output:

- **For scientific papers**: title, ≥1 author name, ≥1 section heading text.
- **For invoices**: ≥1 line-item description text, total amount, ≥1 company name.
- **For baseline_core**: ≥2 paragraph text fragments, expected doc_type = `baseline_core`.

These facts become the spot-check assertions in the test. Documents where verifiable
facts are unavailable (e.g., fully scanned with no known ground truth) should be
used for schema-only or completeness-only assertions.

---

## Sourcing guidelines

### Approved sources

| Source | Type | Access |
|---|---|---|
| **arXiv.org** | Scientific papers | Open access; LaTeX-generated PDFs; metadata known |
| **PubMed Central Open Access** | Scientific papers | CC BY; often two-column; rich metadata |
| **US government printing office / Congress.gov** | Reports, letters | Public domain; no copyright |
| **NIST publications (nvlpubs.nist.gov)** | Technical reports | Public domain; table-heavy |
| **Invoices from open-source accounting projects** | Invoices | MIT/CC-licensed sample data |
| **Project Gutenberg** | Prose documents | Public domain; good for `baseline_core` |
| **OSF Preprints (CC BY)** | Scientific papers | Open access |

### Rejection list

- Elsevier, Springer, Wiley full-text PDFs (copyright restricted).
- Company annual reports (copyright, PII risk).
- Legal filings unless from a public-domain court record repository.
- Any document downloaded behind a paywall or login.

### Metadata to record per document

For each selected document, record in a companion manifest (`tests/fixtures/real_manifest.json`
— committed to the repo; PDFs themselves are not committed unless ≤200 KB):

```json
{
  "filename": "arxiv_2301_00001.pdf",
  "source_url": "https://arxiv.org/pdf/2301.00001",
  "license": "CC BY 4.0",
  "expected_doc_type": "scientific_paper",
  "page_count": 8,
  "layout": "two_column",
  "quality": "native",
  "spot_checks": {
    "title_fragment": "Attention Is All You Need",
    "author_fragment": "Vaswani",
    "section_fragment": "Multi-Head Attention"
  },
  "min_blocks": 30,
  "notes": "Standard two-column NeurIPS format; figure-heavy second half"
}
```

---

## Assertion strategy

### What to assert (per document)

1. **Schema validity** (always): output passes the JSON Schema for the declared doc type.
2. **Classification** (always): `document_type` in output matches `expected_doc_type`.
3. **Completeness** (always): `len(structured_payload) >= min_blocks`.
4. **Spot-check text** (when verifiable facts are known): each `spot_checks` value appears
   in at least one block's `text` field (case-insensitive, NFKC-normalised substring match).
   Use the same `_text_in_some` helper already in the test suite.
5. **Metadata subfield** (type-specific, stability-gated):
   - `scientific_paper`: ≥1 block has `metadata.bibliographic` with non-empty `authors`.
   - `invoice`: ≥1 block has `metadata.table_data` with `rows` present.
   - `baseline_core`: no schema-specific metadata keys appear.

### What NOT to assert

- **Exact block count**: varies by model and caching state.
- **Exact block text**: Claude may paraphrase or merge lines; substring match only.
- **Bbox coordinates**: non-deterministic in value; assert only non-negativity (already
  covered by `assert_valid_bbox_fields` in `_compare.py`).
- **Block order beyond column-bucket level**: fine-grained reading order varies.
- **`parent_id` values**: hierarchy assignment can vary; assert only structural validity
  (no self-reference, no unknown IDs — covered by A3 already).

### Stability gate before adding any metadata assertion

Before asserting a metadata subfield for a real document (e.g.,
`metadata.bibliographic` on a specific arXiv paper), run the extraction **5 times**.
If the subfield is present and correct ≥4/5 runs, add the assertion. If not, add a
`# Stability: X/5 — deferred` comment and assert completeness only.

This mirrors the D-group approach used for synthetic tests.

---

## Test group design

- **Marker**: `@pytest.mark.grp_r` — added to `pyproject.toml` markers list.
- **Excluded from default run**: not in `make test`; run via `make test-real` or
  `pytest -m grp_r`.
- **API key guard**: add `grp_r` to the `require_real_api_key` fixture in
  `tests/integration/conftest.py`.
- **Storage**: PDFs go in `tests/fixtures/pdfs/real/`. This path is a subdirectory of
  the already-gitignored `tests/fixtures/pdfs/` directory, so no new gitignore entry
  is needed. **Do NOT use `tests/fixtures/real/pdfs/`** — that is a different path that
  is not covered by the existing rule.
- **Manifest**: `tests/fixtures/real_manifest.json` — committed to the repo (it is
  metadata only; it contains source URLs and assertion facts, no PDF content).
- **Download helper**: a `download_real_fixtures.py` script fetches PDFs from
  `source_url` fields in the manifest and saves them to `tests/fixtures/pdfs/real/`.
  Run manually before a real-doc test session; not executed in CI.
- **Skip-on-missing**: tests MUST call `pytest.skip` (not raise `FileNotFoundError`)
  when the fixture file does not exist. The fixture download is a pre-condition, not a
  test failure. Pattern: `if not Path(pdf_path).exists(): pytest.skip("fixture not downloaded")`.

  **Decision gate**: PDFs ≤200 KB can be committed directly to the repo, removing the
  download requirement for those specific tests.

---

## Candidate examples (Phase 1 starting points)

These are specific candidates identified during Phase 1 research. Status codes:
**PASS** = verified, ready to add to manifest. **CONDITIONAL** = verified exists but one
or more facts (file size, license) need manual confirmation. **NEEDS VERIFICATION** =
candidate identified but page count or license not confirmed. PDFs marked ≤200 KB can
be committed directly to the repo (removing the download requirement for those tests).

| Slot | Candidate | Source URL | License | Status |
|---|---|---|---|---|
| SP-1 | "Attention Is All You Need" (Vaswani et al., 2017) — 15 pp, two-column, figures, numbered refs | `https://arxiv.org/pdf/1706.03762` | CC BY-NC-SA | PASS — memorisation risk HIGH (see note) |
| SP-2 | *(open — needs manual selection)* arXiv preprint with TOTAL PDF ≤4 pages including references. ACL 2022 short papers are 8–9 pp total; SemEval system papers are 6–8 pp — both too long. Best candidates: (a) an arXiv preprint of a Physical Review Letters paper (~4 pp, any physics topic); (b) a 2-page NeurIPS/ICML workshop extended abstract; (c) any arXiv paper where the full PDF is confirmed ≤4 pp. | arXiv | CC BY (verify) | NEEDS MANUAL SELECTION — verify total PDF ≤4 pp before adding |
| SP-3 | eLife "Wnt3 signalling controls lateral inhibition of pigmentation" (or similar eLife brief paper, PMC7725503) — CC BY, author-year refs, ~28 pp | `https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7725503/pdf/` | CC BY 4.0 | CONDITIONAL — verify file size ≤5 MB before committing URL |
| SP-4 | NIST IR 8170 "Approaches for Federal Agencies to Use the Cybersecurity Framework" (2020) — 33 pp, single-column, table-heavy | `https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8170.pdf` | Public domain | CONDITIONAL — verify file size ≤5 MB |
| SP-5 | "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding" (Devlin et al., 2018) — 16 pp, two-column, numbered refs | `https://arxiv.org/pdf/1810.04805` | CC BY | PASS — memorisation risk HIGH (see note) |
| SP-6 | NBS Technical Note 290 (1966, NIST Legacy Collection) — scanned typewritten, ~34 pp | `https://nvlpubs.nist.gov/nistpubs/Legacy/TN/nbstechnicalnote290.pdf` | Public domain | CONDITIONAL — verify file size ≤5 MB; this is the scanned-quality axis doc |
| INV-1 | `simple_invoice.pdf` (strzibny/invoice_printer) — 1 pp, 1 table, English, formal grid, ~20 KB | `https://raw.githubusercontent.com/strzibny/invoice_printer/master/examples/simple_invoice.pdf` | MIT | PASS — commit directly (20 KB) |
| INV-2 | `breakdown.pdf` (strzibny/invoice_printer) — 1 pp, 2 tables (info box + line items + VAT), English, ~24 KB | `https://raw.githubusercontent.com/strzibny/invoice_printer/master/examples/breakdown.pdf` | MIT | PASS — commit directly (24 KB) |
| INV-3 | `long_invoice.pdf` (strzibny/invoice_printer) — 3 pp, running line items across pages, ~72 KB | `https://raw.githubusercontent.com/strzibny/invoice_printer/master/examples/long_invoice.pdf` | MIT | PASS — commit directly (72 KB) |
| INV-4 | `complex_invoice.pdf` (strzibny/invoice_printer) — 1 pp, multi-section with embedded logo, ~175 KB | `https://raw.githubusercontent.com/strzibny/invoice_printer/master/examples/complex_invoice.pdf` | MIT | CONDITIONAL — commit directly (175 KB); layout is formal-complex, not truly informal mixed-text; informal-axis gap acknowledged (see note) |
| INV-5 | `czech_invoice.pdf` (strzibny/invoice_printer) — 1 pp, Czech language, 2 tables, ~48 KB | `https://raw.githubusercontent.com/strzibny/invoice_printer/master/examples/czech_invoice.pdf` | MIT | PASS — commit directly (48 KB) |
| BC-1 | CBO "Monthly Budget Review: Summary for Fiscal Year 2022" — multi-page policy summary with prose + tables | `https://www.cbo.gov/system/files/2022-11/58592-MBR.pdf` | Public domain | NEEDS VERIFICATION — confirm URL, expected page count 5–10 pp; alternative: any CRS "In Brief" report at crsreports.congress.gov |
| BC-2 | GAO Science & Tech Spotlight "Wastewater Surveillance" (GAO-22-105841, April 2022) — 2 pp, headings + bullet points + brief prose | `https://www.gao.gov/assets/gao-22-105841.pdf` | Public domain | CONDITIONAL — URL confirmed via web search; verify direct PDF access and exact page count (expected 2 pp) |
| BC-3 | "The Art of War" by Sun Tzu, Lionel Giles translation (Project Gutenberg #17405) — ~15 pp when converted, numbered chapter headings + prose paragraphs | `https://www.gutenberg.org/files/17405/17405.txt` (text file; PDF must be generated by fixture script) | Public domain | NEEDS PDF CONVERSION — add generation step to `download_real_fixtures.py`; no pre-existing PDF to commit |
| BC-4 | GAO Science & Tech Spotlight "Brain-Computer Interfaces" (GAO-22-106118, Sept 2022) — 2 pp, headings + bullet points + sidebar elements | `https://www.gao.gov/assets/gao-22-106118.pdf` | Public domain | CONDITIONAL — URL confirmed via web search; verify direct PDF access (if blocked, use govinfo.gov mirror) |

**Coverage notes:**

- **SP-1 and SP-5 memorisation risk**: Both are famous ML papers. Spot-check assertions
  (title, author name, section heading) may pass even on hallucinated output because
  the model has memorised the content. This risk is acceptable — the extraction test
  still validates the pipeline end-to-end. If memorisation is a concern, substitute
  with a less famous paper of similar layout (same venue, same format, different topic).

- **SP-2 manual selection needed**: ACL/EMNLP/NAACL short papers (4-page content limit)
  are 8–9 pages total including references. No standard NLP venue produces PDFs ≤4 pages
  total. Best alternatives: an arXiv preprint of a Physical Review Letters paper (PRL
  papers are exactly 4 typeset pages and appear on arXiv), or a 2-page workshop extended
  abstract. Confirm total PDF page count before adding to manifest.

- **INV-4 informal-layout axis gap**: All five invoice candidates come from
  `strzibny/invoice_printer`, a library that generates professional-grade formatted
  invoices. None is truly "informal" in the sense of free-form mixed text + table.
  `complex_invoice.pdf` is the most varied layout. If coverage of the informal axis is
  important, replace INV-4 with a hand-typed or minimally-formatted invoice from a
  different source (e.g., a public domain handwritten invoice scan, or a government
  procurement order with informal layout).

- **BC-3 PDF conversion**: The fixture download script must generate the PDF from the
  Project Gutenberg plain-text file. A minimal implementation using `fpdf2` (already a
  dev dependency) creates a single-column PDF with Roman headings for chapter titles and
  body text for paragraphs. Target: ~15 pages. The resulting PDF path is
  `tests/fixtures/pdfs/real/gutenberg_art_of_war.pdf`.

- **BC-2 and BC-4 GAO access**: The GAO website (gao.gov) returns HTTP 403 to automated
  clients. The PDF files are also mirrored on govinfo.gov under the path pattern
  `https://govinfo.gov/content/pkg/GOVPUB-GA-PURL-gpoXXXXXX/pdf/GOVPUB-GA-PURL-gpoXXXXXX.pdf`.
  If direct gao.gov access fails, use govinfo.gov mirror. The govinfo.gov URL for
  GAO-22-105841 is `https://govinfo.gov/content/pkg/GOVPUB-GA-PURL-gpo177086/pdf/GOVPUB-GA-PURL-gpo177086.pdf`
  (confirmed via web search).

---

## Implementation phases

### Phase 1 — Document selection (manual, no code)

For each of the 15 slots in the coverage matrix, find a candidate document from an
approved source, verify it meets all four selection criteria, record its manifest entry.
Estimated effort: 2–3 hours of manual curation.

**Exit condition**: 15 manifest entries complete; each has ≥3 verifiable spot-check facts.

### Phase 2 — Baseline sampling (3 runs per document)

Run each document through the pipeline **three times** (real API). Record for each run:
- Was the correct doc type returned?
- Were spot-check texts found in extracted blocks?
- Which metadata subfields were populated?
- Any extraction warnings?

Three runs surface variability before the stability gate. Documents where classification
is wrong on ≥2/3 runs, or where spot-check texts are absent on ≥2/3 runs, should be
replaced or their expected assertions adjusted.

### Phase 3 — Stability gate for metadata assertions

For the 6 scientific papers and 5 invoices, run each **5 times**. Lock in a metadata
assertion when it passes **≥4/5** runs; add a `# Stability: X/5 — deferred` comment
when it passes <4/5. Stability threshold is ≥4/5, not 5/5, to account for
real-document variability being slightly higher than synthetic.

### Phase 4 — Test implementation

Write `tests/integration/test_real_docs.py` with one test per document using the
helper pattern established in the D-group and E-group tests. Each test is parameterised
over the manifest — single assertion function, manifest-driven inputs.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Source URL goes dead | Medium | Commit the PDF directly if ≤200 KB; otherwise store a local copy outside repo on a persistent host |
| Classification wrong on real doc | Medium | Check in Phase 2; replace document or adjust `expected_doc_type` if it's genuinely ambiguous |
| Metadata subfields not populated on real layout | Medium | Stability gate; defer assertion to completeness-only if <4/5 |
| PDF too large for API (>5 MB) | Low | Enforce the 5 MB anti-selection rule; check file size before adding to manifest |
| PII in selected document | Low | Use only documents from approved public-domain/open-access sources; no user-submitted content |
| Cost spike in CI | Low | Mark `grp_r` excluded from default run; estimate cost per run in manifest README |
| Real PDFs accidentally committed to git | High if path wrong | Store at `tests/fixtures/pdfs/real/` (subdirectory of gitignored dir); never at `tests/fixtures/real/pdfs/` which is NOT covered |
| Test fails with FileNotFoundError instead of skip | High if not guarded | Each test must check `Path(pdf_path).exists()` and call `pytest.skip` if missing |
