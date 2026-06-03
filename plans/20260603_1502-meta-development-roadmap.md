# PDFScout — Meta Development Roadmap

_Created: 2026-06-03 15:02_
_Updated: 2026-06-03 15:05 · DA review v1 — A2 placement corrected (hierarchy entry not new node), A4 fallback risk added, B1 classifier dilution risk added_
_Updated: 2026-06-03 15:12 · A3, A4, A6, A7 implemented and shipped in v1.2.0_

## Purpose

Survey all available development directions after the 1.1.1 release (37/37 e2e tests green).
Provides a prioritised menu for the next planning cycle; each item has its own plan before implementation.

---

## Current state

| Dimension | Status |
|---|---|
| Pipeline | 7-node LangGraph DAG; native extractor → classifier → pioneer → retry loop → burst → hierarchy |
| Test suite | 37 e2e tests across 9 groups (A–I); 1 full-chain no-mock group (I) |
| API | FastAPI `POST /extract` + `GET /jobs/{id}` + `DELETE /jobs/{id}` + `GET /health`; in-memory job store |
| Schemas | 3 doc types: `baseline_core`, `invoice`, `scientific_paper` |
| Observability | Optional Langfuse tracing; all node spans + token usage |
| Known gaps | 5 infrastructure issues identified below; no streaming; single-model hardcoded |

---

## Category A — Infrastructure / Correctness

These are bugs or reliability gaps in the current codebase — not features.

### A1 · Job store persistence ★★★ (High value, Low effort)

**Problem:** `jobs: dict[str, JobRecord] = {}` in `src/api/jobs.py` is in-memory. A server restart silently loses all in-flight and completed jobs. Any client polling `GET /jobs/{id}` gets 404 after a restart — no error, just a ghost job.

**Fix:** Swap the dict for a small SQLite table (already a project dependency via `langgraph-checkpoint-sqlite`). `JobRecord` maps cleanly to a single table. Job IDs are SHA-256 hashes so they're already a natural PK. Checkpoint resume already works end-to-end; this makes job status and results survive restarts too.

**Scope:** `src/api/jobs.py` only. Schema migration is one `CREATE TABLE IF NOT EXISTS`.

**Risk:** Low. SQLite is already used for LangGraph checkpoints; adding a second DB file (`api_jobs.db`) keeps concerns separate and avoids schema collision.

---

### A2 · Burst-page validation gap ★★ (Medium value, Medium effort)

**Problem:** Pioneer (page 1) runs through a validation + retry loop (`pioneer_validation_route`, max 3 retries). Pages 2–N sent through `burst_dispatcher` go directly to `parser_worker` nodes with only tenacity retry for HTTP 429/529. A malformed page-2 JSON response (wrong field types, missing required fields) will propagate into `hierarchical_document_tree` undetected.

**Fix:** Two options:
1. **Narrow:** Validate blocks at the entry of `hierarchy_node` (before applying `relation_map`) — filter/log invalid blocks and continue. No retry. The graph is `parser_worker → hierarchy_node` with a `merge_flat_blocks` reducer accumulating all burst results; `hierarchy_node` is the earliest point where all pages are available. No new graph node needed.
2. **Full parity:** Thread the same `pioneer_validation_route` retry logic into each `parser_worker`. Significantly more complex; requires LangGraph subgraph or a shared validation utility called within the worker.

Recommend option 1 first. It catches corruption at the natural aggregation point without redesigning the burst architecture.

**Scope:** ~30 lines added to the start of `hierarchy_node.py`; no graph topology changes.

**Risk:** Medium. The validation must not raise and abort the pipeline — it must log and drop. Thorough test needed (C1).

---

### A3 · Hierarchy output validation ★ (Low value, Low effort)

**Problem:** `hierarchy_node` calls Claude, gets `relation_map`, and promotes orphan blocks to root with a warning but no validation that `relation_map` itself is structurally sound (e.g., circular references, references to non-existent block IDs). Currently silent.

