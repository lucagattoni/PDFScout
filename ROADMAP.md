# PDFScout — Roadmap

The single tracking document for this project's future direction. Every open
item, deferred decision, and rejected proposal lives here — not in chat history,
not in private notes. When priorities change, update this file in the same
commit as the work that changes them.

Current version: see [CHANGELOG.md](CHANGELOG.md)

---

## Open Now

Ordered by priority. Pick from the top unless there's a reason not to. Item numbers
are stable IDs (cited from the CHANGELOG and plans), not rank — file order is the
priority order. Items 9–15 were added by the 2026-10-19 repository review.

### 9 · Validate the current pipeline end to end (review finding, 2026-10-19)

**What:** The v1.12.2–v1.12.5 fixes (non-strict streaming extraction, the
`PDFSCOUT_EFFORT` knob) and the v1.12.6 corpus refresh were verified by offline
tests and golden regeneration only; the repo does not record a paid e2e re-run
since. Two gaps:

1. **e2e sweep.** Run `pytest -m e2e -k grp_r` (every slot ≤5 pages, so cheap) and
   the synthetic groups a–i; record the outcome in the CHANGELOG.
2. **Effort mismatch.** The v1.12.6 goldens were generated at `effort=low`, but the
   runtime default sends no effort and nothing in the tests or `Makefile` sets
   `PDFSCOUT_EFFORT`. Unless a local `.env` sets it, e2e compares default-effort
   output against low-effort goldens. Settle it with #1's effort decision: run e2e
   under the same setting the goldens used, or regenerate them at the default.

**Scope:** Small — no code, one paid sweep (needs sign-off per the cost cap in
CLAUDE.md → Investigation rules).

### 8 · Usage & cost accounting for tests and e2e runs (Important — requested 2026-07-13)

**What — two layers:**

1. **Token utilisation everywhere (base layer, unconditional).** e2e PDF
   processing already logs it (v1.8.0: `[USAGE]` lines, `USAGE:` summary,
   Langfuse metadata); the gap is **test-side runs** — the golden-generation
   script and API-hitting tests log block counts only. Add per-run and
   per-slot token totals to their logs.
2. **Cost derived from tokens (per call and per document).** Verified
   reliable — see below — so surface a money figure everywhere usage appears.

**Reliability — verified feasible, exact to the cent.** The API `usage` object
returns the exact billed token counts per call (`input_tokens`,
`output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`),
and cost is a deterministic function of them:

| Component | Multiplier on input price |
|---|---|
| Uncached input | 1× ($3/MTok on claude-sonnet-5 as recorded 2026-07-13; the intro $2 rate ended 2026-08-31) |
| Output | $15/MTok as recorded 2026-07-13 (intro $10 ended 2026-08-31) |
| Cache read | 0.1× |
| Cache write, 5m TTL | 1.25× |
| Cache write, 1h TTL | 2× |

`PDFSCOUT_CACHE_TTL` selects the TTL for the whole run, so the correct write
multiplier is always known. **Caveat (the only unreliability):** the API has no
per-request billed-cost field and the org Cost Report Admin API only
aggregates, so pricing lives in a local table (config) that must be kept
current. The intro-pricing window ended 2026-08-31 — verify the rates against
Anthropic's published pricing before populating the table, and re-check it on
every model change.

**How:** price table in `src/config.py` keyed by model id; `cost_of(entry)` in
`src/utils/usage.py`; add `cost` to `usage_entry` output and a `total_cost` to
`summarize_usage`; print in `[USAGE]`/`USAGE:` lines and Langfuse metadata;
golden generator prints per-run and per-slot cost.

### 10 · Model-version trial (review finding, 2026-10-19)

**What:** `MODEL` is pinned to `claude-sonnet-5`. As of 2026-10-19 Sonnet 5.5
(`claude-sonnet-5-5`) is listed as the current Sonnet — verify against Anthropic's
models list. Any model change needs re-validation (see B4); golden `model_version`
is deliberately decoupled from `MODEL` (v1.7.1), so the goldens won't flag a swap.

