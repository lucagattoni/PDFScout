# Langfuse Integration Plan
Date: 2026-05-30

## Goal

Add end-to-end observability to PDFScout using Langfuse v4. Every pipeline run
should produce a single trace in Langfuse showing the full node execution tree,
every Claude API call with its inputs/outputs and token counts, and key metadata
(pdf_hash, document_type, page count) so runs are searchable and comparable.

---

## What Langfuse Gives Us

Langfuse integrates with LangGraph via LangChain's callback system. The
`CallbackHandler` is passed to each `graph.stream()` / `graph.astream()` call
through LangGraph's standard `config={"callbacks": [...]}` parameter.

**Automatically traced with zero extra code:**
- The overall graph run → a single Langfuse **trace**
- Each LangGraph node → a **span** nested under the trace
- Every `client.messages.create()` call inside a node → a child **LLM span**
  with full input messages, output content, model name, and token counts
- Tool-use calls (the `extract_*_structure` and `set_block_relations` tools) →
  captured inside the LLM span

**Not automatic — requires manual enrichment:**
- Custom trace metadata (pdf_hash, document_type, total_pages, file path)
- User ID / session ID tagging for filtering
- Extraction warnings surfaced as span metadata

---

## Package

```
langfuse==4.x   (latest: 4.7.1)
```

Import path for the callback handler:
```python
from langfuse.langchain import CallbackHandler
```

> **Note:** Langfuse v4 requires Pydantic v2. It will be pulled in as a
> transitive dependency — no conflict with our current deps since we removed
> Pydantic from direct dependencies in the Claude PDF Chat migration.

---

## Environment Variables

Three new variables must be added to `.env` and `.env.example`:

| Variable | Description |
|---|---|
| `LANGFUSE_PUBLIC_KEY` | Public key from the Langfuse project settings (`pk-lf-...`) |
| `LANGFUSE_SECRET_KEY` | Secret key from the Langfuse project settings (`sk-lf-...`) |
| `LANGFUSE_HOST` | API host. Defaults to `https://cloud.langfuse.com`. Override for self-hosted deployments. |

`CallbackHandler()` reads all three from the environment automatically — no
constructor arguments needed for the default cloud setup.

---

## Architecture of a Trace

When PDFScout runs on a 5-page invoice:

```
Trace: "PDFScout — invoice — a3f1c9..."
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

Token counts per LLM span show cache hits vs. cache misses directly (Anthropic
returns `cache_read_input_tokens` in usage; Langfuse captures the full usage
object).

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
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 3. `main.py` — create handler, enrich trace, flush after run

This is the only file that changes in the application code.

```python
from langfuse.langchain import CallbackHandler

async def main():
    ...
    pdf_hash = hash_file(target_pdf)

    # Create one handler per pipeline run so each PDF gets its own trace
    langfuse_handler = CallbackHandler()

    config = {
        "configurable": {"thread_id": pdf_hash},
        "callbacks": [langfuse_handler],
    }

    async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
        app = build_app(checkpointer)
        async for event in app.stream(initial_inputs, config):
            for node_name in event:
                print(f"[GRAPH] Node '{node_name}' completed.")

        final_state = await app.get_state(config)
        tree_result = final_state.values.get("hierarchical_document_tree")

    # Flush before exit — LangGraph's astream is async but CallbackHandler
    # batches sends in a background thread; flush() blocks until the queue drains
    langfuse_handler.flush()
    ...
```

**Trace metadata enrichment** (set after classifier resolves document_type):

Langfuse v4 removed `update_trace` from `CallbackHandler`. The v4 way to attach
metadata to the enclosing trace is to wrap the graph run in a
`langfuse.start_as_current_span()` context and call `span.update_trace()` on it:

```python
from langfuse import Langfuse

langfuse = Langfuse()

with langfuse.start_as_current_span(
    name=f"PDFScout — {os.path.basename(target_pdf)}",
    update_attributes={
        "session_id": pdf_hash,
        "metadata": {
            "file": os.path.basename(target_pdf),
            "pdf_hash": pdf_hash,
        }
    }
):
    langfuse_handler = CallbackHandler()
    config = {
        "configurable": {"thread_id": pdf_hash},
        "callbacks": [langfuse_handler],
    }
    async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
        app = build_app(checkpointer)
        async for event in app.stream(initial_inputs, config):
            for node_name in event:
                print(f"[GRAPH] Node '{node_name}' completed.")
        final_state = await app.get_state(config)
        tree_result = final_state.values.get("hierarchical_document_tree")

langfuse_handler.flush()
```

---

## Known Limitations & Gotchas

### Async blocking
Langfuse does not implement `AsyncCallbackHandler`. The standard `CallbackHandler`
dispatches its HTTP sends on a background thread, so the async event loop is not
blocked. However, within-callback synchronous work (serialising observation
payloads) runs inline. For PDFScout's workload (≤600 pages, no latency SLA)
this is not a concern.

### flush() is mandatory before process exit
The SDK batches observations and flushes on a timer. Without an explicit
`langfuse_handler.flush()` after the graph run completes, the last batch may
never be sent if the process exits before the timer fires. **Always call flush
before `asyncio.run()` returns.**

### Checkpoint resume creates a new trace
LangGraph's SQLite checkpointer lets a run resume mid-graph. Each `main.py`
invocation — including resumes — creates a new `CallbackHandler` and therefore
a new trace. If a document takes two runs to complete (e.g. interrupted on page
4), there will be two partial traces for the same `pdf_hash`. This is an
intentional trade-off; filtering by `session_id=pdf_hash` in Langfuse groups
them. A future improvement could use `langfuse.start_as_current_span()` with an
explicit `trace_id` derived from `pdf_hash` to merge them.

### No async span nesting (known Langfuse bug #10721)
In some async LangGraph patterns, `CallbackHandler` observations don't nest
correctly under an active parent span. For PDFScout this is low-risk because
we're adding the `start_as_current_span` wrapper ourselves; child spans from
the graph should still nest under it.

---

## Execution Order

1. `uv add "langfuse>=4.0.0"` — add dependency
2. Update `.env.example` — add the three `LANGFUSE_*` variables
3. Update `main.py` — import `Langfuse` and `CallbackHandler`; wrap `app.stream`
   in `start_as_current_span`; pass `callbacks` in `config`; call `flush()`
4. Update `README.md` — add Langfuse to the observability section under
   Installation (copy keys, set env vars)
5. Test locally with a real PDF and verify the trace appears in the Langfuse UI

---

## README Addition

Add a new **Observability** section between Installation and Usage:

```markdown
## Observability

PDFScout ships with [Langfuse](https://langfuse.com/) tracing. Every pipeline
run produces a trace showing node execution, Claude API calls, token usage
(including prompt-cache hits), and extraction metadata.

To enable it, add the following to your `.env`:

\`\`\`
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com   # omit for cloud default
\`\`\`

Get keys from your [Langfuse project settings](https://cloud.langfuse.com).
Tracing is skipped gracefully if the keys are absent.
```
