# Langfuse Integration Plan
Date: 2026-05-30  
Revised: 2026-05-30 (devil's advocate review applied)

## Goal

Add end-to-end observability to PDFScout using Langfuse v4. Every pipeline run
should produce a single trace in Langfuse showing the full node execution tree,
every Claude API call with its inputs/outputs and token counts, and key metadata
(pdf_hash, document_type, page count) so runs are searchable and comparable.

Checkpoint resumes of the same PDF must merge into the same trace, not create
a new orphan trace per invocation.

---

## What Langfuse Gives Us

Langfuse integrates with LangGraph via LangChain's callback system. The
`CallbackHandler` is passed to each `graph.stream()` call through LangGraph's
standard `config={"callbacks": [...]}` parameter.

**Automatically traced with zero extra code:**
- The overall graph run → a single Langfuse **trace**
- Each LangGraph node → a **span** nested under the trace
- Every `client.messages.create()` call inside a node → a child **LLM span**
  with full input messages, output content, model name, and token counts
- Tool-use calls (the `extract_*_structure` and `set_block_relations` tools) →
  captured inside the LLM span

**Not automatic — requires manual enrichment:**
- Custom trace metadata (pdf_hash, document_type, total_pages, file path) — set
  via `start_as_current_span(update_attributes={...})` for values known upfront,
  and via `span.update(metadata={...})` post-run for values resolved by the graph
- Session ID tagging (`session_id=pdf_hash`) — enables filtering all runs for
  the same PDF in the Langfuse UI (no user_id concept in a CLI tool)
- Extraction warnings — joined as a newline string in post-run `span.update()`
  (Langfuse v4 coerces metadata values to `str`, max 200 chars; a raw list would
  be serialised as its `repr` which is unreadable)
- Deterministic trace ID for checkpoint resume merging

---

## Package

```
langfuse>=4.0.0   (latest: 4.7.1)
```

Import paths:
```python
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
```

> **Note:** Langfuse v4 requires Pydantic v2. Pydantic v2.13.4 is already a
> transitive dependency (via langgraph) — no conflict.

---

## Environment Variables

| Variable | Description |
|---|---|
| `LANGFUSE_PUBLIC_KEY` | Public key from Langfuse project settings (`pk-lf-...`) |
| `LANGFUSE_SECRET_KEY` | Secret key from Langfuse project settings (`sk-lf-...`) |
| `LANGFUSE_BASE_URL` | API host. Defaults to `https://cloud.langfuse.com`. Override for self-hosted. |

> **Important:** The canonical v4 variable is `LANGFUSE_BASE_URL`, not
> `LANGFUSE_HOST`. Both are accepted but `LANGFUSE_BASE_URL` is the primary name.

`CallbackHandler()` reads all three from the environment automatically when
keys are present.

---

## Architecture of a Trace

When PDFScout runs on a 5-page invoice (including a checkpoint resume):

```
Trace ID: uuid5(pdf_hash)  ← same ID on every invocation of this PDF
  ├─ Span: native_extractor_node
  ├─ Span: classifier_node
  │    └─ LLM: claude-sonnet-4-6  [classify prompt → "invoice"]
  ├─ Span: window_parser_node  (page 1 — pioneer)
  │    └─ LLM: claude-sonnet-4-6  [extract_invoice_structure tool]
  ├─ Span: retry_incrementor_node  (if page 1 failed validation)
  ├─ Span: window_parser_node  (page 2 — burst)
  │    └─ LLM: claude-sonnet-4-6
  ├─ Span: window_parser_node  (page 3)
  │    └─ LLM: claude-sonnet-4-6
  ...
  └─ Span: layout_hierarchy_agent_node
       └─ LLM: claude-sonnet-4-6  [set_block_relations tool]
```

If this is a resume run (e.g., interrupted at page 3), the new run's spans
appear under the same trace ID in Langfuse rather than a separate trace.
Token counts per LLM span reveal cache hits vs. cache misses (Anthropic returns
`cache_read_input_tokens` in the usage object; Langfuse captures it verbatim).

---

## File-level Changes

### 1. `pyproject.toml` — add dependency

```toml
"langfuse>=4.0.0",
```

### 2. `.env.example` — add new variables

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

### 3. `main.py` — full implementation

```python
import atexit
import os
import sys
import asyncio
import json
from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.graph import build_app
from src.utils.pdf_utils import hash_file

load_dotenv()

# Graceful degradation: tracing only activates when both keys are present.
# Absent keys → empty callbacks list → pipeline runs without any tracing.
_LANGFUSE_ENABLED = bool(
    os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
)

if _LANGFUSE_ENABLED:
    _langfuse = Langfuse()
    # Safety-net: flush on normal interpreter exit even if main() raises before
    # reaching its own shutdown() call (e.g. keyboard interrupt, unhandled exception).
    atexit.register(_langfuse.shutdown)


async def main():
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("CRITICAL ENVIRONMENT ERROR: ANTHROPIC_API_KEY environment variable missing.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("EXECUTION ERROR: Missing file path. Usage: uv run main.py <path_to_pdf>")
        sys.exit(1)

    target_pdf = sys.argv[1]
    pdf_hash = hash_file(target_pdf)

    # Derive a deterministic trace ID from the PDF hash so every invocation
    # of the same file — including checkpoint resumes — merges into one trace.
    trace_id = _langfuse.create_trace_id(seed=pdf_hash) if _LANGFUSE_ENABLED else None

    initial_inputs = {"file_path": target_pdf}
    print(f"Initializing extraction pipeline for: {target_pdf} (thread: {pdf_hash[:8]}...)")

    if _LANGFUSE_ENABLED:
        with _langfuse.start_as_current_span(
            name=f"PDFScout — {os.path.basename(target_pdf)}",
            trace_context={"trace_id": trace_id},
            update_attributes={
                "session_id": pdf_hash,
                "metadata": {
                    "file": os.path.basename(target_pdf),
                    "pdf_hash": pdf_hash,
                },
            },
        ) as span:
            callbacks = [CallbackHandler()]
            config = {"configurable": {"thread_id": pdf_hash}, "callbacks": callbacks}

            try:
                async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
                    app = build_app(checkpointer)
                    async for event in app.stream(initial_inputs, config):
                        for node_name in event:
                            print(f"[GRAPH] Node '{node_name}' completed.")
                    final_state = await app.get_state(config)
                    tree_result = final_state.values.get("hierarchical_document_tree")

                # Enrich trace with values resolved during the graph run.
                # Must happen inside the with block so the span is still open.
                # Langfuse v4 coerces metadata values to str (max 200 chars),
                # so lists are joined rather than passed raw.
                state_values = final_state.values if final_state else {}
                warnings = tree_result.get("extraction_warnings", []) if tree_result else []
                span.update(metadata={
                    "file": os.path.basename(target_pdf),
                    "pdf_hash": pdf_hash,
                    "document_type": tree_result.get("document_type") if tree_result else None,
                    "total_pages": str(state_values.get("total_pages", "")),
                    "extraction_warnings": "\n".join(warnings) if warnings else "",
                })
            finally:
                # flush() inside the with block guarantees child LLM spans are
                # queued before the parent span's end-time is recorded and sent.
                _langfuse.shutdown()
    else:
        config = {"configurable": {"thread_id": pdf_hash}}
        async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
            app = build_app(checkpointer)
            async for event in app.stream(initial_inputs, config):
                for node_name in event:
                    print(f"[GRAPH] Node '{node_name}' completed.")
            final_state = await app.get_state(config)
            tree_result = final_state.values.get("hierarchical_document_tree")

    if tree_result and tree_result.get("extraction_warnings"):
        print("\nWARNINGS:")
        for w in tree_result["extraction_warnings"]:
            print(f"  ! {w}")

    print("\nExtraction complete. Output tree:\n")
    print(json.dumps(tree_result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Design Decisions & Rationale

### flush() sequencing
`_langfuse.shutdown()` (stronger than `flush()` — it also joins background
ingestion threads) is called in two places:

1. In `try/finally` inside the `with start_as_current_span()` block — this is
   the primary call. Placing it **inside** the `with` block ensures all LLM
   child span payloads are queued before the parent span's end-time is committed.
   Calling it outside would create a race where the parent span arrives at
   Langfuse before its children.

2. Via `atexit.register(_langfuse.shutdown)` at module level — this is the
   last-resort backstop for unexpected exits (unhandled exceptions, KeyboardInterrupt)
   that bail out before reaching the `finally` clause. `atexit` fires on normal
   interpreter termination; it does NOT fire on SIGKILL or `os._exit()`.

### Deterministic trace ID for checkpoint resume
`_langfuse.create_trace_id(seed=pdf_hash)` generates a UUID5 from the PDF's
SHA-256 hash. The same hash always produces the same trace ID. When a run is
interrupted and resumed, both invocations write spans under the same trace ID
in Langfuse, giving a complete view of the full extraction across sessions
rather than two orphaned partial traces.

### Graceful degradation
Tracing is opt-in. If `LANGFUSE_PUBLIC_KEY` or `LANGFUSE_SECRET_KEY` are
absent from the environment, `_LANGFUSE_ENABLED` is `False` and the pipeline
runs exactly as before — no import error, no crash, no changed behaviour.

### Post-run metadata enrichment
`document_type`, `total_pages`, and `extraction_warnings` are only available
after the graph completes. All three are read from `final_state.values` and
`tree_result` inside the `with` block (before the span closes) and written via
`span.update(metadata={...})`.

`extraction_warnings` is joined with `"\n"` before storing — Langfuse v4
coerces metadata values to `str` with a 200-char cap. A raw list would be
serialised as its Python `repr`, which is not readable or filterable. The joined
string is truncated by the SDK if it exceeds 200 chars; for most documents the
warning list is short enough to fit.

`user_id` is not set — there is no user concept in a CLI tool. `session_id` is
set to `pdf_hash`, which groups all runs for the same PDF together in the
Langfuse UI.

---

## Known Limitations

### Burst worker span nesting (Langfuse bug #10721)
LangGraph's Send API spawns burst `parser_worker` tasks as concurrent asyncio
tasks. Python `contextvars` context is propagated to tasks created via
`asyncio.create_task()`, but LangGraph's internal task management for Send
nodes may or may not propagate the Langfuse span context. Bug #10721 confirms
that in some async LangGraph patterns, callback observations don't nest
correctly under an active parent span. **This is unresolved.** Worst case:
burst worker LLM spans appear as root-level observations in Langfuse rather
than nested under the correct node span. The overall trace is still complete
and searchable; only the nesting may be flat.

### atexit does not cover all exit paths
`atexit` fires on normal interpreter exit and `sys.exit()`. It does NOT fire on
SIGKILL, `os._exit()`, or Python fatal internal errors. For a CLI tool this is
acceptable. If PDFScout is ever embedded in a long-running service, replace the
`atexit` approach with an explicit `shutdown()` call in the service's teardown.

---

## Execution Order

1. `uv add "langfuse>=4.0.0"` — add dependency
2. Update `.env.example` — add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`
3. Replace `main.py` with the implementation above
4. Update `README.md` — add Observability section (see below)
5. Test locally: set keys, run against a real PDF, verify trace appears in Langfuse UI

---

## README Addition

Add a new **Observability** section between Installation and Usage:

```markdown
## Observability

PDFScout ships with optional [Langfuse](https://langfuse.com/) tracing. When
enabled, every pipeline run produces a single trace showing node execution,
Claude API calls, token usage (including prompt-cache hits), and extraction
metadata. Checkpoint resumes of the same PDF merge into the same trace.

To enable, add to your `.env`:

\`\`\`
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com   # omit to use cloud default
\`\`\`

Get keys from your [Langfuse project settings](https://cloud.langfuse.com).
If the keys are absent the pipeline runs normally with no tracing.
```
