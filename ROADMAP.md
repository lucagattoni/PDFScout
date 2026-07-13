# PDFScout — Roadmap

The single tracking document for this project's future direction. Every open
item, deferred decision, and rejected proposal lives here — not in chat history,
not in private notes. When priorities change, update this file in the same
commit as the work that changes them.

Current version: see [CHANGELOG.md](CHANGELOG.md)

---

## Open Now

Ordered by priority. Pick from the top unless there's a reason not to.

### 1 · Determinism strategy — maximize reproducibility (2026-07-13 research conclusion)

**Bottom line: bit-identical output across fresh runs is not achievable on the
hosted Claude API — the goal is minimizing variance, not "determinism."**
`temperature`/`top_p`/`top_k` are 400-rejected on the current model (removed
v1.6.4), there is **no `seed` parameter**, and even `temperature=0` never
guaranteed identical output. The dominant cause is *batch-invariance*: hosted
inference batches requests dynamically, so GPU reduction-kernel order — and thus
the exact logits — shifts with batch size/load. Fixing that needs
batch-invariant kernels in the serving stack, which Anthropic controls, not us
(Thinking Machines Lab, "Defeating Nondeterminism in LLM Inference", 2025).

Levers, most → least in our control:

**A · Application-level (ours; the only true determinism we have — already shipped).**
- **Checkpoint cache by `pdf_hash`.** Same PDF → same `thread_id` → LangGraph
  resumes from `state_checkpoint.db` without re-calling the model → byte-identical
  on re-run. Caveat: only same-file re-runs on a persistent DB; a fresh run,
  cleared DB, or different machine re-infers.
- **Deterministic post-processing.** `geometric_pre_sorter` sorts with a
  `block_id` final tiebreak and dedups by `block_id` → identical block set →
  identical ordering. Keep every downstream sort/dedup total-ordered.

**B · Request parameters (ours to set; each needs a quality check before committing).**
- **Disable thinking — highest-value lever.** Post-Sonnet-5, omitting `thinking`
  silently runs *adaptive* thinking, whose depth/content vary run-to-run and feed
  the output. Workers + hierarchy already force `tool_choice` (thinking
  suppressed); the **classifier runs free-form → adaptive on** — this is Open #2.
  Recommend setting `thinking={"type":"disabled"}` **explicitly on every call**,
  not relying on implicit `tool_choice` suppression.
- **`strict: true`** on the extraction + `set_block_relations` tools (with
  `additionalProperties:false` + `required`) → guarantees schema-exact tool
  inputs, removing field-ordering/missing-field structural variance at the API
  layer; complements the existing jsonschema retry loop.
- **`output_config={"effort":"low"}`** (default is `high`) → less exploration,
  more scoped/consistent output for a mechanical task. Test hierarchy accuracy
  first — relational reasoning may want `medium`.
- **Prompt tightening** — "extract only what is present; do not infer,
  summarize, or re-order." The current model follows literally, so explicit
  scope reduces semantic variance.

**C · Fundamental ceiling (not ours).** No `seed`; batch-invariance
nondeterminism; prompt caching does not touch output sampling (neither helps nor
hurts determinism).

**Measure it, don't assume it.** The real-golden corpus already quantifies
variance: `raw_block_counts` across `n_runs: 5` and the `classification_unstable`
flag (e.g. `sp-1` = [106,101,106,102,106]). Use that spread as the determinism
metric — apply the B-levers, regenerate, and check whether block-count spread and
`classification_unstable` shrink. This turns "as deterministic as possible" into
a measurable acceptance test.

**Actionable next steps (tracked):** Open #2 (disable classifier thinking) — the
first and highest-value fix — **shipped in v1.8.0** (`thinking: disabled` on the
classifier call). Open #3 (completeness oracle) targets the *symptom*
of residual variance — silently dropped blocks — regardless of cause. New
candidates from this analysis: (i) add `strict:true` to the extraction/hierarchy
tools; (ii) trial `effort:"low"`; (iii) add a block-count-spread-over-N-runs
check to golden regeneration.

**Scope:** (i)/(ii) Small each + one paid verification run; the checkpoint-cache
and deterministic-sort guarantees (A) are already in place.

