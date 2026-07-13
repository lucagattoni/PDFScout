# PDFScout — Roadmap

The single tracking document for this project's future direction. Every open
item, deferred decision, and rejected proposal lives here — not in chat history,
not in private notes. When priorities change, update this file in the same
commit as the work that changes them.

Current version: see [CHANGELOG.md](CHANGELOG.md)

---

## Open Now

Ordered by priority. Pick from the top unless there's a reason not to.

### 1 · Real-document golden corpus completion (Group R)

**What:** `tests/integration/test_real_docs.py` (`grp_r`, `e2e`-marked) is
parametrized over 15 manifest slots defined in `tests/fixtures/real_manifest.json`:
`sp-1..6` (scientific_paper), `inv-1..5` (invoice), `bc-1..4` (baseline_core).
Only 10 of 15 have a golden file, and of those, only 5 are actually committed:

| Slot group | Golden generated | Committed |
|---|---|---|
| `inv-1..5` | 5/5 | ✅ 5/5 |
| `sp-1..6` | 5/6 (`sp-1..5`) | ✅ 5/5 (`sp-1..5` committed in v1.6.3, 2026-07-13); `sp-6` ungenerated |
| `bc-1..4` | 0/4 | ❌ 0/4 |

**Fix:**
1. ~~Commit the 5 untracked `sp-*.json` files.~~ Done in v1.6.3 (`b12a29f`/`d617b71`).
2. Run `scripts/download_real_fixtures.py --slot sp-6,bc-1,bc-2,bc-3,bc-4` then
   `scripts/generate_real_ground_truth.py --slot sp-6,bc-1,bc-2,bc-3,bc-4` to
   fill the remaining 5 slots (`sp-6` + `bc-1..4`).
3. Confirm `pytest -m e2e -k grp_r` passes for all 15 slots.

**Scope:** Medium — no code changes, but requires live API calls to generate
ground truth and manual verification of `bc-3`/`sp-1` fixture notes (manifest
flags these as needing selection review). Full detail in
`plans/20260603_1540-real-doc-test-corpus.md` and
`plans/20260604_0739-real-doc-infrastructure.md`.

### 2 · Reading-order banding (in progress — `feat/reading-order-banding`)

**What:** `geometric_pre_sorter` now bands each page at full-width blocks and
orders column-major within each band, fixing unnatural order on invoices/forms
(full-width tables/headers/footers previously sorted after or between side-by-side
field groups). Implemented + unit-tested on the branch.

**Remaining:** user e2e validation before merge — `pytest -m e2e -k "grp_g or grp_r"`
(confirm two/three-column and paper goldens still pass) and a real invoice run
(confirm natural order end-to-end). On green: merge, bump to v1.7.0 (MINOR), move
here to Recently Shipped. Full detail in `plans/20260713_0214-reading-order-banding.md`.

**Scope:** Small — one pure function + a config constant; deterministic, no API cost.

---

## Deferred

### B3 · Streaming / SSE output from API (High effort)

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

## Rejected

| Item | Decision |
|------|----------|
| **A5 Files API** — upload PDF once, reference by file_id | Rejected: `cache_control` compatibility undocumented for Files API; current base64 + `cache_control` is the documented recommendation. Revisit if Anthropic explicitly documents Files API + caching. |
| **Option B — Merge classifier into pioneer** | Rejected: silent misclassification risk (wrong type that produces syntactically valid blocks passes validation silently), retry loop quality degrades for type-level errors, implementation cost disproportionate to savings at current scale. Full analysis in `plans/20260608_1130-merge-classifier-into-pioneer.md`. |

---

## Recently Shipped

Compact history — full detail in [CHANGELOG.md](CHANGELOG.md) and the linked plan files.

| Item | Version | Detail |
|---|---|---|
| C3 · API job-loss regression test | v1.5.1 | `TestJobStorePersistence` in `test_api_jobs.py` |
| A2 · Burst page validation full parity | v1.5.0 | Burst pages retry inline up to 3× on schema failure, mirroring pioneer |
| B1 · `contract` document schema | v1.5.0 | `plans/20260615_2020-contract-schema-b1.md` |
| B2 · Extraction quality flags on blocks | v1.6.0 | `plans/20260616_0515-confidence-scores-b2.md` |
| C2 · Classifier fallback integration test | v1.6.1 | `TestClassifierFallback` in `test_graph_pipeline.py` |
