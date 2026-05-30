# FastAPI Interface Plan
_Created: 2026-05-30 21:12_

## Goal

Expose the PDFScout LangGraph pipeline as an HTTP API so the project can be
tested without the CLI. "Basic" scope: file upload, async job tracking via
polling, and the same optional Langfuse tracing — no auth, no database, no
Redis, no SSE.

---

## Design decisions

### 1. Execution model — job-based async with polling

A PDF extraction takes seconds to minutes depending on page count. A synchronous
`POST /extract → wait → JSON` would hold the HTTP connection open for the full
duration and fail on proxy timeouts.

Chosen approach:
- `POST /extract` accepts the PDF and returns a `job_id` immediately.
- The pipeline runs as a background `asyncio` task.
- `GET /jobs/{job_id}` polls status (`queued | running | completed | failed`).
- `GET /jobs/{job_id}/result` returns the tree on completion.

**Alternative considered — SSE streaming**: Would surface per-node events in real
time (closer to CLI `[GRAPH] Node '...' completed.` output) but complicates the
client. Excluded from "basic" scope; the node event log is stored in the job
record so it can be retrieved after completion.

### 2. Job ID = pdf_hash

The LangGraph checkpointer uses `thread_id = pdf_hash`. Making `job_id =
pdf_hash` has two consequences:

- **Idempotency**: submitting the same PDF a second time returns the existing
  `job_id` and, if the first run completed, the existing result.
- **Checkpoint resume**: if a run was interrupted (server restart, etc.), the
  second submission resumes from the last checkpoint automatically — same
  behaviour as the CLI.

Collision risk is negligible (SHA-256, files not adversarially chosen).

### 3. Shared resources via FastAPI lifespan

The LangGraph app and the SQLite checkpointer are both expensive to initialise.
They are created once in the FastAPI `lifespan` context manager and stored in
app state, then reused by every request.

```
lifespan startup:
  open AsyncSqliteSaver  →  app.state.checkpointer
  build_app(checkpointer) →  app.state.graph
  Langfuse()              →  app.state.langfuse  (if keys present)

lifespan shutdown:
  langfuse.shutdown()   (flushes trace queue — only once, not per-request)
  # AsyncSqliteSaver closes automatically via async context manager __aexit__
```

**Why not open per-request**: `AsyncSqliteSaver.from_conn_string(...)` is an
async context manager that opens the SQLite connection and runs WAL-mode setup.
Opening it for every request adds ~10 ms overhead and risks write contention
between concurrent requests.

### 4. Langfuse lifecycle change from `main.py`

`main.py` calls `langfuse.shutdown()` in the `finally` block of each run.
In a long-running server this would kill the background flush thread after the
first request. The API moves `shutdown()` to the lifespan cleanup so it fires
exactly once — at process exit — after all spans are enqueued.

Each extraction still opens a span and calls `span.update()` post-run, but
without the per-run `shutdown()`.

### 5. Temp file handling

Uploaded PDFs are written to `tmp/uploads/{pdf_hash}.pdf`. The path is passed
to the pipeline as `state["file_path"]`. The background task deletes the file in
a `finally` block after the pipeline finishes or raises.

Using the pdf_hash as the filename means two concurrent uploads of the same PDF
write to the same path — safe because the content is identical (hash match).
The second upload's write is effectively a no-op.

Temp directory is created at startup if absent (`tmp/uploads/` relative to CWD).

### 6. In-memory job store

A module-level `dict[str, JobRecord]` is the job store. No persistence across
restarts; acceptable for a "basic testing" interface.

```python
@dataclass
class JobRecord:
    job_id: str
    file_name: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    completed_at: datetime | None
    total_pages: int | None
    document_type: str | None
    warnings: list[str]
    error: str | None
    result: dict | None
    events: list[str]        # "[GRAPH] Node 'X' completed." lines
```

