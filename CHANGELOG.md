# Changelog

## [1.5.0] — 2026-06-15

### Added

- **A2 — Burst page validation retry** (`src/nodes/worker_node.py`, `src/graph.py`) — burst
  pages (pages 2–N, dispatched via `Send`) now have inline validation parity with the pioneer
  page. A new `burst_worker_node` replaces `window_parser_node` for the `parser_worker` graph
  node. On schema validation failure it retries up to 3 times, injecting the error detail into
  the next prompt (identical to `retry_incrementor_node`'s behaviour for the pioneer). After 3
  failed attempts it degrades gracefully: returns whatever blocks were last produced and logs an
  `extraction_warnings` entry. Blocks missing required fields at hierarchy are still filtered as a
  second safety net. No graph topology changes — only the node function wired to `parser_worker`
  changed.
- **`TestBurstWorkerNode` unit tests** (`tests/unit/nodes/test_worker_node.py`) — five tests
  covering: first-attempt pass, retry until valid, max-retry degradation with warning, error
  injection into retry content, empty-block retry.

### Changed

- **C1 test updated** (`tests/integration/test_graph_pipeline.py`) — `test_c1_burst_malformed_block_filtered`
  renamed to `test_c1_burst_malformed_block_retried_then_filtered`; mock side_effect extended
  to provide 3 malformed burst responses (one per retry attempt) instead of 1.

## [1.4.1] — 2026-06-04

### Fixed

- **Worker node blocks type guard** (`src/nodes/worker_node.py`) — Claude occasionally
  serialises the `blocks` array as a JSON string inside the tool call response instead of
  a JSON array. The worker node now attempts `json.loads()` on a string return and falls
  back to `[]` on failure, preventing a `TypeError: can only concatenate list (not "str")
  to list` crash in the `merge_flat_blocks` reducer.
- **`merge_flat_blocks` type guard** (`src/state.py`) — added a non-list guard so any
  unexpected type for `new` returns the existing accumulator unchanged rather than
  propagating a crash through LangGraph's `apply_writes`.
- **Corpus manifest URL fixes** — three blocked slots replaced with verified-accessible
  alternatives: sp-3 (PMC bot-blocked → Frontiers fbioe.2020.00001), bc-1 (CBO 403 →
  NIST SP 1301), bc-2 (gao.gov 403 → govinfo primary), bc-4 (GAO-22-106118 no mirror →
  CISA phishing-resistant MFA fact sheet).

## [1.4.0] — 2026-06-04

### Added

- **Real-document corpus infrastructure (C0–C4)** — a full pipeline for managing, downloading,
  generating ground-truth for, and testing against a 15-slot corpus of real-world PDFs
  (scientific papers, invoices, baseline documents).

- **C0 — Manifest** (`tests/fixtures/real_manifest.json`) — 15-entry JSON array recording
  source URL, SHA-256 checksum, license, and memorisation risk for each slot.  All 15 URLs
  now populated (sp-1–6, inv-1–5, bc-1–4).

- **C1 — Downloader** (`scripts/download_real_fixtures.py`) — fetches real PDFs, records
  checksums in the manifest, handles null-URL slots gracefully, and retries `fallback_url`
  on 4xx/5xx.  PDFs land in `tests/fixtures/pdfs/real/` (gitignored; never committed).

- **C2 — Ground-truth generator** (`scripts/generate_real_ground_truth.py`) — runs the
  full pipeline N times (default 5) per slot and derives stable assertions by consensus:
  `min_blocks` (80th-percentile floor × 0.85), `spot_check_fragments` (headings stable
  across ≥80% of runs), `metadata_required`/`metadata_deferred` (scientific papers),
  `table_assertions` (invoices, largest table by area with 40% row safety margin).
  Golden files for inv-1–5 committed to `tests/fixtures/real_golden/`.

- **C3 — Test runner** (`tests/integration/test_real_docs.py`, marker `grp_r`) — 15
  parametrized tests (one per slot) comparing live pipeline output against committed
  golden files.  Slots without a golden file or PDF skip gracefully.  Tiered assertions:
  schema validity, classification, block count, spot-check text, metadata, table dimensions.
  Current result: 5 pass (inv-1–5), 10 skip (remaining slots pending Phase 5 local run).

- **C4 — Offline evaluator** (`scripts/evaluate_real_docs.py`) — produces a
  `YYYYMMDD_HHMM-evaluation.json` report without pytest overhead.  Verdicts: PASS, WARN
  (deferred-metadata mismatch), SKIP (no PDF or no golden), FAIL (required assertion
  failed, including PDF checksum mismatch).

- **Shared golden loader** (`tests/fixtures/_golden.py`) — exports `load_golden(slot_id)`
  and `CURRENT_SCHEMA_VERSION` (single source of truth; imported by C2 and C3).

- **Corpus runbook** (`docs/real_doc_workflow.md`) — step-by-step instructions for adding
  slots, updating golden files, and handling upstream PDF changes.

- **`grp_r` pytest marker** — registered in `pyproject.toml`; `conftest.py` gates these
  tests on `ANTHROPIC_API_KEY` (same pattern as Groups B–I).

## [1.3.0] — 2026-06-03

### Fixed

- **A1 — Job store persistence** (`src/api/jobs.py`, `api.py`, `src/api/runner.py`) — job
  records are now persisted to `api_jobs.db` (SQLite) using `aiosqlite`. On startup all
  previous records are loaded back into memory; jobs still in `running` or `queued` state
  are automatically marked `failed` (server restart interrupted them). `save()` is called
  at each status transition (`running`, `completed`, `failed`); `remove()` is called on
  job deletion. In-memory dict is preserved unchanged, so all existing tests pass without
  modification. `api_jobs.db` added to `.gitignore`.
- **A2 (partial) — Burst block validation** (`src/nodes/hierarchy_node.py`) — blocks
  missing any required field (`block_id`, `type`, `bbox`, `text`) are now dropped before
  the hierarchy step and logged as `extraction_warnings`. Prevents a `KeyError` crash when
  the burst path returns a structurally invalid block. Full burst retry parity deferred.

### Added

- **C1 — Burst adversarial test** (`tests/integration/test_graph_pipeline.py`) — new
  `TestBurstAdversarial.test_c1_burst_malformed_block_filtered`: all API calls mocked,
  burst page 2 returns a block missing `block_id`. Asserts pipeline completes, page-1
  block is present, malformed block is absent, and a warning is logged. No API key needed.

## [1.2.0] — 2026-06-03

### Fixed

- **A4 — API version string** (`api.py`) — `FastAPI(version=...)` was hardcoded to
  `"0.3.0"` since the API was introduced. Now reads from `importlib.metadata` with a
  `tomllib` fallback for non-installed (source-run) environments. `/health` and `/docs`
  now report the current package version.
- **A6 — Hierarchy `max_tokens` scaling** (`src/nodes/hierarchy_node.py`) — was
  hardcoded to `4000`, which silently truncates responses for documents with many
  blocks. Now scales as `min(16000, max(4000, len(blocks) * 40))`, preventing silent
  orphan-promotion on long documents.
- **A3 — Hierarchy output validation** (`src/nodes/hierarchy_node.py`) — `relation_map`
  edges that reference a non-existent `block_id` or that are self-referential are now
  detected, logged as extraction warnings, and dropped (edge set to `null`) rather than
  propagating corrupt parent references into the output tree.

### Changed

- **A7 — Remove unused calibration fixture** — deleted
  `tests/fixtures/generators/grp_calibration_multipoint.py`. The bbox calibration plan
  was closed; this file was not registered in `generate_all.py` or any test.

## [1.1.1] — 2026-06-03

### Changed

- **D-metadata Phase 2** — D2–D5 test assertions tightened from "if populated"
  fallbacks to direct structural checks. A 3-run baseline sample confirmed all
  four `scientific_paper` metadata subfields (`bibliographic`, `section`,
  `reference`, `figure_table`) populate correctly with the existing prompt; a
  5/5 stability gate preceded each assertion change. No pipeline or schema code
  was modified.

## [1.1.0] — 2026-06-03

### Added

- **9 new synthetic e2e tests** across five groups — full suite is now 37 tests:
  - **C10** `grp_c_unicode` — Latin-1 extended characters (accented vowels, umlaut,
    cedilla); asserts either unicode-preserved or ASCII-normalised form extracted.
  - **C12** `grp_c_emphasis` — page with normal, bold, italic, and bold-italic text;
    asserts all four emphasis variants are present in extracted blocks.
  - **D7** `grp_d_no_metadata` — baseline_core document; asserts no schema-specific
    metadata keys (`bibliographic`, `section`, `reference`, `figure_table`,
    `table_data`) are hallucinated for a doc type that carries none.
  - **E1 page-bleeding assertion** — added to existing E1 two-page test; asserts
    page-1 blocks contain no text exclusive to page 2 and vice versa.
  - **F6** `grp_f_hierarchy` — orphan paragraph before any heading must land at root
    (`parent_id=None`); subsequent paragraph under heading must get `parent_id=h1`.
  - **G2** `grp_g_three_column` — three-column A4 layout; asserts all col-1 blocks
    precede col-2, col-2 precede col-3 in `structured_payload`. Column positions
    chosen at ~74/225/376 Claude-unit bucket centres (≥24-unit boundary margin).
  - **H2** `grp_h_tiny` — single page with 4 pt (sub-legibility) text; asserts
    pipeline completes without exception regardless of whether Claude extracts it.
  - **`assert_valid_bbox_fields` helper** added to `tests/integration/_compare.py`;
    verifies `[ymin, xmin, ymax, xmax]` order and non-negative coordinates.
  - **C1 coordinate check** — `assert_valid_bbox_fields` applied to the C1 paragraph
    test as a standing bbox-order regression guard.

## [1.0.0] — 2026-06-03

### Added

- **`is_continued` field fully enabled** — all three schemas (`baseline_core`,
  `invoice`, `scientific_paper`) now carry a `description` on the `is_continued`
  field; the extraction prompt instructs Claude to set it `true` when a block's
  text is cut off at the bottom of a page and continues at the top of the next.
  The negative constraint ("omit or set false for all complete blocks") prevents
  spurious flags on pages with whitespace near the bottom.
- **E3 synthetic test** — extraction-only assertion: `grp_e_continuation.pdf`
  (two-page fixture, one cross-page paragraph split) must produce exactly one
  page-1 block with `is_continued=true`. Hierarchy is mocked per E-group
  convention.
- **F5 synthetic test** — hierarchy Rule 2 narrow assertion: pre-built blocks
  with `is_continued=true` on a page-1 fragment must cause the hierarchy agent
  to assign the page-2 continuation block as its child (`parent_id = p1c`).
- **Group I synthetic tests** — full-chain integration group (no LLM tier
  mocked except classifier). I1 verifies that extraction and hierarchy work
  together in a single pipeline run for the continuation case: page-1 fragment
  gets `is_continued=true` **and** page-2 block gets `parent_id` pointing at
  the fragment.

### Changed

- `pyproject.toml` — added `grp_i` pytest marker; updated test-count comment.
- `tests/integration/conftest.py` — `grp_i` added to the API-key guard so
  Group I tests are skipped when no real key is present.

### Fixed

- Applied `ruff format` to 15 previously-unformatted Python files (fixture
  generators, integration test helpers). Lint and format are now fully clean
  across all 71 tracked Python files.

## [0.3.0] — 2026-05-30

### Added

- **FastAPI HTTP interface** (`api.py`) — exposes the extraction pipeline as an
  async HTTP API. `POST /extract` accepts PDF uploads and returns a `job_id`
  immediately; `GET /jobs/{job_id}` polls status and retrieves the result.
  `DELETE /jobs/{job_id}` cleans up completed jobs.
- `src/api/` module — `jobs.py` (in-memory job store), `models.py` (Pydantic
  response models), `runner.py` (background extraction task with resume
  detection).
- `src/utils/tracing.py` — `tracing_span()` async context manager, shared by
  both the CLI and the API to open a Langfuse span without duplicating the
  `if/else` branch in each entry point. `main.py` updated to use it.
- `API_README.md` — full endpoint reference, job lifecycle diagram, operational
  notes, and configuration guide.
- `GET /health` — returns model, supported doc types, and Langfuse status.
- Checkpoint resume via API — re-submitting a PDF whose extraction was
  interrupted (e.g., server restart) resumes from the last checkpoint rather
  than restarting from page 1.
- Idempotent job IDs — `job_id` is the SHA-256 hash of the PDF; submitting the
  same file twice returns the existing result without restarting the pipeline.

### Changed

- `pyproject.toml` — added `fastapi`, `uvicorn[standard]`, `python-multipart`.
- `.gitignore` — added `tmp/` (API upload staging directory) and
  `api_checkpoint.db` (API-specific SQLite checkpoint).

## [0.2.0] — 2026-05-30

### Added

- **Langfuse observability** — optional end-to-end tracing via Langfuse v4.
  Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env` to enable.
  Every pipeline run produces a trace with node spans, Claude API calls, token
  usage (including prompt-cache hits), and extraction metadata. Absent keys →
  pipeline runs unchanged with no tracing.
- `src/utils/pdf_utils.py` — shared `hash_file` and `encode_pdf_async` helpers
  (eliminates duplicate implementations that previously existed in `main.py`
  and `extractor_node.py`).
- `.env` / `python-dotenv` support — `ANTHROPIC_API_KEY` (and now Langfuse keys)
  are loaded from a gitignored `.env` file at startup.
- `.env.example` — documents all required environment variables.

### Changed

- **Claude PDF Chat migration** — replaced `pdfplumber` text extraction with
  Claude's native PDF vision API. Every page is sent as a `document` block with
  `cache_control: ephemeral`, achieving >90% cache-hit rate on input tokens
  across multi-page documents. Works on scanned PDFs and complex layouts.
- `pypdf` replaces `pdfplumber` for page counting and encrypted-PDF detection.
- `src/schema_registry.py` — schema directory now anchored to `__file__`
  instead of the process working directory, fixing runs from outside the project
  root.
- `pyproject.toml` — removed `pydantic` and `pdfplumber` direct dependencies;
  added `pypdf`, `python-dotenv`, `langfuse`, `langchain`.

### Fixed

- **Retry accumulation** (`state.py`, `extractor_node.py`, `retry_node.py`) —
  `merge_flat_blocks` reducer now accepts `None` as a reset sentinel. Extractor
  and retry nodes emit `None` to clear the buffer before each fresh run,
  preventing stale blocks from accumulating across retry attempts.
- **Bare `next()` crash** (`worker_node.py`, `hierarchy_node.py`) — replaced
  with `next(..., None)` + explicit `ValueError`, preventing a PEP 479
  `StopIteration` → `RuntimeError` conversion that bypassed tenacity retries.
- **Empty-block retry loop** (`retry_node.py`) — explicit emptiness check now
  produces a meaningful error message instead of "Unknown schema violation"
  when the model returned no blocks.
- **Blocking file I/O in async coroutines** (`worker_node.py`,
  `classifier_node.py`) — PDF encoding moved to `asyncio.to_thread` via
  `encode_pdf_async`, avoiding event-loop stalls on large PDFs.
- **Orphaned block warnings** (`hierarchy_node.py`) — blocks missing from the
  hierarchy agent's `relation_map` now emit a warning to `extraction_warnings`
  instead of silently being promoted to root.
- **Duplicate hash functions** (`main.py`, `extractor_node.py`) — consolidated
  into `hash_file` in `src/utils/pdf_utils.py`.

## [0.1.0] — 2026-05-30

Initial release — LangGraph multi-agent PDF structure extractor with:

- StateGraph pipeline: native extractor → classifier → pioneer parser →
  self-healing validation loop → burst dispatcher → hierarchy agent
- JSON Schema Draft-07 validation with `SchemaRegistry`
- SQLite checkpoint persistence via `AsyncSqliteSaver`
- Supported document types: `invoice`, `scientific_paper`, `baseline_core`