**Fix:** Before applying the `relation_map`, validate: (a) all `child_id` values exist in the block list, (b) no block is its own parent, (c) no circular chains. Log a warning per violation; drop bad edges (don't crash).

**Scope:** ~20 lines added to `hierarchy_node.py`.

**Risk:** Low. Purely additive validation; existing behaviour preserved when output is clean.

---

### A4 · API version string bug ★ (Low value, Trivial effort)

**Problem:** `api.py` line 14: `FastAPI(title="PDFScout API", version="0.3.0")`. This was the version at API introduction and was never updated. Now stale (current: 1.1.1).

**Fix:** Read version from `importlib.metadata.version("pdfscout")` at startup, with a try/except fallback to read `[project] version` from `pyproject.toml` directly. **Caution:** `importlib.metadata` raises `PackageNotFoundError` when the package is run from source without an editable install (confirmed in the dev environment). The fallback is required, not optional.

**Scope:** `api.py` only; ~5 lines with the try/except.

**Risk:** Very low. Fallback guarantees the app always starts.

---

### A5 · Double PDF encoding (Files API opportunity) ★★ (Medium value, Medium effort)

**Problem:** Both `classifier_node.py` and `worker_node.py` call `encode_pdf_async` independently. For a 10 MB PDF this is ~13 MB of base64 computed twice and sent in two separate API calls. The Anthropic Files API (`client.beta.files.upload`) would encode once, store server-side, and reference by file ID in subsequent calls — reducing token count and latency for large PDFs.

**Fix:** In the pipeline state, after the native extractor, upload the PDF once and store the `file_id` in state. Both classifier and worker reference the same file ID.

**Scope:** New `upload_node` (or inline in extractor), state field `pdf_file_id`, both classifier and worker updated to use file ID when present. Fallback to base64 if Files API unavailable (API key tier check).

**Risk:** Medium. Files API is in beta; introduces a new API surface. Need to handle upload failures and file TTL (files expire after 24h by default). Test impact: existing e2e tests mock at `_classify` / `_call_api` level, not at the HTTP layer — should be unaffected.

---

### A6 · Hierarchy max_tokens scaling ★ (Low value, Low effort)

**Problem:** `hierarchy_node.py` hardcodes `max_tokens=4000`. A document with 100+ blocks can easily produce a `relation_map` JSON response larger than 4000 tokens. The API silently truncates → malformed JSON → silent orphan-promotion of all remaining blocks.

**Fix:** Scale `max_tokens` with block count: `max_tokens = max(4000, len(blocks) * 40)`. Cap at the model's context limit (8192 for claude-3-5-sonnet-20241022, 64000 for claude-3-5 extended). Log the chosen value.

**Scope:** 1-line change in `hierarchy_node.py`.

**Risk:** Low. Increases token usage proportionally but prevents silent truncation. Cost is bounded by document size.

---

### A7 · Remove unused calibration fixture ★ (Trivial value, Trivial effort)

**Problem:** `tests/fixtures/generators/grp_calibration_multipoint.py` exists and is not referenced by `generate_all.py` or any test. It's dead code that confuses the test fixture picture.

**Fix:** Delete the file, or add it to `generate_all.py` + a calibration test group. Given bbox calibration is permanently closed (`BBOX_ASSERTIONS_VIABLE = False`), deletion is cleaner.

**Scope:** 1 file deleted.

**Risk:** None.

---

## Category B — Features

New capabilities that expand what PDFScout can do.

### B1 · New document schema ★★★ (High value, Medium effort)

**Problem / opportunity:** Only 3 doc types. `contract`, `legal`, `financial_report`, and `medical_report` are natural next targets for real-world use. Each requires: JSON schema in `schemas/`, classifier prompt update, `_doc_type_instructions` in `worker_node.py`, and e2e test fixtures.

**Recommended first target:** `contract` — well-defined structure (parties, clauses, dates, signatures), distinct from `scientific_paper` and `invoice`, good demand signal.

**Scope per new schema:** ~2h. Schema file + classifier update + worker instructions + 3–5 D-group style tests.

**Risk:** Medium. Two specific risks:
1. **Misclassification degrades extraction silently** — recommend adding a B-group adversarial test (near-miss doc correctly rejected to the intended type).
2. **Classifier prompt dilution** — adding a new doc type to the classifier's system prompt increases prompt length and can slightly degrade confidence on all existing types. Run the full B-group stability check after adding each new type to confirm no regression.

---

### B2 · Confidence scores on blocks ★★ (Medium value, Medium effort)

**Problem / opportunity:** All blocks are returned with equal confidence. Downstream consumers (RAG pipelines, UI highlighting) would benefit from a `confidence` field (0.0–1.0) signalling extraction certainty — useful for: low-resolution scans, partially obscured text, tables with merged cells.

**Fix:** Add `confidence` (number, 0–1) as an optional field to `baseline_core.json` (inherited by all schemas). Add a prompt instruction for when to set low confidence. Add one test: H-group fixture with degraded text → at least one block has `confidence < 1.0`.

**Risk:** Medium. Model may set confidence arbitrarily rather than meaningfully. Need a stability gate before asserting specific values.

---

### B3 · Streaming / SSE output from API ★★ (Medium value, High effort)

**Problem / opportunity:** Currently `POST /extract` returns a `job_id` and the client polls. For interactive UIs, server-sent events (SSE) would allow page-by-page streaming of extracted blocks as the burst dispatcher completes each page.

**Fix:** New `GET /jobs/{id}/stream` SSE endpoint. LangGraph emits `astream_events`; filter for `parser_worker` node completions and push each page's blocks as an SSE event.

**Risk:** High. LangGraph's `astream_events` interface is more complex than `ainvoke`. SSE connection lifecycle (client disconnect, reconnect) adds substantial edge cases. Worth a full standalone plan before committing.

---

### B4 · Multi-model support ★ (Low value, High effort)

**Problem / opportunity:** Claude model is hardcoded in `worker_node.py` and `hierarchy_node.py`. Supporting model selection per request (e.g., haiku for speed, opus for accuracy) would give cost/quality flexibility.

**Risk:** High. Different models have meaningfully different instruction-following behaviour. The prompt + schema combination is calibrated for a specific model family. Switching models without re-running the stability gate risks silent regression. Not worth the complexity until the extraction prompt is model-agnostic.

---

## Category C — Test coverage gaps

### C1 · Burst-page adversarial test ★★ (Medium value, Low effort)

**Problem:** No test exercises what happens when a page-2 parser response is malformed. The current test suite only verifies the happy path for multi-page documents (E-group uses correctly-formed blocks).

**Fix:** Mock `parser_worker` for page 2 to return a block missing a required field. Assert: (a) pipeline completes without exception, (b) page-1 blocks are present in output, (c) malformed page-2 block is absent or flagged.

**Scope:** ~40 lines. No new fixture needed; mock the node response.

---

### C2 · Classifier fallback test ★ (Low value, Low effort)

**Problem:** No test verifies the classifier's fallback behaviour when it returns an unexpected/garbage string. The fallback (presumably `baseline_core`) is inferred from reading the code, not covered by a test.

**Fix:** Mock `_classify` to return `"garbage_type"`. Assert the pipeline completes and returns a valid `baseline_core`-shaped result.

**Scope:** ~20 lines. Inline test, no fixture.

---

### C3 · API job-loss regression test ★ (Medium value, Low effort — after A1)

**Problem:** There is no test that verifies job records survive a server restart. This is the observable symptom of the A1 bug.

**Fix:** After A1 is implemented, add an integration test: create a job, re-initialise the job store (simulate restart), assert the job is still retrievable.

**Scope:** ~30 lines. Blocked on A1.

---

## Priority recommendation

| Rank | Item | Status | Rationale |
|---|---|---|---|
| 1 | **A4** (version string) | ✅ v1.2.0 | Eliminates a silent lie in the API response |
| 2 | **A7** (dead fixture) | ✅ v1.2.0 | Reduces fixture confusion |
| 3 | **A6** (hierarchy max_tokens) | ✅ v1.2.0 | Prevents silent data loss on long documents |
| 4 | **A3** (hierarchy validation) | ✅ v1.2.0 | Surfaces corrupt edges that previously propagated silently |
| 5 | **A1** (job persistence) | ⬜ next | Correctness bug for production use; well-contained fix using existing SQLite dep |
| 6 | **C1** (burst adversarial test) | ⬜ next | Validates the most important unguarded failure mode; low effort |
| 7 | **A2** (burst validation) | ⬜ | Closes the gap C1 exposes; medium effort; plan separately |
| 8 | **B1** (new schema) | ⬜ | Highest feature value; warrants its own full plan |
| 9 | **A5** (Files API) | ⬜ | Real cost win for large PDFs; medium risk; plan separately |
| 10 | **B2** (confidence scores) | ⬜ | Nice-to-have; needs stability gate before asserting |
| — | **B3** (streaming) | ⬜ deferred | High effort; defer until core correctness is solid |
| — | **B4** (multi-model) | ⬜ deferred | Low value relative to risk; defer indefinitely |

---

## What to do next

The four trivial fixes (A4, A7, A6, A3) can be batched into a single "cleanup" PR with no plan needed — combined they touch <50 lines across 3 files. A1 + C1 + A2 form a natural correctness sprint. B1 (new schema) is the highest-value feature and warrants its own plan document.
