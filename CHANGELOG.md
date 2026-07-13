# Changelog

## [1.10.1] — 20260713 08:02

### Changed

- **Strict tool use on all model-facing tools** (`src/schema_registry.py`,
  `src/nodes/hierarchy_node.py`) — extraction tools and the hierarchy relation tool
  now set `strict: true`: tool inputs are guaranteed schema-exact at generation time,
  removing structural variance (missing fields, stray keys) before the jsonschema
  retry loop. Two-layer validation: the API-side schema is sanitized (`_strictify`
  adds `additionalProperties: false` everywhere and strips unsupported constraint
  keywords — minItems/maxItems/uniqueItems/maxLength/…); the local jsonschema layer
  keeps the full constraints. Optional block fields stay optional. The API's
  `uniqueItems` rejection was caught by a cheap live probe and added to the strip
  set. Live-verified on a real 2-page bill: zero 400s, zero retries, zero warnings,
  richest extraction of that document to date (69 blocks), reasoning behavior
  unchanged on forced-tool calls. Note: the tools-prefix change invalidates existing
  prompt-cache entries once.


## [1.10.0] — 20260713 07:42

### Added

- **Switchable prompt-cache TTL** (`src/utils/usage.py: cache_control()`, env
  `PDFSCOUT_CACHE_TTL=1h`) — multi-run workloads over the same document read the
  ~12k-token PDF prefix at 0.1× across runs instead of racing the 5-minute TTL
  (each sp-5 run takes ~4.5 min — a coin flip). The regeneration script sets it
  automatically; single extractions keep the cheaper 5m default. Runs stay
  sequential by design: truly concurrent identical requests each pay the full
  cache write.
- **CLAUDE.md investigation rule #7: cost cap on paid testing** — most expensive
  workloads need explicit sign-off; minimum viable spend otherwise.

### Fixed

- **Golden `min_blocks` could exceed a generating run's own block count**
  (`scripts/generate_real_ground_truth.py`) — 0.85×p80 under high run-to-run spread
  (observed: counts [210, 247, 255] → threshold 216 > 210, guaranteed flakiness).
  Now clamped to ≤95% of the observed minimum; committed goldens recomputed offline
  (sp-5 216→199, sp-1 105→103).

### Changed

- **sp-5 golden regenerated** for the current model (3 runs, cost-capped; block
  counts 210–255, 10 stable fragments, title+authors consensus) and unskipped.


## [1.9.0] — 20260713 05:21

### Added

- **Completeness oracle** (`src/nodes/coverage_node.py`, new `coverage_auditor` graph
  node between the workers and the hierarchy agent; no API call) — audits each page's
  extracted blocks against the PDF's native text layer, word-level and order-free
  (robust to hyphenation, column reflow, table linearization; table cells and metadata
  count as coverage). Warns below 50% word coverage (25% on figure pages — figures are
  summarized by design); self-disables on unusable native layers (subset-font PDFs
  extract as control-character soup; char-class ratio separates cleanly). Validated:
  flags the historical dropped-page failure at 0%, silent on known-good runs.
  Closes ROADMAP #3.
- **Cross-page duplication detection** (same node) — flags a page whose substantial
  blocks mostly duplicate ONE other page (page-attribution failure: a worker
  re-extracting a neighbouring page, observed on a real 16-page paper as duplicates
  plus silently dropped sections). Single-dominant rule suppresses templated-
  boilerplate false positives. ROADMAP #7 detection half.
- **Native page anchors in worker prompts** (`worker_node.py`) — each page's
  extraction prompt carries the first/last native-text-layer lines («…»), anchoring
  the model to the physical page; best-effort, cache-safe. ROADMAP #7 prevention half.
- **Pioneer [RETRY] visibility** (`retry_node.py`) — the pioneer retry path now prints
  the same [RETRY] stderr line as burst workers (a live run showed a silent retry).

### Changed

