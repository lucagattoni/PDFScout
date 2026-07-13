# PDFScout — Roadmap

The single tracking document for this project's future direction. Every open
item, deferred decision, and rejected proposal lives here — not in chat history,
not in private notes. When priorities change, update this file in the same
commit as the work that changes them.

Current version: see [CHANGELOG.md](CHANGELOG.md)

---

## Open Now

Ordered by priority. Pick from the top unless there's a reason not to.

Items 3 and 6 remain from the 2026-07-13 real-document test session (2-page Irish
utility bill + 3-page Italian Enel invoice, both extracted end-to-end on v1.7.2
with per-call usage instrumentation).

### 3 · Page-1 completeness variance — no detector for silently dropped blocks

**What:** across three runs of the same bill, page 1 gained/lost blocks
("Total due" missing in one run, "Energy tips" in another) with no warning.
Since `temperature` was removed (v1.6.4) there is no determinism knob, and
nothing detects a dropped region.

**Investigate:** use the native text layer (already extracted by
`native_extractor`) as a completeness oracle — diff significant native-layer
text spans against extracted block text; unmatched spans → targeted retry or at
minimum an `extraction_warning`. Same philosophy as the v1.7.2 truncation fix:
convert silent drops into visible ones.

**Scope:** Medium — needs a matching heuristic robust to whitespace/reflow, and
a threshold for "significant".

### 6 · Real-document golden corpus completion (Group R)

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

---

## Deferred

### D1 · Streaming worker calls for >16k-token pages (contingency)

**What:** `WORKER_MAX_TOKENS = 16000` (v1.7.2) covers the densest real pages
seen so far (~5.4k needed), but a page requiring more would truncate again —
now correctly reported as a truncation warning rather than a silent drop.

**Fix when triggered:** switch worker calls to `client.messages.stream(...)` +
`get_final_message()`, raising the safe ceiling to 64–128k. Defer until a real
document actually hits the 16k warning.

---

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
| **Classifier cache-prefix unification (was Open #5)** | Rejected after analysis (2026-07-13): sharing the workers' cache requires an identical `tools` list AND identical `tool_choice` — but workers send a per-doc-type tool the classifier cannot know in advance, and the workers' forced `tool_choice` invalidates the message-tier cache (where the PDF lives) even with identical tools. Structural, not tunable. Revisit only if the API changes cache semantics for `tool_choice`. |
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
| Reading-order banding | v1.7.0 | `plans/20260713_0214-reading-order-banding.md` — band pages at full-width blocks, column-major within band |
| Golden `model_version` decoupled from `MODEL` | v1.7.1 | Fixed literal in `_common.py`; stops test runs dirtying tracked goldens (`tests/unit/test_golden_meta.py`) |
| `temperature` removed (rejected by current model) | v1.6.4 | API began rejecting non-default sampling params on the extraction model; removed from all call sites |
| Dense-page max_tokens truncation fix | v1.7.2 | `WORKER_MAX_TOKENS` 4000→16000 + `stop_reason` truncation detection in both workers (branch `fix/worker-max-tokens-truncation`, pending merge). Root cause of "Page 2: no blocks" on real 2-page bill |
| Classifier thinking pinned off + retry/usage observability | v1.8.0 | `thinking: disabled` on classifier (adaptive default would blow the 10-token budget); `[RETRY]` stderr lines with discarded validation errors; `PDFSCOUT_LOG_USAGE=1` per-call usage; end-of-run USAGE summary; Langfuse trace usage metadata; `usage_log` state field |
| Reading-order banding v2 — general, scale-invariant | v1.7.3 | `plans/20260713_0354-reading-order-band-splits.md` — within-band column-major, heading pull-down, all knobs as span fractions; 11/12 human-order constraints on real docs (was 5/12); known limitation: bandless pages stay whole-page column-major |
| Prompt caching verified on real docs | v1.7.2 session | Burst pages + retries read the full ~11.8k-token PDF prefix from cache (pioneer writes it); classifier writes a separate orphaned entry (→ Open #5); hierarchy call uncached |
