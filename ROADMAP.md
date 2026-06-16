# PDFScout — Roadmap

This document tracks planned and deferred development work. Items are grouped
by category and ordered by priority within each group.

Current version: see [CHANGELOG.md](CHANGELOG.md)

---

## Category A — Infrastructure / Correctness

### C3 · API job-loss regression test ✅ Done in v1.5.1

Two tests in `TestJobStorePersistence` (`tests/integration/test_api_jobs.py`):
`test_job_survives_reinit` (completed job reloaded after re-init) and
`test_running_job_marked_failed_on_reinit` (interrupted jobs auto-failed on restart).

---

### A2 · Burst page validation full parity ✅ Done in v1.5.0

Burst pages now retry inline up to 3 times on schema validation failure,
mirroring the pioneer's graph-level retry loop.

---

## Category B — Features

### B1 · New document schema — `contract` ✅ Done in v1.5.0

`schemas/contract.json` shipped with `signature_block` block type and metadata
subfields `contract_meta`, `party`, `clause`, `signature`. B3/B4 classifier
e2e tests added. Full detail in `plans/20260615_2020-contract-schema-b1.md`.

---

### B2 · Extraction quality flags on blocks ✅ Done in v1.6.0

`extraction_flags` (optional array of enum strings) added to all 4 schemas and
both extraction prompts. Four flags: `partial_visibility`, `low_legibility`,
`ambiguous_type`, `possible_encoding_error`. Empty array = high confidence.
Designed for RAG pipeline filtering. Full detail in
`plans/20260616_0515-confidence-scores-b2.md`.

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
