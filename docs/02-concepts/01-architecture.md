# Architecture

[Documentation index](../index.md) · [Project overview](https://github.com/lucagattoni/PDFScout)

## How it works — plain language

PDFScout reads a PDF the way a person would: it first flips through to see what
kind of document it is (an invoice? a paper? a contract?), then reads page 1
carefully and checks its own work, then reads all the remaining pages at the
same time to go fast. When every page is done, it compares what it extracted
against the text embedded in the PDF file itself — if a page came back
incomplete, it re-reads that page. Finally it figures out how the pieces relate
(which paragraphs belong under which headings) and returns one structured tree.

Two engineering ideas make this cheap and reliable:

- **Read once, reuse everywhere.** The PDF is uploaded once and cached at the
  provider, so the 2nd…Nth page readers pay ~10% of the input cost.
- **Never trust a single pass.** Every page's output is validated against a
  schema and retried on failure, and an independent audit compares the result
  with the PDF's own text layer.

## The pipeline — technical view

The pipeline is a LangGraph state machine with two distinct execution phases — sequential for the pioneer page, concurrent for all remaining pages — joined by a map-reduce merge. The pioneer page runs first for two reasons: its call **primes the provider-side prompt cache** with the fully-processed PDF (so the concurrent burst that follows reads it at 0.1× input cost), and its schema-validation loop catches systematic formatting problems once, before N parallel workers repeat them.

```text
START
  └─► native_extractor          (local: pypdf page count + SHA-256 hash)
        └─► classifier           (Claude: returns document type token)
              └─► pioneer_parser (Claude: page 1, sequential — primes prompt cache)
                    ├─► [validation failure, retry_count < 3]
                    │     └─► retry_node ──► pioneer_parser
                    └─► [validation pass OR retry_count >= 3]
                          └─► burst_dispatcher
                                ├─► [single-page doc] ──► coverage_auditor
                                └─► [multi-page doc]
                                      Send("parser_worker", page=2)
                                      Send("parser_worker", page=3)
                                      ...
                                      Send("parser_worker", page=N)
                                        └─► (merge via merge_flat_blocks)
                                              └─► coverage_auditor
                                                    └─► hierarchy_node
                                                          └─► END
```

## Nodes

| Node | Responsibility |
|---|---|
| `native_extractor` | Counts pages with `pypdf`, guards against encrypted PDFs, and computes a chunked SHA-256 hash used as the LangGraph thread ID |
| `classifier` | Sends the full PDF to Claude via the native PDF Chat API and returns one of the supported document type tokens; falls back to `baseline_core` for unknown values |
| `pioneer_parser` | Sends page 1 as a `document` block to Claude via tool-calling; marks the document block with `cache_control: ephemeral` to establish the provider's prompt cache for all subsequent burst calls; appends doc-type-specific supplemental instructions (e.g. requests optional metadata subfields for `scientific_paper`) |
| `retry_node` | Re-runs `jsonschema` validation to capture the specific error, increments `retry_count`, and writes the error detail to state for the model's next attempt |
| `burst_dispatcher` | Emits one `Send("parser_worker", ...)` per remaining page using LangGraph's Send API; writes a degradation warning to state if pioneer validation exhausted its retries |
| `parser_worker` | Extracts pages 2–N concurrently under an `asyncio.Semaphore`; includes an inline validation-retry loop (up to 3 attempts) mirroring the pioneer's graph-level retry; degrades gracefully with a warning after 3 failed attempts |
| `coverage_auditor` | Completeness oracle: compares each page's extracted blocks against the PDF's native text layer, word-level and order-free; flags pages with dropped content or cross-page duplication (wrong-page extraction), then **re-extracts up to `COVERAGE_RETRY_MAX_PAGES` flagged pages once each**, keeping whichever block set scores better native coverage (never regresses). Self-disables on pages whose native layer is unusable (scans, subset-font encodings) and applies a lower threshold on figure pages |
| `hierarchy_node` | Deduplicates blocks by `block_id`, sorts by geometric reading order, then uses Claude tool-calling to assign `parent_id` relationships across the full flat block list |

## Agentic design — who does what

PDFScout is a small multi-agent system where each agent has one job and a
deterministic harness checks its work:

| Agent | Role | Pattern |
|---|---|---|
| `classifier` | Reads the whole PDF, emits **one token** (the document type) | Constrained decision agent — forced tool-free, tiny `max_tokens`, unknown values fall back to `baseline_core` |
| `pioneer_parser` / `parser_worker` | Extract one page each into typed blocks | Tool-calling extractors — the JSON Schema *is* the tool signature; output is validated locally against the full schema (not strict tool use, which stalls streaming on the richer schemas) |
| `coverage_auditor` | Compares each page's blocks against the PDF's native text layer | **Critic/oracle** — deterministic ground truth (no LLM), with bounded self-correction: up to `COVERAGE_RETRY_MAX_PAGES` flagged pages are re-extracted once, keeping whichever result covers more |
| `hierarchy_node` | Assigns parent–child relations across all blocks | Hybrid — a deterministic geometric pre-sorter establishes reading order; the model only judges semantic nesting |

The guiding principle: **deterministic where possible, model where necessary.**
Page counting, hashing, reading-order sorting, coverage scoring, and validation
are all plain code; the model is reserved for what code can't do (visual
structure recognition, semantic classification). Every model output passes
through a code-level gate (schema validation, coverage audit) before it is
trusted.

