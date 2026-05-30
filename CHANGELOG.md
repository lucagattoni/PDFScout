# Changelog

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