**Plan:** after #8 (so the comparison is in dollars) and #9 (so the baseline is
green), run the real-document corpus on both models and compare golden pass rate,
block-count spread, `classification_unstable`, coverage warnings, and cost per
document. Adopt only on equal-or-better quality; otherwise record the result under
Rejected. Re-check default behaviours that can differ across versions (adaptive
thinking, `effort` semantics — see #1).

**Scope:** Medium — one paid corpus sweep per model; needs sign-off.

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
- **`strict: true`** — **partly reverted.** Shipped in v1.10.1 on the extraction +
  `set_block_relations` tools; v1.12.5 dropped it on extraction (strict +
  streaming stalls the richest schemas, `scientific_paper`/`contract`). It stays
  on the hierarchy tool. Extraction relies on the local jsonschema validation +
  retry loop for structure.
- **`output_config={"effort":"low"}`** (default is `high`) → less exploration,
  more scoped/consistent output for a mechanical task. Test hierarchy accuracy
  first — relational reasoning may want `medium`. **Shipped opt-in (v1.12.4)**
  as the `PDFSCOUT_EFFORT` env knob on all calls; default sends nothing (zero
  behavior change). Early A/B (n=3) halved block-count variance at equal
  quality; broader validation across the corpus still required before adopting
  `low` as a default.
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

**Status (2026-10-19):**

- Classifier thinking pinned off — shipped v1.8.0.
- `strict: true` — shipped v1.10.1, reverted on extraction in v1.12.5 (see above).
- `effort` — shipped as the opt-in `PDFSCOUT_EFFORT` knob (v1.12.4); the v1.12.6
  goldens were regenerated at `effort=low`.
- Block-count spread over N runs — recorded per golden (`raw_block_counts`);
  median 6.3% at `low` (v1.12.6).
- Completeness oracle (the symptom-level fix for silently dropped blocks) — shipped
  v1.9.0.

**Still open:** decide the effort default — adopt `low` explicitly only after a
corpus-wide A/B against the default (the paid sweep in #9 supplies it) — and whether
to add the "extract only what is present" prompt tightening.

**Scope:** Small — one paid verification run, shared with #9. The
checkpoint-cache and deterministic-sort guarantees (A) are already in place.

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

**Auto-retry shipped in v1.11.0:** the coverage auditor re-extracts up to
`COVERAGE_RETRY_MAX_PAGES` flagged pages once each and replaces a page's blocks
only when the retry scores better native coverage (never regresses; unscoreable
pages are not retried). For a duplicate pair, the page with the LOWER native
coverage is the one retried (that's the misattributed one). Verified via unit
tests incl. the real sp-5 failure shape; triggers naturally on live flagged runs.

**Remains open:** structural fix (send each worker a single-page PDF —
trade-off: loses the shared prompt-cache prefix); single dropped headings on
otherwise-covered pages (needs span/bbox-aware matching — v2 of the oracle).

### 11 · REST API hardening (review finding, 2026-10-19)

**What** (found by reading `api.py` / `src/api/`, not yet exercised — write a
failing test first for each):

- No authentication, rate limiting or CORS; every upload spawns N paid calls.
  Fine on localhost, unsafe if the API is ever exposed.
- `asyncio.create_task(run_extraction(...))` keeps no reference to the task; Python's
  docs warn such tasks can be garbage-collected mid-run. Hold them in a set and
  discard on completion.
- `jobs.init()` marks every queued or running job `failed` on restart, and a re-POST
  without `force` returns that failed record — so checkpoint resume (README:
  "Interrupted runs resume") appears reachable from the CLI only. Either resume
  interrupted jobs at startup or document that API resume is not supported.
- The PDF check trusts the client-declared `content-type`; add a `%PDF-` magic-byte
  check.

**Scope:** Small each. The one decision needed is the auth model (shared-secret
header vs none).

### 12 · Long-document cost and quality benchmark (review finding, 2026-10-19)

**What:** Every page worker re-sends the whole PDF (cached after the first call).
The docs list 600 pages as the API maximum (100 on 200k-context models), but the
test corpus caps at 5 pages, so cost and quality at 20–100 pages are unmeasured.
One suspected limit, from reading `hierarchy_node.py` (not tested): the single
hierarchy call's budget is `min(16000, max(4000, blocks × 40))`, so it stops scaling
at about 400 blocks, and — unlike the workers — it never checks
`stop_reason == "max_tokens"`. If a truncated forced tool call arrives with empty
input, as the worker code documents, every block would be promoted to root with one
warning each.

**Plan:** run one 20–50 page public document outside the 5-page corpus (one-off, not
a manifest slot) and report dollars per page, cache-hit rate, coverage warnings and
hierarchy behaviour above ~400 blocks. Add the missing truncation check regardless —
it is cheap.

**Scope:** Medium — one paid run; needs sign-off.

### 13 · Pipeable CLI output (review finding, 2026-10-19)

**What:** `main.py` prints `[GRAPH]` progress lines and the final JSON to the same
stdout stream, so the result cannot be piped without parsing around the progress
text, and there is no `--output` flag.

**Fix:** add `--output <file>` (opt-in, non-breaking) and send progress to stderr
only when it is used; making stdout JSON-only the default would change the CLI
contract (MAJOR under the release rules) — decide before doing it. Update the README
and `docs/01-getting-started/02-usage.md` examples in the same change.

**Scope:** Small.

### 14 · Dependency freshness (review finding, 2026-10-19)

**What:** On 2026-10-19 `uv pip list --outdated` reported newer versions of locked
dependencies — notably `anthropic` (0.116.0 locked, 1.15.0 listed), `langfuse`
(4.14.0 → 5.0.2) and `fastapi` (0.139.0 → 0.148.0). Re-check; the numbers are dated.
There is no Dependabot or Renovate config.

**Fix:** add `.github/dependabot.yml` (uv + github-actions ecosystems, weekly,
grouped) — the `ci` workflow now gates those PRs. Take the `anthropic` major bump
deliberately: the pipeline depends on the streaming and `output_config` surface, so
run the offline suite plus #9's sweep before merging it.

**Scope:** Small (config); Medium for the `anthropic` bump.

### 15 · Worker prompt/parse duplication (review finding, 2026-10-19)

**What:** `window_parser_node` and `burst_worker_node` (`src/nodes/worker_node.py`)
repeat the prompt construction and the tool-block / `blocks` parsing logic. Tech
debt only — no behavioural bug known.

**Fix:** extract shared helpers the next time the worker is touched for another
reason; don't refactor standalone (CLAUDE.md → surgical changes).

**Scope:** Small.

---

## Deferred

### D2 · PyPI publishing (removed dead workflow, 2026-07-13)

**What:** `.github/workflows/python-publish.yml` (an unedited GitHub template)
fired on every GitHub release and always failed: `pdfscout` does not exist on
PyPI and no trusted publisher is configured — its only nine runs ever (the
2026-07-13 release backfill) all failed with `invalid-publisher`. It lay
dormant before that because releases created by `release.yml` use the built-in
`GITHUB_TOKEN`, which never triggers other workflows. Removed in the same
commit as this entry.

**To revive:** decide whether PDFScout should be pip-installable; if yes,
create the PyPI project, configure trusted publishing (repo
`lucagattoni/PDFScout`, workflow `python-publish.yml`, environment `pypi`),
and restore the workflow from git history (`1603a19`).

### D1 · Raise `WORKER_MAX_TOKENS` above 16k for very dense pages (contingency)

**What:** `WORKER_MAX_TOKENS = 16000` (v1.7.2) covers the densest real pages
seen so far (~5.4k needed), but a page requiring more would truncate again —
reported as a truncation warning rather than a silent drop.

**Fix when triggered:** worker calls already stream (v1.12.3), so the long-request
timeout no longer caps the budget; raise `WORKER_MAX_TOKENS` toward the 64–128k
ceiling from the original analysis. Defer until a real document actually hits the
16k warning.

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
| CI gate (`ci.yml`): ruff, format check, `uv lock --check`, offline pytest | v1.12.7 | Runs on every branch push and pull request; closes the "no CI on tests" review finding (2026-10-19). Markdown lint stays local (`make lint-md`). |
| Real-document corpus refresh + goldens regenerated (was #6, Group R) | v1.12.6 | `sp-1..6` replaced with July-2026 arXiv papers (≤5 pp, verified with pypdf, post-cutoff); `bc-1` → Federal Register FERC scoping notice, `bc-3` → June FOMC statement; `bc-2`/`bc-4`/`inv-1..5` unchanged. 10 slots regenerated (3 runs, `effort=low`, 1-hour cache), 15/15 goldens committed. Median run-to-run block spread 6.3% (7/10 ≤8%; `sp-2`/`bc-1`/`bc-3` higher — the `min_blocks` 95%-of-observed-min clamp keeps all goldens non-flaky). Metadata consensus normalization (folded into v1.11.0) confirmed on `sp-1`. Drove the v1.12.2–v1.12.5 fixes. Remaining paid e2e pass → #9. Plans: `plans/20260603_1540-real-doc-test-corpus.md`, `plans/20260604_0739-real-doc-infrastructure.md`. |
| `PDFSCOUT_EFFORT` env knob | v1.12.4 | `output_config.effort` on every call; unset sends nothing. Early A/B (n=3) halved block-count variance at equal quality. Default decision → #1. |
| Hierarchical MkDocs documentation + GitHub Pages deploy | v1.12.0–v1.12.1 | Docs site auto-deployed from `main`; strict build as a PR check. |
| Coverage auto-retry of flagged pages | v1.11.0 | Auto-retry half of #7 (details there). |
| Strict tool use dropped on extraction (streaming hang fix) | v1.12.5 | Strict + streaming hangs scientific_paper/contract (grammar-ceiling stall, no 400 → fallback never fires); extraction tool now non-strict with local jsonschema validation. Hierarchy stays strict. Confirmed by live probe 2026-07-13. |
| Extraction/hierarchy streaming (APITimeoutError fix) | v1.12.3 | Worker + hierarchy calls stream via messages.stream()/get_final_message() instead of blocking create() at max_tokens=16000 — avoids the API long-request timeout that broke golden regen on dense pages. Found 2026-07-13. |
| Strict-schema "too complex" regression fix | v1.12.2 | Strict tool use (v1.10.1) broke `scientific_paper`/`contract` extraction — the API rejects their strict grammar with `400 "Schema is too complex."`. Worker now falls back to a non-strict tool on that error, memoized per doc type; `_call_api` no longer retries deterministic 4xx. Found via golden regen 2026-07-13. |
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