- **sp-1 golden regenerated** for the current model (5 runs; min_blocks 90→105,
  unstable fragment dropped by consensus) and e2e-verified against the final pipeline.
- **Manifest `skip_e2e_reason`** — real-doc slots can opt out of routine e2e runs with
  a recorded reason; set for sp-4 (large document, deferred) and temporarily for sp-5
  (regeneration blocked: API credit balance exhausted mid-run on 2026-07-13).

### Fixed

- **Golden regeneration survives single-run failures**
  (`scripts/generate_real_ground_truth.py`) — one failed run no longer aborts the slot
  and loses completed paid runs; requires ≥ max(3, 60%·n) successes.


## [1.8.2] — 20260713 04:43

### Fixed

- **Real-doc golden metadata comparison over-brittle** (`tests/integration/
  test_real_docs.py`) — `metadata_required` compared model-extracted strings by byte
  equality; a one-character case difference ("Physics-Informed" vs
  "Physics-informed") or a line-break hyphenation reading ("task-specific" vs
  "taskspecific") failed the test even though the value was captured. New `_norm_eq`
  compares whitespace/case-normalized with hyphen canonicalization; lists compare
  element-wise. Verified offline against captured trees: all sp-1 and sp-5
  metadata assertions pass.

### Known issues (recorded in ROADMAP)

