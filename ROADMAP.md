# PDFScout — Roadmap

This document tracks planned and deferred development work. Items are grouped
by category and ordered by priority within each group.

Current version: see [CHANGELOG.md](CHANGELOG.md)

---

## Category A — Infrastructure / Correctness

### C3 · API job-loss regression test (Low effort)

**What:** No test verifies that job records survive a server restart. `A1` (SQLite
persistence) is already shipped; this test is its missing regression gate.

**Fix:** Integration test — create a job, re-initialise the `JobStore` (simulate
restart), assert the job is still retrievable via `GET /jobs/{id}`.

**Scope:** ~30 lines in `tests/integration/test_api_jobs.py`.

---

### A2 · Burst page validation full parity ✅ Done in v1.5.0

Burst pages now retry inline up to 3 times on schema validation failure,
mirroring the pioneer's graph-level retry loop.

---

## Category B — Features

### B1 · New document schema — `contract` ⭐ High priority

**What:** Only 3 doc types exist. `contract` is the highest-value next target:
well-defined structure (parties, recitals, clauses, signatures, effective date),
clearly distinct from `invoice` and `scientific_paper`, high real-world demand.

**Scope per new schema:**
1. `schemas/contract.json` — 8-type block enum + metadata fields (`parties`,
   `clause`, `signature`, `effective_date`)
2. `src/config.py` — add `"contract"` to `SUPPORTED_DOC_TYPES`
3. `src/nodes/worker_node.py` — add contract-specific extraction instructions to
   `_doc_type_instructions()`
4. Synthetic PDF fixtures + golden files (D-group style: 3–5 tests)
5. B-group adversarial test: near-miss document correctly rejected to the right type

**Risk:** Classifier prompt dilution — adding a new type may slightly degrade
classification confidence on existing types. Run the full B-group stability check
after adding the schema and confirm no regression before shipping.

---

### B2 · Confidence scores on blocks (Medium effort)

**What:** All blocks are returned with equal weight. A `confidence` field (0.0–1.0)
would help downstream consumers (RAG pipelines, review UIs) identify uncertain
extractions — e.g. low-resolution scans, obscured text, merged-cell tables.

**Fix:** Add `confidence` (number, 0–1, optional) to `baseline_core.json`.
Add a prompt instruction for when to set it below 1.0. Gate with an H-group test
(degraded text fixture, at least one block has `confidence < 1.0`).

**Risk:** Model may set confidence arbitrarily rather than meaningfully.
Needs a stability gate before asserting specific values in tests.

---

### B3 · Streaming / SSE output from API (High effort — deferred)

**What:** `POST /extract` returns a `job_id` and the client polls. For interactive
UIs, server-sent events would allow page-by-page block streaming as the burst
dispatcher completes each page.

**Fix:** New `GET /jobs/{id}/stream` SSE endpoint using LangGraph's `astream_events`.

**Risk:** High — SSE connection lifecycle (disconnect, reconnect, backpressure),
LangGraph event filtering, and partial-result delivery are all non-trivial.
Defer until core correctness and schema coverage are solid.

---

### B4 · Multi-model support (Deferred indefinitely)

The extraction prompt is calibrated to a specific model family. Supporting
per-request model selection would require re-validating all e2e tests and golden
files against each target model. Low value relative to the risk of silent
quality regression. Revisit only if there is a concrete cost/speed requirement.

---

## Category C — Test coverage

### C2 · Classifier fallback integration test (Low effort)

**What:** Unit tests cover the fallback (`test_unknown_falls_back` in
`test_classifier_node.py`), but no integration test verifies that the full
pipeline completes with a valid `baseline_core`-shaped result when the
classifier returns garbage.

**Fix:** Integration test in `test_graph_pipeline.py` — mock `_classify` to
return `"garbage_type"`, assert pipeline completes and `document_type` is
`baseline_core`.

**Scope:** ~20 lines. No new fixture needed.

---

## Deferred / Rejected

| Item | Decision |
|------|----------|
| **A5 Files API** — upload PDF once, reference by file_id | Rejected: `cache_control` compatibility undocumented for Files API; current base64 + `cache_control` is the documented recommendation. Revisit if Anthropic explicitly documents Files API + caching. |
| **Option B — Merge classifier into pioneer** | Rejected: silent misclassification risk (wrong type that produces syntactically valid blocks passes validation silently), retry loop quality degrades for type-level errors, implementation cost disproportionate to savings at current scale. Full analysis in `plans/20260608_1130-merge-classifier-into-pioneer.md`. |
