# Langfuse Integration Plan
Date: 2026-05-30  
Revised: 2026-05-30 (three rounds of devil's advocate review applied)

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

| What | How | When |
|---|---|---|
| `session_id = pdf_hash` | `update_attributes={"session_id": pdf_hash}` on the opening span — confirmed top-level Langfuse field, enables grouping all runs for the same file in the UI | Before graph runs |
| `file`, `pdf_hash`, `document_type`, `total_pages` | `span.update(metadata={...})` — `update_attributes` only accepts top-level fields; arbitrary key/value pairs belong in `metadata` | After graph completes, inside `with` block |
| `extraction_warnings` | `"\n".join(extraction_warnings)` in the same `span.update()` — Langfuse v4 coerces metadata values to `str` (max 200 chars); a raw list serialises as `repr` which is neither readable nor filterable | After graph completes, inside `with` block |
| Deterministic trace ID | `_langfuse.create_trace_id(seed=pdf_hash)` → `trace_context={"trace_id": trace_id}` — same PDF hash always yields the same UUID so checkpoint resume spans merge into the existing trace | Before graph runs |

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
# Absent keys → pipeline runs unchanged, no import error, no crash.
_LANGFUSE_ENABLED = bool(
    os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
)
_langfuse = Langfuse() if _LANGFUSE_ENABLED else None


async def main():
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("CRITICAL ENVIRONMENT ERROR: ANTHROPIC_API_KEY environment variable missing.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("EXECUTION ERROR: Missing file path. Usage: uv run main.py <path_to_pdf>")
        sys.exit(1)

    target_pdf = sys.argv[1]
    pdf_hash = hash_file(target_pdf)
    print(f"Initializing extraction pipeline for: {target_pdf} (thread: {pdf_hash[:8]}...)")

    # Conditionally inject the Langfuse callback — single graph execution path.
    callbacks = [CallbackHandler()] if _LANGFUSE_ENABLED else []
    config = {"configurable": {"thread_id": pdf_hash}}
    if callbacks:
        config["callbacks"] = callbacks

    if _LANGFUSE_ENABLED:
        # Deterministic trace ID: same PDF → same ID on every run, so checkpoint
        # resumes merge into the existing trace rather than creating a new one.
        trace_id = _langfuse.create_trace_id(seed=pdf_hash)
        try:
            with _langfuse.start_as_current_span(
                name=f"PDFScout — {os.path.basename(target_pdf)}",
                trace_context={"trace_id": trace_id},
                update_attributes={"session_id": pdf_hash},
            ) as span:
                async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
                    app = build_app(checkpointer)
                    async for event in app.stream({"file_path": target_pdf}, config):
                        for node_name in event:
                            print(f"[GRAPH] Node '{node_name}' completed.")
                    final_state = await app.get_state(config)

                # Post-run metadata enrichment — all fields go here, including
                # those known upfront (file, pdf_hash). update_attributes only
                # accepts confirmed top-level span fields (session_id, user_id,
                # tags); passing a nested "metadata" dict there is unverified.
                # Langfuse v4 coerces metadata values to str (max 200 chars);
                # use "\n".join() for lists rather than passing them raw.
                state_values = final_state.values if final_state else {}
                tree_result = state_values.get("hierarchical_document_tree")
                extraction_warnings = (
                    tree_result.get("extraction_warnings", []) if tree_result else []
                )
                span.update(metadata={
                    "file": os.path.basename(target_pdf),
                    "pdf_hash": pdf_hash,
                    "document_type": tree_result.get("document_type") if tree_result else "",
                    "total_pages": str(state_values.get("total_pages", "")),
                    "extraction_warnings": "\n".join(extraction_warnings),
                })
            # ← with __exit__ fires here: span end-time is recorded and ENQUEUED
        finally:
            # shutdown() runs AFTER with __exit__, so the parent span end-event
            # is already in the queue and gets sent along with child spans.
            # Guard against None in case Langfuse() construction failed mid-way.
            # No manual atexit: SDK registers its own; a second one risks a
            # double-shutdown hang (confirmed bug #6515).
            if _langfuse:
                _langfuse.shutdown()
    else:
        async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
            app = build_app(checkpointer)
            async for event in app.stream({"file_path": target_pdf}, config):
                for node_name in event:
                    print(f"[GRAPH] Node '{node_name}' completed.")
            final_state = await app.get_state(config)
        tree_result = final_state.values.get("hierarchical_document_tree") if final_state else None

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

### shutdown() sequencing — why try/finally wraps the with block, not vice versa

`_langfuse.shutdown()` must be called **after** the `with start_as_current_span()`
block exits, not inside it. The reason:

1. Code runs inside the `with` block, including `span.update()` for post-run
   metadata enrichment.
2. `with __exit__` fires when the block closes — this records the parent span's
   end-time and **enqueues** it into the background flush queue.
3. `shutdown()` in the `finally` clause drains the queue — the parent span
   end-event is already there and gets sent along with all child LLM spans.

If `shutdown()` were placed **inside** the `with` block (before `__exit__`), it
would kill the background thread before `__exit__` had a chance to enqueue the
parent span end-event — the root span would appear open/missing in Langfuse.

**No manual `atexit` is registered.** The Langfuse SDK automatically registers
its own `atexit` hook at import time. Adding a second `atexit.register` risks
calling `shutdown()` twice: once from `finally` and once from `atexit`.
Calling `shutdown()` twice can cause a hang on `ThreadPoolExecutor` teardown
(confirmed in Langfuse bug #6515). The SDK's built-in `atexit` provides the
backstop for unexpected exits; `try/finally` covers the primary path (normal
exit, exceptions, `KeyboardInterrupt`).

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

### Custom trace metadata — all in one span.update() call

All custom metadata is written via a single `span.update(metadata={...})` call
inside the `with` block, after the graph completes but before `__exit__` fires.
This includes fields known upfront (`file`, `pdf_hash`) as well as fields
resolved by the graph (`document_type`, `total_pages`, `extraction_warnings`).

`update_attributes` (the opening span parameter) only accepts confirmed top-level
Langfuse span fields: `session_id`, `user_id`, `tags`, `input`, `output`. Passing
a nested `"metadata"` dict inside `update_attributes` is **not a documented API
shape** and may be silently ignored or raise a `TypeError`. Keeping all metadata
in `span.update()` is the safe, verified approach.

`extraction_warnings` is joined with `"\n"` — Langfuse v4 coerces all metadata
values to `str` with a 200-char cap. A raw list serialises as its Python `repr`
(`"['...', '...']"`), which is neither readable nor filterable. The joined string
is the correct form; the full warning list is also printed to stdout by the
existing warnings block, so nothing is lost if the string is truncated.

`user_id` is not set — there is no user concept in a CLI tool. `session_id` is
set to `pdf_hash`, grouping all runs for the same file in the Langfuse UI.

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

### Unrecoverable exits lose the last batch
Neither `try/finally` nor the SDK's built-in `atexit` fires on SIGKILL or
`os._exit()`. Observations buffered in the flush queue at that moment are lost.
For a CLI tool this is acceptable — the only way to hit SIGKILL is an external
`kill -9`, which is an operator action. If PDFScout is ever embedded in a
long-running service, the service's graceful-shutdown handler should call
`_langfuse.shutdown()` explicitly on SIGTERM.

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