- sp goldens are stale for the current model (sp-4 `min_blocks` 309 vs observed 281;
  fragment sets drift) — needs regeneration, sign-off required (Open #6).
- Cross-page duplicate blocks + dropped sections observed in burst extraction on a
  16-page paper (new Open #7); block_id-only dedup cannot catch cross-worker
  duplicates.


## [1.8.1] — 20260713 04:23

### Fixed

- **Heading pull-down gap too tight** (`src/config.py`) — `BAND_PULLDOWN_GAP_FRAC`
  0.035 → 0.05. The e2e generalization run caught the synthetic
  `grp_g_heading_table_sidebar` fixture missing pull-down by 0.1 unit (gap 28.0 vs
  threshold 27.9 on a 796 span): the model bounds text glyphs tightly, so real
  heading-to-table gaps include cell padding — about two line-heights, not one.
  Offline replay on both real documents unchanged (11/12 constraints);
  `test_g4_heading_adjacent_to_its_table` now passes live.


## [1.8.0] — 20260713 04:22

### Added

- **Usage observability** (`src/utils/usage.py`, `src/state.py`, all API nodes,
  `main.py`) — every Anthropic call now records a `usage_log` entry (context, input/
  output tokens, cache read/write, stop reason) merged into graph state.
  `PDFSCOUT_LOG_USAGE=1` prints per-call `[USAGE]` lines to stderr in real time; every
  run prints an aggregate `USAGE:` summary; Langfuse traces carry the same totals as
  metadata. Verified live: classifier/pioneer cache writes, burst cache reads and the
  summary line all reported correctly on a real 2-page document.
- **Retry-cause visibility** (`src/nodes/worker_node.py`) — burst validation attempts
  that fail are printed as `[RETRY]` stderr lines with the discarded error at the
  moment they happen, so the cause of paid retries is no longer silent when a later
  attempt succeeds.

### Fixed

- **Classifier truncation risk** (`src/nodes/classifier_node.py`) — the current model
  runs adaptive thinking by default when `thinking` is omitted, and thinking tokens
  count against `max_tokens`; with `CLASSIFIER_MAX_TOKENS = 10` a single thinking
  burst would truncate classification. Thinking is now explicitly disabled on the
  classifier call. (`_classify` now returns `(doc_type, usage)`.)

### Rejected

- **Classifier cache-prefix unification** (ROADMAP, was Open #5) — structural analysis
  showed sharing the workers' cache prefix is impossible: per-doc-type tool lists and
  the workers' forced `tool_choice` (which invalidates the message-tier cache) both
  break the prefix match. Recorded in ROADMAP → Rejected.


## [1.7.3] — 20260713 03:54

### Fixed

- **Reading-order banding v2** (`src/nodes/hierarchy_node.py`, `src/config.py`) — three
  general ordering defects reproduced on real documents (ROADMAP #1): full-width blocks
  no longer lead their band (labels left of a wide block read first); heading/title
  blocks directly above a full-width block are pulled into its band — nearest block,
  jitter-tolerant — so a section heading stays adjacent to its table; all tuning knobs
  are now fractions of the page x-span (`COLUMN_BUCKET_FRAC = 0.11`,
  `BAND_PULLDOWN_GAP_FRAC = 0.035`, `BAND_FULL_WIDTH_FRAC` 0.6 → 0.55), making ordering
  invariant to the model's coordinate scale (observed x-spans 855–1125 for the same A4
  page). Offline replay on two real documents: 11/12 human-reading-order constraints
  (was 5/12). Known limitation recorded in the plan: pages with no full-width block
  remain whole-page column-major. 7 new sorter unit tests (edge cases: jitter, stacked
  tables, negative pull cases, scale invariance, degenerate geometry) and 2 new
  synthetic layout fixtures + e2e tests (`grp_g_label_sidebar`,
  `grp_g_heading_table_sidebar`). 180 non-e2e tests.

### Added

- **CLAUDE.md Investigation rules** — offline-replay-first, mechanism-not-document
  root-causing, principle-derived scale-invariant thresholds, edge-case test
  enumeration, anti-overfit gate, synthetic-fixture distillation, ask-on-ambiguity.


## [1.7.2] — 20260713 03:12

### Fixed

- **Dense pages silently dropped by max_tokens truncation** (`src/config.py`,
  `src/nodes/worker_node.py`, `src/nodes/retry_node.py`, `src/state.py`) — pages whose
  extraction needed more than `WORKER_MAX_TOKENS = 4000` output tokens hit
  `stop_reason: "max_tokens"`; the API discards a forced tool call truncated mid-JSON
  (empty `tool_use.input`), which the workers misdiagnosed as *"No blocks were extracted"*
  and retried with an identical budget — 3 guaranteed-identical truncations, then the page
  was dropped with a misleading warning (reproduced on a real 2-page utility bill: page 2
  needed ~5,400 tokens and always came back empty). Two-part fix: `WORKER_MAX_TOKENS`
  raised to 16000 (a cap, not a spend — simple pages cost the same), and both worker nodes
  now check `stop_reason == "max_tokens"`, surfacing a distinct truncation error whose
  retry instruction asks for *more concise* block text instead of nudging the model to
  return more. New `truncation_error` state field threads the detail through the pioneer
  graph-retry path (`retry_incrementor_node` prefers it over the no-blocks message).
  5 new unit tests (169 total non-e2e).

## [1.7.1] — 20260713 02:45

### Fixed

- **Golden `model_version` decoupled from live `MODEL`** (`tests/fixtures/generators/_common.py`)
  — `golden_meta` stamped `model_version: MODEL`, so the session-start fixture regeneration
  rewrote every tracked synthetic golden on each test run and misrepresented provenance
  whenever `MODEL` changed without the (hand-authored, model-agnostic) expected data being
  regenerated. Replaced with a fixed `_GOLDEN_MODEL_VERSION = "claude-sonnet-5"` literal, so
  regeneration produces no golden churn. Two regression tests
  (`tests/unit/test_golden_meta.py`) fail if the coupling is reintroduced. Verified: v1.6.4's
  golden regen changed only this one metadata line per file — no expected data was altered.

## [1.7.0] — 20260713 02:33

### Changed

- **Reading-order banding in `geometric_pre_sorter`** (`src/nodes/hierarchy_node.py`,
  `src/config.py`) — the pre-sorter now splits each page into horizontal bands at every
  full-width block (width ≥ new `BAND_FULL_WIDTH_FRAC = 0.6` of the page x-span) and orders
  blocks column-major within each band, instead of column-major over the whole page. This
  produces natural top-to-bottom reading order for invoices/forms (full-width tables,
  headers, and footers no longer sort after or between the side-by-side field groups) while
  leaving multi-column papers grouped by column. Strict superset of the previous behavior:
  with no full-width blocks every block lands in band 0 and the order is unchanged. Two new
  unit tests cover the full-width-band case and a real-invoice regression fixture (18 blocks).
  Validated by the full non-e2e suite and a real invoice end-to-end run.

## [1.6.4] — 20260713 02:22

### Fixed

- **`temperature` param rejected by Sonnet 5** (`src/config.py`, `src/nodes/classifier_node.py`,
  `src/nodes/worker_node.py`, `src/nodes/hierarchy_node.py`) — the API began returning
  `400 invalid_request_error: 'temperature' is deprecated for this model` on
  `claude-sonnet-5`, crashing the classifier node on every run. Removed
  `temperature=EXTRACTION_TEMPERATURE` from all three API call sites and dropped the
  `EXTRACTION_TEMPERATURE` constant (README config table updated). Verified by the full
  non-e2e suite (160 passed) and a real-bill end-to-end run.
- **Ruff UP017 lint failures** (`scripts/evaluate_real_docs.py`,
  `scripts/generate_real_ground_truth.py`) — `datetime.timezone.utc` → `datetime.UTC`
  alias; pre-existing failures surfaced by the ruff bump in the 1.6.3 lockfile refresh.

### Changed

- **Golden fixtures regenerated** (`tests/fixtures/golden/grp_*.json`) — `model_version`
  meta updated `claude-sonnet-4-6` → `claude-sonnet-5`; stale since the MODEL bump, rewritten
  by the session-start fixture regeneration hook.

## [1.6.3] — 20260713 01:56

### Changed

- **Dependency lockfile refresh** (`uv.lock`) — ~30 transitive/direct packages bumped
  (fastapi 0.105→0.116, anthropic 0.105→0.116, langgraph 1.2.4→1.2.9, ruff, opentelemetry,
  and others); `pyproject.toml` declared constraints unchanged. Validated by the full
  non-e2e suite (160 passed) and a real-invoice end-to-end run on Sonnet 5.

### Added

- **Scientific-paper golden fixtures** (`tests/fixtures/real_golden/sp-1.json`…`sp-5.json`) —
  ground-truth for the `@pytest.mark.e2e` `test_real_doc` slots `sp-1`…`sp-5`, which
  previously skipped for lack of a golden file. Structural metrics plus public paper
  title/abstract and spot-check fragments. Slot `sp-6` remains ungenerated and still skips.

## [1.6.2] — 20260713 01:52

### Fixed

- **Async streaming bug** (`main.py`, `src/api/runner.py`) — both the CLI and the API job
  runner iterated the LangGraph app with `async for` over the **synchronous** `.stream()`
  method, which returns a plain generator and raised
  `TypeError: 'async for' requires an object with __aiter__ method, got generator`. Switched
  both call sites to the async `.astream()`. Also fixed a latent companion bug in `main.py`
  where the sync, non-awaitable `.get_state()` was `await`ed; now uses `.aget_state()`
  (the runner already used the async variant). Test mocks in
  `tests/integration/test_api_runner.py` updated to stub `astream`.

### Changed

- **Model upgraded to Claude Sonnet 5** (`src/config.py`, `README.md`) — `MODEL` bumped from
  `claude-sonnet-4-6` to `claude-sonnet-5` for all classification, extraction, and hierarchy
  calls. Verified end-to-end on a real invoice.

## [1.6.1] — 2026-07-07

### Added

- **C2 — Classifier fallback integration test** (`tests/integration/test_graph_pipeline.py`) —
  `TestClassifierFallback::test_c2_unknown_doc_type_falls_back_to_baseline_core` verifies that
  when the classifier returns an unsupported token (`"garbage_type"`), the full pipeline
  completes end-to-end with `document_type == "baseline_core"` in both the final state and the
  output tree. Closes the C2 roadmap item; unit-level fallback coverage already existed in
  `test_classifier_node.py`.

## [1.6.0] — 2026-06-16

### Added

- **B2 — Extraction quality flags and notes** (`schemas/baseline_core.json`,
  `schemas/invoice.json`, `schemas/scientific_paper.json`, `schemas/contract.json`,
  `src/nodes/worker_node.py`) — all four schemas now include two companion optional fields
  on every block. `extraction_flags` is an array of named quality signals (`partial_visibility`,
  `low_legibility`, `ambiguous_type`, `possible_encoding_error`) with `uniqueItems: true` —
  invalid or duplicate flags are rejected by schema validation. `extraction_note` is a
  free-text string set alongside flags to describe the specific issue on that block in one
  sentence; designed to feed a downstream remediation agent that can inspect flagged blocks
  and attempt targeted correction. A single `_EXTRACTION_FLAGS_INSTRUCTION` constant is
  appended to the extraction prompt in both `window_parser_node` and `burst_worker_node`.
  Empty/absent = high confidence.

- **32 new unit tests** — 28 parametrized across all 4 schemas × 7 test functions
  (`test_extraction_flags_valid_flag_accepted`, `test_extraction_flags_invalid_flag_rejected`,
  `test_extraction_flags_absent_passes`, `test_extraction_flags_duplicate_flag_rejected`,
  `test_extraction_note_with_flags_accepted`, `test_extraction_note_absent_passes`,
  `test_extraction_note_too_long_rejected`) plus 4 passthrough tests asserting that both
  flags and note survive the `window_parser_node` and `burst_worker_node` paths unchanged.
  The `maxLength` boundary test uses `EXTRACTION_NOTE_MAX_LENGTH + 1` from config so it
  stays valid if the constant is changed.

## [1.5.1] — 2026-06-16

### Added

- **C3 — API job-loss regression tests** (`tests/integration/test_api_jobs.py`) — two tests
  in `TestJobStorePersistence`: `test_job_survives_reinit` (completed job written to SQLite
  is reloaded after re-init, simulating a server restart) and
  `test_running_job_marked_failed_on_reinit` (jobs still in `running` state at restart are
  automatically marked `failed` on `init()`). Both tests use `tmp_path` for isolation and
  reset module-level state in `finally` blocks.

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
- **`contract` document type** (`schemas/contract.json`, `src/config.py`,
  `src/nodes/worker_node.py`) — new first-class schema for legal contracts.
  Adds a `signature_block` block type (contract-only) and four metadata subfields:
  `contract_meta` (contract_type, effective_date, governing_law), `party`
  (party_name, party_role, address), `clause` (clause_number, clause_title),
  and `signature` (signatory_name, party_role, date_label). The classifier
  automatically receives `"contract"` as a valid output token via `SUPPORTED_DOC_TYPES`.
- **B3 classifier fixture** (`tests/fixtures/generators/grp_b_classifier.py`) —
  synthetic one-page "SERVICE AGREEMENT" PDF with parties, recitals, three clauses,
  and a signature block; used by the B3 e2e classifier accuracy test.
- **B4 adversarial classifier fixture** — vendor invoice with a "Terms and Conditions"
  footer (legal-sounding language); asserts the classifier returns `"invoice"` not
  `"contract"`, guarding against alphabetical-first position bias.
- **Unit tests** (`tests/unit/nodes/test_classifier_node.py`,
  `tests/unit/test_schema_registry.py`) — `test_contract_classified`,
  `test_contract_loads`, `test_contract_tool_name`, `test_contract_paragraph_block_passes`,
  `test_contract_signature_block_type_accepted`, `test_contract_invalid_block_type_rejected`.

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