## LangGraph mechanics

How each LangGraph feature is used, and why:

- **`StateGraph` over a `TypedDict` state** (`PDFParserState`). Every node is a
  pure-ish function `state → partial update`; LangGraph merges updates into the
  shared state. Nothing is passed between agents except through this state.
- **Custom reducers for concurrent writes.** Fields written by parallel
  branches are declared with `Annotated[..., reducer]`: `extracted_flat_blocks`
  uses `merge_flat_blocks`, warnings and per-call usage entries append via
  their own reducers. Reducers make the fan-in deterministic — N workers can
  finish in any order and the merged state is the same.
- **Sentinel contracts inside reducers.** Two subtleties live here: passing
  `None` resets a channel (used so a fresh run on a checkpointed thread doesn't
  double-count usage from the previous run), and a `__replace_pages__` marker
  lets the coverage auditor surgically replace all blocks of specific pages —
  needed because a plain append-reducer could otherwise only ever add blocks.
- **Map-reduce fan-out with the Send API.** `dispatch_pages` is a conditional
  edge that returns `[Send("parser_worker", {...page 2}), Send(..., page 3), …]`
  — one branch per remaining page, created dynamically at runtime (the page
  count isn't known when the graph is compiled). Single-page documents return a
  node name instead, skipping the burst entirely. Concurrency *within* the
  fan-out is additionally bounded by an `asyncio.Semaphore`
  (`CONCURRENCY_LIMIT`) to respect API rate limits.
- **A cycle for self-healing.** `pioneer_parser → pioneer_validation_route`
  is a conditional edge that loops back through `retry_node` on schema
  failure (max 3 times) and proceeds to `burst_dispatcher` on success or
  exhaustion. The retry is a *graph* cycle, not a hidden loop inside a node, so
  every attempt is checkpointed and observable.
- **Checkpointing = resumability.** The graph is compiled with an
  `AsyncSqliteSaver`; the thread ID is the PDF's SHA-256 hash. State persists
  after every node, so re-running an interrupted extraction resumes from the
  last completed node instead of paying for the whole document again (see
  [usage](../01-getting-started/02-usage.md#checkpoint-resumption)).

## Self-Healing Loop (Pioneer Page)

Page 1 is special: it runs sequentially before the burst phase and its output is validated against the schema. If validation fails, the `retry_node` captures the exact `jsonschema.ValidationError` path and message and feeds it back to the model as a structured error prompt. This loop runs up to 3 times before the pipeline degrades gracefully — page 1's partial output is included as-is, a warning is appended to `extraction_warnings`, and the burst phase continues normally.

Pages 2–N use `burst_worker_node`, which retries inline up to 3 times on schema validation failure before degrading gracefully. Transient HTTP errors (429/529) are handled separately by `tenacity`'s `@retry` decorator at the API call site.

## Reading order — the geometric pre-sorter's logic

Before the hierarchy agent sees any block, a deterministic pre-sorter
establishes reading order. The algorithm, and the reasoning behind each step:

1. **Split the page into horizontal bands** at every block spanning at least
   `BAND_FULL_WIDTH_FRAC` (0.55) of the page's x-span. Logic: a full-width
   element (a table, a banner, a totals row) is a visual separator — a reader
   never reads *around* it, so nothing below it may sort before it.
2. **Within each band, sort column-major**: bucket blocks into columns by
   x-position (`COLUMN_BUCKET_FRAC` = 0.11 of the x-span), read each column
   top-to-bottom, columns left-to-right. Logic: within a band, multi-column
   text is read one column at a time.
3. **Pull headings down**: a heading/title whose bottom edge lies within
   `BAND_PULLDOWN_GAP_FRAC` (0.05) of the x-span above a full-width block
   joins that block's band. Logic: a heading introduces what follows it — a
   band boundary must not strand it above its own content. The pull-down is
   restricted to heading/title block types so body text is never re-ordered.

Every threshold is a **fraction of the page's x-span, never an absolute
value** — the model emits coordinate spans anywhere from 855 to 1125 units for
the same A4 page, so absolute thresholds would silently break between runs.
This single band+column pass yields natural top-to-bottom order for invoices
and forms while keeping two-column papers grouped by column.

## The coverage oracle's logic

The auditor needs ground truth that doesn't come from a model. It uses the
PDF's own embedded text layer, with defenses against the ways that layer lies:

- **Word-level and order-free.** It checks *which* significant words (≥5
  alphabetic characters, Unicode-normalized, hyphenation-canonicalized) from
  the native layer appear anywhere in the extracted blocks — not their order.
  Logic: extraction may legitimately reflow, reorder, and summarize; what it
  must never do is silently *drop content*.
- **Self-disabling on unusable layers.** Scanned pages have no text layer;
  subset-font PDFs decode to symbol soup. A character-class gate
  (`COVERAGE_CHAR_CLASS_MIN` = 0.85) plus minimum-size gates detect both, and
  the oracle skips those pages rather than emit false alarms.
- **Figure damping.** Pages containing figure blocks use a lower warn
  threshold (0.25 vs 0.5): figures are summarized by design, so their caption
  and axis text won't appear verbatim.
- **Cross-page duplication detection.** If most of a page's substantial blocks
  duplicate exactly **one** other page, a worker almost certainly extracted
  the wrong page — a real failure mode near page boundaries. The
  single-dominant-page rule separates this from legitimately repeated content
  (headers, footers), which spreads across *many* pages.
- **Bounded, never-regressing self-repair.** Flagged pages are re-extracted at
  most once each, capped at `COVERAGE_RETRY_MAX_PAGES` per run (cost control);
  the new result is kept only if it scores better coverage. For a duplicated
  pair, the *lower-coverage* page is retried — that's the likelier
  mis-extraction.

## Prompt Caching

Every page extraction call sends the PDF as a `document` block with `cache_control: {"type": "ephemeral"}`. The pioneer call establishes this block in Anthropic's prompt cache — caching Claude's fully-processed representation of the PDF (image + text per page). All subsequent burst calls hit the warm cache, achieving a >90% cache-hit rate on input tokens across multi-page documents.

> **Note:** The default prompt-cache TTL is 5 minutes — burst pages dispatched after this window pay full input token cost. For multi-run workloads over the same document, set `PDFSCOUT_CACHE_TTL=1h` (2× write cost paid once, then every run reads the PDF prefix at 0.1×). See [configuration](../03-reference/01-configuration.md).

## Project Structure

```text
PDFScout/
├── main.py                     # CLI entry point (loads .env via python-dotenv)
├── api.py                      # FastAPI app — see docs/reference/api.md
├── Makefile                    # install, lint, fix, test, coverage, ci, clean
├── pyproject.toml / uv.lock    # uv-managed dependencies + ruff and pytest configuration
├── schemas/                    # JSON Schema Draft-07 blueprints (+ README.md authoring guide)
├── docs/                       # architecture, output format, configuration, testing, design notes
├── plans/                      # dated implementation plans
├── scripts/                    # real-doc corpus tooling: download, golden generation, evaluation
├── src/
│   ├── config.py               # centralized tunables — see docs/03-reference/01-configuration.md
│   ├── state.py                # PDFParserState TypedDict + merge reducers
│   ├── schema_registry.py      # jsonschema loader, validator, and strict tool builder
│   ├── edges.py                # pioneer validation routing
│   ├── graph.py                # LangGraph graph, Send API dispatch, build_app() factory
│   ├── api/                    # FastAPI runner, job store, response models
│   ├── extractors/             # pypdf page counter + encrypted-PDF guard
│   ├── utils/                  # PDF hashing/encoding, usage accounting, Langfuse tracing
│   └── nodes/                  # extractor, classifier, worker, retry, coverage, hierarchy
└── tests/
    ├── unit/                   # reducers, registry, edges, utils, graph topology, every node
    ├── integration/            # API endpoints, graph pipeline, synthetic e2e groups A–I, Group R
    └── fixtures/               # synthetic generators + goldens; real-doc manifest + goldens
```