Access is from a single `asyncio` event loop (FastAPI's), so a plain `dict` is
safe without locks.

### 7. Duplicate-run guard

If a job for `job_id` already exists and is `running`, the `POST /extract`
endpoint returns `202 Accepted` with the existing job record rather than
starting a second pipeline invocation for the same PDF. If the prior run
`completed` or `failed`, the client may pass `?force=true` to clear the
old record and re-run (useful for testing after schema changes).

### 8. File-size guard

The Anthropic API rejects requests larger than 32 MB. The API checks the upload
size before saving to disk and returns `413 Content Too Large` immediately.

### 9. No authentication

Out of scope for a basic testing interface. Add an API key middleware layer
(FastAPI dependency) when moving to production.

---

## New dependencies

| Package | Version | Why |
|---|---|---|
| `fastapi` | `>=0.115.0` | Web framework |
| `uvicorn[standard]` | `>=0.34.0` | ASGI server (includes `httptools` + `uvloop` for performance) |
| `python-multipart` | `>=0.0.20` | Required by FastAPI for `UploadFile` / multipart form data |

No new AI or data-processing dependencies.

---

## File structure

```
PDFScout/
├── api.py                  # FastAPI app entry point (new)
├── src/
│   └── api/
│       ├── __init__.py     # new (empty)
│       ├── models.py       # Pydantic response models (new)
│       ├── jobs.py         # JobRecord dataclass + in-memory store (new)
│       └── runner.py       # background extraction task (new)
└── tmp/
    └── uploads/            # temp PDF storage (auto-created, gitignored)
```

`api.py` at the root mirrors `main.py`; `src/api/` holds the implementation
modules.

---

## Endpoints

### `GET /health`

```
200 OK
{
  "status": "ok",
  "model": "claude-sonnet-4-6",
  "supported_doc_types": ["invoice", "scientific_paper"],
  "fallback_doc_type": "baseline_core",
  "langfuse_enabled": false
}
```

No authentication needed.

---

### `POST /extract`

**Request**: `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | `UploadFile` | PDF file (required) |
| `force` | `bool` | Re-run even if a completed/failed job exists for this PDF (default: `false`) |

**Responses**:

| Code | Meaning |
|---|---|
| `202 Accepted` | Job created (or existing running job returned) |
| `400 Bad Request` | Not a PDF (`application/pdf` check) |
| `413 Content Too Large` | File exceeds 32 MB |
| `422 Unprocessable Entity` | File is encrypted or has zero pages (detected before background task starts) |

`202` body:
```json
{
  "job_id": "a3f1c9d2...",
  "status": "queued",
  "file_name": "invoice.pdf",
  "created_at": "2026-05-30T21:12:00Z"
}
```

**Implementation note**: The endpoint reads the entire upload into memory to
compute the hash (needed to check for an existing job before saving), then
writes to disk only if the job is new. For files near 32 MB this holds 32 MB in
RAM momentarily — acceptable for a test interface.

---

### `GET /jobs/{job_id}`

Returns the full `JobRecord`.

```json
{
  "job_id": "a3f1c9d2...",
  "file_name": "invoice.pdf",
  "status": "running",
  "created_at": "2026-05-30T21:12:00Z",
  "completed_at": null,
  "total_pages": null,
  "document_type": null,
  "warnings": [],
  "error": null,
  "events": [
    "[GRAPH] Node 'native_extractor' completed.",
    "[GRAPH] Node 'classifier' completed."
  ],
  "result": null
}
```

On `completed`, `result` holds the full `hierarchical_document_tree` dict.
On `failed`, `error` holds the exception message.

| Code | Meaning |
|---|---|
| `200 OK` | Job found |
| `404 Not Found` | Unknown job_id |

---

### `DELETE /jobs/{job_id}`

Removes the job record from the in-memory store and deletes the temp file if
still present. Returns `204 No Content`. Does not cancel a running pipeline
(LangGraph tasks are not cancellable mid-flight without additional scaffolding).

---

## Background task (`src/api/runner.py`)

```
async def run_extraction(job_id, file_path, graph, checkpointer, langfuse):
    job = jobs[job_id]
    job.status = "running"
    try:
        config = {"configurable": {"thread_id": job_id}}

        if langfuse:
            with langfuse.start_as_current_span(name=f"PDFScout — {job.file_name}") as span:
                with propagate_attributes(session_id=job_id):
                    await _stream_graph(graph, file_path, config, job)
                _update_span(span, job)
        else:
            await _stream_graph(graph, file_path, config, job)

        job.status = "completed"
        job.completed_at = datetime.utcnow()
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = datetime.utcnow()
    finally:
        Path(file_path).unlink(missing_ok=True)

async def _stream_graph(graph, file_path, config, job):
    async for event in graph.stream({"file_path": file_path}, config):
        for node_name in event:
            job.events.append(f"[GRAPH] Node '{node_name}' completed.")
    final_state = await graph.aget_state(config)
    tree = final_state.values.get("hierarchical_document_tree") if final_state else None
    job.result = tree
    job.warnings = tree.get("extraction_warnings", []) if tree else []
    job.document_type = tree.get("document_type") if tree else None
    job.total_pages = final_state.values.get("total_pages") if final_state else None
```

**Why not `asyncio.create_task` directly in the endpoint**: FastAPI's
`BackgroundTasks` runs in the same event loop as the request but after the
response is sent. For simplicity, we use `asyncio.create_task()` directly so
we have a handle to store in the job record (future cancellation support).

---

## `api.py` (entry point)

```python
uvicorn api:app --host 0.0.0.0 --port 8000
```

Or via uv:

```bash
uv run uvicorn api:app --reload
```

The `lifespan` context manager:
1. Creates `tmp/uploads/`
2. Opens `AsyncSqliteSaver` (same `state_checkpoint.db` as CLI — runs share checkpoints)
3. Compiles LangGraph app
4. Initialises Langfuse if keys present
5. On shutdown: calls `langfuse.shutdown()` (once)

---

## Error handling

| Exception | HTTP code | Source |
|---|---|---|
| `ValueError: PDF is encrypted` | 422 | `get_page_count()` |
| `ValueError: PDF yielded zero pages` | 422 | `native_extractor_node` |
| File size > 32 MB | 413 | Upload handler |
| Content-Type not `application/pdf` | 400 | Upload handler |
| Any other `Exception` in background task | — | `job.status = "failed"`, `job.error = str(exc)` |

The encrypted PDF and zero-pages errors are synchronous (detected by `pypdf`
before the first API call) so they can be raised pre-emptively in the endpoint
handler rather than inside the background task, giving an immediate non-202
response.

**Implementation note for early validation**: Call `get_page_count(tmp_path)`
synchronously (via `asyncio.to_thread`) before returning `202`. If it raises,
delete the temp file and return the appropriate error code.

---

## Open issues / devil's advocate concerns

| # | Concern | Decision |
|---|---|---|
| 1 | In-memory store is lost on restart | Acceptable for "basic testing." Document it. |
| 2 | Concurrent bursts from multiple jobs can exceed `CONCURRENCY_LIMIT` | The semaphore in `worker_node.py` is process-global — it caps total concurrent Anthropic calls across all jobs. No additional throttling needed. |
| 3 | `DELETE /jobs/{job_id}` on a running job | Documents as "does not cancel the pipeline." The task finishes and writes to a now-absent job record; that's a no-op since we check existence before writing. Need a guard: check `job_id in jobs` before each write in `runner.py`. |
| 4 | Same PDF submitted twice concurrently (before hash computed) | Both requests compute the hash, first wins the `jobs[job_id] = ...` assignment, second sees the existing record and returns 202 without starting a new task. The race window is tiny (hash + dict write). |
| 5 | `graph.aget_state()` vs `graph.get_state()` | The compiled graph exposes both. Background task is an async coroutine — use `aget_state()` (non-blocking). |
| 6 | Langfuse `span.update()` metadata after `propagate_attributes` exits | Same as `main.py`: `span.update()` is called inside the `with span` block but outside `with propagate_attributes` — correct, targets only the parent span. |
| 7 | `tmp/uploads/` gitignored? | Yes — add `tmp/` to `.gitignore`. |
| 8 | Upload file content-type spoofing | Only check `content_type == "application/pdf"`; a client can fake it. The `pypdf` early validation catches corrupted/non-PDF content before it reaches Claude. |

---

## Implementation steps (ordered)

1. `uv add fastapi "uvicorn[standard]" python-multipart` — update `pyproject.toml` and `uv.lock`
2. Add `tmp/` to `.gitignore`
3. Create `src/api/__init__.py` (empty)
4. Create `src/api/models.py` — Pydantic `JobResponse` and `HealthResponse` models
5. Create `src/api/jobs.py` — `JobRecord` dataclass + `jobs: dict[str, JobRecord]` module-level store
6. Create `src/api/runner.py` — `run_extraction()` coroutine
7. Create `api.py` — FastAPI app with lifespan, routes inline (small enough for a single file)
8. Update `README.md` — add "API Server" section under "Usage" with `uvicorn` command
9. Update `CHANGELOG.md` — document as a new feature (minor version bump deferred until implementation is complete and reviewed)