Items 6 and 7 remain from the 2026-07-13 real-document test session (2-page Irish
utility bill + 3-page Italian Enel invoice, both extracted end-to-end on v1.7.2
with per-call usage instrumentation).

### 7 · Cross-page duplicate blocks and dropped sections in burst extraction

**What (found 2026-07-13 on a real 16-page paper):** adjacent burst workers each
extract the full PDF with a "page N only" instruction; near page boundaries the
model sometimes re-emits neighbouring-page blocks (observed: "3.1 Pre-training
BERT", "Task #1/#2", "References" duplicated under distinct block_ids — 251
blocks where 5 prior runs produced 126–162) while other sections drop entirely
(observed: "3.2 Fine-tuning BERT", "4 Experiments" headings absent). The
hierarchy node's dedup is by block_id only, so cross-worker duplicates survive
into the output.

**Investigate:** content+bbox-based dedup across pages (same normalized text +
overlapping bbox on the same page number → duplicate); stricter page-exclusivity
prompting; and page-attribution validation (block's bbox page vs assigned page).
**Shipped in v1.9.0:** (a) cross-page duplication detection in
`coverage_auditor` — flags a page whose substantial blocks mostly duplicate ONE
other page (single-dominant rule suppresses templated-boilerplate false
positives; validated: catches the real 4/5 failure, silent on clean docs);
(b) prevention — worker prompts carry first/last native-text-layer line anchors
per page when the layer is usable.

**Remains open:** structural fix (send each worker a single-page PDF —
trade-off: loses the shared prompt-cache prefix); auto-retry of a flagged page;
single dropped headings on otherwise-covered pages (needs span/bbox-aware
matching — v2 of the coverage oracle).

### 6 · Real-document golden corpus completion (Group R)

**Generator improvement (small, found during v1.9.0 regen):**
`generate_real_ground_truth.py` computes `metadata_required` consensus by exact
value equality, so run-to-run case flicker ("Physics-Informed" vs
"Physics-informed") drops a key from the required set entirely (sp-1 lost
`title`). The consensus grouping should use the same normalized equality as
`test_real_docs._norm_eq` and store the most common raw value.

**Update (2026-07-13, v1.8.x):** the sp goldens are additionally **stale for the
current model** — they were generated 2026-06-04 under the previous MODEL. The
e2e generalization run showed: sp-4 block counts shifted below `min_blocks`
(281 vs golden 309, old-model runs were 314–366); some long
`spot_check_fragments` no longer extract verbatim; fragment stability differs
run-to-run (also see Open #3). Metadata byte-equality brittleness is fixed
(normalized comparison in `test_real_docs.py`, v1.8.2), but `min_blocks` and
fragment sets need regeneration via `scripts/generate_real_ground_truth.py`
(5 runs per slot — nontrivial API cost, sp-4 is a large NIST document; get
sign-off before running).

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
| Completeness oracle (`coverage_auditor` node) | v1.9.0 | Was Open #3. Native-text-layer word-coverage audit per page, warning-only; self-disables on unusable layers (subset fonts → control-char soup); figure pages get a lower bar. Validated: flags the real dropped-page case at 0% coverage, silent on known-good runs and on a 16-page paper |
| sp goldens refreshed for current model + large-doc skip | v1.9.0 | sp-1/sp-5 regenerated (5 runs each); sp-4 carries `skip_e2e_reason` in the manifest (large doc, deferred) |
| Classifier thinking pinned off + retry/usage observability | v1.8.0 | `thinking: disabled` on classifier (adaptive default would blow the 10-token budget); `[RETRY]` stderr lines with discarded validation errors; `PDFSCOUT_LOG_USAGE=1` per-call usage; end-of-run USAGE summary; Langfuse trace usage metadata; `usage_log` state field |
| Reading-order banding v2 — general, scale-invariant | v1.7.3 | `plans/20260713_0354-reading-order-band-splits.md` — within-band column-major, heading pull-down, all knobs as span fractions; 11/12 human-order constraints on real docs (was 5/12); known limitation: bandless pages stay whole-page column-major |
| Prompt caching verified on real docs | v1.7.2 session | Burst pages + retries read the full ~11.8k-token PDF prefix from cache (pioneer writes it); classifier writes a separate orphaned entry (→ Open #5); hierarchy call uncached |
