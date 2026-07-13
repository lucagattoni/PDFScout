# Configuration

[Documentation index](../index.md) · [Project overview](https://github.com/lucagattoni/PDFScout)

All tunable constants live in `src/config.py`. Every geometric threshold is
expressed as a **fraction of the page's x-span**, never an absolute value —
the model emits coordinate spans of 855–1125 units for the same A4 page, so
absolute thresholds would silently break between runs.

## Model & concurrency

```python
MODEL = "claude-sonnet-5"
CONCURRENCY_LIMIT = 3               # Max concurrent Anthropic API calls during burst phase
SUPPORTED_DOC_TYPES = {"invoice", "scientific_paper", "contract"}
FALLBACK_DOC_TYPE = "baseline_core"
```

`CONCURRENCY_LIMIT` caps the `asyncio.Semaphore` on parallel `parser_worker`
calls. Increase it for faster processing on large documents; decrease it if
hitting TPM rate limits.

## Token budgets

```python
CLASSIFIER_MAX_TOKENS = 10          # Single-token classification response
WORKER_MAX_TOKENS = 16000           # Page extraction budget (dense pages exceed 4000 and truncate)
HIERARCHY_MAX_TOKENS_BASE = 4000    # Minimum hierarchy-agent budget
HIERARCHY_MAX_TOKENS_CEIL = 16000   # Maximum hierarchy-agent budget
HIERARCHY_TOKENS_PER_BLOCK = 40     # Estimated tokens per block for dynamic scaling
```

The hierarchy budget is `HIERARCHY_TOKENS_PER_BLOCK × block count`, clamped
between base and ceiling. The worker budget is deliberately large: when a
forced tool call is truncated by `max_tokens`, the API discards the partial
JSON and the page silently comes back empty — the pipeline detects
`stop_reason == "max_tokens"` and fails loudly instead.

## Reading order (geometric pre-sorter)

```python
COLUMN_BUCKET_FRAC = 0.11           # Column bucket width for column-major sort
BAND_FULL_WIDTH_FRAC = 0.55         # Min width for a block to start a reading-order band
BAND_PULLDOWN_GAP_FRAC = 0.05       # Max gap for a heading to join the band below it
```

The logic behind each knob is explained in
[architecture → reading order](../02-concepts/01-architecture.md#reading-order-the-geometric-pre-sorters-logic).
Raise `BAND_FULL_WIDTH_FRAC` to treat fewer blocks as band-splitters; raise
`COLUMN_BUCKET_FRAC` to merge narrow columns.

## Validation & retries

```python
VALIDATION_MAX_RETRIES = 3          # Schema-validation retries (pioneer graph-level + burst inline)
HTTP_MAX_RETRIES = 3                # Tenacity retries on transient HTTP errors (429/529)
RETRY_BACKOFF_MULTIPLIER = 1        # Exponential backoff multiplier (seconds)
RETRY_BACKOFF_MIN_SECONDS = 1
RETRY_BACKOFF_MAX_SECONDS = 10
EXTRACTION_NOTE_MAX_LENGTH = 200    # Max chars for extraction_note (injected into schemas)
```

Schema-validation retries (the model produced structurally wrong data) and
HTTP retries (the API was transiently unavailable) are separate mechanisms
with separate budgets — a page can consume both.

## Coverage oracle

```python
COVERAGE_MIN_NATIVE_CHARS = 80      # Below this, a page's native layer is too thin to audit
COVERAGE_CHAR_CLASS_MIN = 0.85      # Min fraction of standard chars for a usable native layer
COVERAGE_MIN_WORDS = 10             # Min significant native words for a page to be auditable
COVERAGE_WARN_THRESHOLD = 0.5       # Warn below this fraction of native-word coverage
COVERAGE_WARN_THRESHOLD_FIGURE = 0.25  # Lower bar on pages containing figure blocks
COVERAGE_RETRY_MAX_PAGES = 2        # Cost cap: max flagged pages re-extracted per run
CROSS_PAGE_DUP_MIN_CHARS = 20       # Min normalized text length to count in duplication checks
CROSS_PAGE_DUP_MIN_BLOCKS = 4       # Min substantial blocks for a meaningful duplication ratio
CROSS_PAGE_DUP_RATIO = 0.5          # Warn when this fraction of a page duplicates one other page
```

Why each gate exists:
[architecture → coverage oracle](../02-concepts/01-architecture.md#the-coverage-oracles-logic).

## Environment variables

| Variable | Values | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | API authentication |
| `PDFSCOUT_CACHE_TTL` | `1h` (default: 5-minute TTL) | Prompt-cache lifetime. The 1-hour TTL costs 2× on the first cache write but lets every subsequent run read the PDF prefix at 0.1× — worth it for multi-run workloads over the same document (golden regeneration, variance measurement). The regeneration script sets it automatically. |
| `PDFSCOUT_LOG_USAGE` | `1` / `true` / `yes` | Print a per-API-call `[USAGE]` line to stderr (cache write/read, input/output tokens, stop reason). Every run also prints an aggregate `USAGE:` summary at the end regardless. |
| `PDFSCOUT_EFFORT` | `low` / `medium` / `high` / `xhigh` / `max` (unset = model default) | Sets `output_config.effort` on every extraction, classifier, and hierarchy call. Unset sends nothing — zero behavior change. Lower effort trades exploration for consistency and fewer tokens on the mechanical extraction task; an early A/B (n=3) showed `low` roughly halved block-count variance at equal quality, but it is **opt-in only** pending broader validation before ever becoming a default. |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` | optional | Enable Langfuse tracing — see [installation](../01-getting-started/01-installation.md#optional-langfuse-tracing) |

Failed validation attempts that later succeed are printed as `[RETRY]` lines
to stderr with the discarded error, so paid retry causes are never silent.

## Observability

With Langfuse configured, every pipeline run produces one trace showing node
execution, Claude API calls, token usage (including prompt-cache hits), and
extraction metadata; aggregate usage totals are attached to the trace
metadata. All runs for the same PDF share a `session_id` (the PDF hash), so
they group in the Langfuse Sessions view.

## Limitations

- **Encrypted PDFs:** password-protected PDFs are not supported by Claude PDF
  Chat. `pypdf` detects encryption at startup and raises a `ValueError`
  before any API call is made.
- **Max request size:** the Anthropic API limit is 32 MB per request. PDFs
  approaching this should use the Files API (upload once, reference by
  `file_id`) rather than per-call base64 encoding.
- **Max pages:** 600 pages per request (100 for 200k-context models). Very
  large documents should be split before processing.
- **Cache TTL:** default 5 minutes; burst pages dispatched after the window
  pay full input cost. Switchable to 1 hour via `PDFSCOUT_CACHE_TTL=1h`.
- **Hierarchy accuracy:** cross-page `is_continued` linkages and complex
  multi-column layouts may produce imperfect parent-child assignments.
