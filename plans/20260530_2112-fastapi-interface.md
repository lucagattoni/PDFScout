# FastAPI Interface Plan
_Created: 2026-05-30 21:12_\
_Updated: 2026-05-30 22:05 · Implementation feasibility pass — tracing interface redesign, StateSnapshot guards, CWD-relative path_

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

**Alternative considered — SSE streaming**: Would surface per-node events in real
time (closer to CLI output) but complicates the client. Excluded from "basic"
scope; the node event log is stored in the job record so it can be retrieved
after completion.

---

### 2. Job ID = pdf_hash

The LangGraph checkpointer uses `thread_id = pdf_hash`. Making `job_id =
pdf_hash` ties the HTTP job identity to the checkpointer thread identity, with
two consequences:

- **Idempotency**: submitting the same PDF a second time returns the existing
  `job_id` and result.
- **Checkpoint resume after server restart**: when the API server restarts, the
  in-memory job store is cleared. If a client re-submits a PDF whose extraction
  was interrupted (e.g., mid-burst), the runner detects the interrupted
  checkpoint and resumes mid-flight rather than restarting from page 1.

**Resume detection (fix for review finding #1)**

Calling `graph.stream({"file_path": file_path}, config)` unconditionally
re-enters the graph at `START`, re-running `native_extractor` and resetting
`extracted_flat_blocks` — the checkpoint is not skipped. For true resume, pass
`None` as input so LangGraph continues from the saved checkpoint without
re-triggering `START`.

The runner checks `snapshot.next` before calling `stream()`:

```python
async def _resolve_input(graph, file_path: str, config: dict, force: bool) -> dict | None:
    if force:
        return {"file_path": file_path}   # force=True → always restart from START
    snapshot = await graph.aget_state(config)
    # snapshot.next is () for a completed or never-started run;
    # non-empty means the run was interrupted mid-execution.
    if snapshot.values and snapshot.next:
        return None  # resume interrupted run — do not re-trigger START
    return {"file_path": file_path}   # no checkpoint or already completed → fresh start
```

`force` is passed from the endpoint's `?force=true` query parameter.

Collision risk: SHA-256, files not adversarially chosen — negligible.

---

### 3. Shared resources via FastAPI lifespan

The LangGraph app and the SQLite checkpointer are both expensive to initialise.
They are created once in the FastAPI `lifespan` context manager and stored in
app state, then reused by every request.

```
lifespan startup:
  open AsyncSqliteSaver("api_checkpoint.db")  →  app.state.graph
  build_app(checkpointer)                     →  app.state.graph
  Langfuse()                                  →  app.state.langfuse  (if keys present)
  mkdir Path(__file__).parent / "tmp" / "uploads"  # anchored to api.py, not CWD

lifespan shutdown:
  langfuse.shutdown()  (once — at process exit, not after each request)
  # AsyncSqliteSaver closes automatically via async context manager __aexit__
```

**Separate checkpoint DB (fix for review finding #5)**

The API uses `api_checkpoint.db`, not the CLI's `state_checkpoint.db`. Running
both simultaneously against the same SQLite file causes WAL lock contention that
surfaces as silent background-task failures rather than HTTP 500s — there is no
signal to the operator. Separate files eliminate the interference entirely.

---

### 4. Langfuse — shared tracing utility (fix for review finding #4)

`main.py` already implements `if langfuse: with span: ... else: run plain`.
The original plan duplicated this branch verbatim in `runner.py`, creating a
third maintenance site (two files with identical Langfuse logic).

**Fix**: extract into `src/utils/tracing.py` as an **async context manager**:

```python
from contextlib import asynccontextmanager
from langfuse import propagate_attributes

@asynccontextmanager
async def tracing_span(langfuse, display_name: str, session_id: str):
    """
    Async context manager that opens a Langfuse span (if langfuse is not None)
    and sets propagate_attributes for the duration of the block.
    Yields the span object (or None). Span stays open while the caller streams
    the graph, reads final state, and calls span.update() — then closes on exit.
    """
    if langfuse:
        with langfuse.start_as_current_span(name=display_name) as span:
            with propagate_attributes(session_id=session_id):
                yield span
    else:
        yield None
```

Usage in both `main.py` and `runner.py`:

```python
async with tracing_span(langfuse, display_name, session_id) as span:
    async for event in graph.stream(input_data, config):
        # per-node work
    final_state = await graph.aget_state(config)
    # ... read job fields from final_state ...
    if span:
        span.update(metadata={...})   # span is still open here
# span closes on __aexit__
```

The `with langfuse.start_as_current_span(...)` inside `asynccontextmanager` is a
synchronous context manager nested inside an async one — valid Python. The `yield`
from inside the `with` block keeps the span open for the entire `async with` body.

`main.py` is also updated to use `tracing_span` — the `if/else` Langfuse branch
is removed from both entry points.

**Lifecycle change from `main.py`**

`main.py` calls `langfuse.shutdown()` in the `finally` block of each CLI run.
In a long-running server this would kill the background flush thread after the
first request. The API moves `shutdown()` to the lifespan cleanup so it fires
exactly once — at process exit — after all spans are enqueued.

**`propagate_attributes` context isolation (review finding #7 — revised)**

Each `run_extraction` coroutine is launched as `asyncio.create_task()`, which
copies the current context at task-creation time. Concurrent jobs therefore have
isolated `ContextVar` copies at the job level — no cross-job bleed. ✓

However, LangGraph's Send fan-out (burst workers) does **not** use
`asyncio.create_task()` internally — it uses a custom `submit()` executor that
does not guarantee ContextVar propagation to dispatched worker coroutines.
Langfuse span context set by `propagate_attributes` may not propagate into
burst-phase worker spans, meaning those child spans may not be attributed to the
parent trace in Langfuse. This is a **known observability limitation**, not a
correctness bug, and affects the CLI equally. Document it; do not attempt to fix
it at the API layer.

---

### 5. Temp file handling and atomic job creation (fix for review findings #2 and #3)

The original plan wrote the file first, then checked the job store — allowing
two concurrent first-time submissions of the same PDF to both start background
tasks, with the first task's `finally` deleting the file while the second was
mid-read.

**Revised flow (endpoint handler)**:

```python
content = await file.read()           # read full upload (≤32 MB by guard)
job_id = hashlib.sha256(content).hexdigest()

# Atomically claim the job record — no await between check and set,
# so no concurrent request can interleave here.
new_record = JobRecord(job_id=job_id, file_name=file.filename, status="queued", ...)
existing = jobs.setdefault(job_id, new_record)

if existing is not new_record:
    # Lost the race — another request already owns this job_id.
    # Return the existing record without writing to disk or starting a task.
    return JobResponse.from_record(existing)

# Won the race — we are the sole owner of this job.
# Write the file only once; no other concurrent request will write it.
_UPLOAD_DIR = Path(__file__).parent.parent.parent / "tmp" / "uploads"  # api.py-relative
tmp_path = _UPLOAD_DIR / f"{job_id}.pdf"
await asyncio.to_thread(tmp_path.write_bytes, content)

# Optionally call force-clear on the job store entry and re-create
# the record above if force=True (handled before the setdefault block).

asyncio.create_task(run_extraction(job_id, str(tmp_path), graph, langfuse, force))
```

Since `asyncio` is cooperative and `dict.setdefault()` is a synchronous
operation (no `await`), only one coroutine can execute it at a time — the first
caller wins atomically. The second caller returns 202 with the existing record
and never writes to disk or starts a task. There is now exactly one `finally`
block responsible for deleting the temp file.

**`force=True` handling**: before the `setdefault` block, check if an existing
record is in `completed` or `failed` state. If yes and `force=True`, delete the
record from `jobs` and proceed as a fresh submission. If the existing record is
`running` and `force=True`, return 409 (see §7).

---

### 6. In-memory job store

A module-level `dict[str, JobRecord]` is the job store. No persistence across
restarts; acceptable for a "basic testing" interface.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

@dataclass
class JobRecord:
    job_id: str
    file_name: str
    created_at: datetime
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    completed_at: datetime | None = None
    total_pages: int | None = None
    document_type: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    result: dict | None = None
    events: list[str] = field(default_factory=list)
```

`status` defaults to `"queued"` so `GET /jobs/{job_id}` returns a valid record
immediately after 202 — before the background task has a chance to set
`"running"`. This closes the window where a status field would be unset.

Access is from a single `asyncio` event loop (FastAPI's), so a plain `dict` is
safe without locks.

---

### 7. Duplicate-run guard and DELETE behaviour (fix for review finding #3)

**POST /extract — duplicate guard**:

| Existing job state | `force` | Action |
|---|---|---|
| `running` | any | Return 202 with existing record — do not start a second task |
| `running` | `true` | Return 409 — cannot force-replace a running job; wait for it to finish |
| `completed` or `failed` | `false` | Return 202 with existing record and result |
| `completed` or `failed` | `true` | Clear record, start fresh |

**DELETE /jobs/{job_id}**:

| Job state | Action |
|---|---|
| `queued` or `running` | Return 409 Conflict — deletion of active jobs is not supported |
| `completed` or `failed` | Remove record, delete temp file (`missing_ok=True`), return 204 |

Returning 409 for running jobs eliminates the stale-reference race documented
in the original review (finding #3). The background task always has a valid
`jobs[job_id]` entry to mutate because deletion only happens after the task
completes. There is no need for a per-write `jobs.get(job_id) is job` guard.

---

### 8. File-size guard

FastAPI's `UploadFile` does not expose a streaming size check before `read()`.
The guard is applied to the in-memory `content` immediately after `await
file.read()`, before any disk write or hashing:

```python
content = await file.read()
if len(content) > 32 * 1024 * 1024:
    raise HTTPException(status_code=413, detail="File exceeds 32 MB limit.")
```

A fast path: check `request.headers.get("content-length")` before calling
`read()` and reject immediately if the declared size exceeds the limit. A
malicious client can spoof `Content-Length`, so the in-memory check remains the
authoritative guard.

---

### 9. Validation errors — let the graph raise (fix for review finding #6)

The original plan called `get_page_count(tmp_path)` pre-flight via
`asyncio.to_thread` before returning 202. This duplicates work that
`native_extractor_node` already does as its first action, causing two full
`pypdf.PdfReader` parses per request.

**Fix**: remove the pre-flight call entirely. Let `native_extractor_node` raise
`ValueError` inside the background task. The runner catches it, sets
`job.status = "failed"` and `job.error = str(exc)`, and the client sees it on
the next `GET /jobs/{job_id}` poll.

The only synchronous validation the endpoint performs is:
- Content-Type check (`application/pdf`)
- Size check (> 32 MB)

Both are O(1) header/length operations requiring no PDF parsing.

---

### 10. No authentication

Out of scope for a basic testing interface. Add an API key middleware layer
(FastAPI dependency) when moving to production.

---

## New dependencies

| Package | Version | Why |
|---|---|---|
| `fastapi` | `>=0.115.0` | Web framework |
| `uvicorn[standard]` | `>=0.34.0` | ASGI server (`httptools` + `uvloop`) |
| `python-multipart` | `>=0.0.20` | Required by FastAPI for `UploadFile` |

---

## File structure

```
PDFScout/
├── api.py                      # FastAPI app entry point (new)
├── API_README.md               # API reference documentation (new)
├── src/
│   ├── api/
│   │   ├── __init__.py         # new (empty)
│   │   ├── models.py           # Pydantic response models (new)
│   │   ├── jobs.py             # JobRecord dataclass + in-memory store (new)
│   │   └── runner.py           # background extraction task (new)
│   └── utils/
│       ├── pdf_utils.py        # existing
│       └── tracing.py          # shared Langfuse tracing helper (new)
└── tmp/
    └── uploads/                # temp PDF storage (auto-created, gitignored)
```

`api.py` at the root mirrors `main.py`; `src/api/` holds the implementation
modules. `src/utils/tracing.py` is shared by both `main.py` and `runner.py`.

---

## Endpoints

### `GET /health`

```json
{
  "status": "ok",
  "model": "claude-sonnet-4-6",
  "supported_doc_types": ["invoice", "scientific_paper"],
  "fallback_doc_type": "baseline_core",
  "langfuse_enabled": false
}
```

---

### `POST /extract`

**Request**: `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | `UploadFile` | PDF file (required) |
| `force` | `bool` | Re-run a completed/failed job (default: `false`) |

**Responses**:

| Code | Meaning |
|---|---|
| `202 Accepted` | Job created or existing record returned |
| `400 Bad Request` | Not a PDF (`content-type` check) |
| `409 Conflict` | `force=true` on a running job |
| `413 Content Too Large` | File exceeds 32 MB |

Encrypted PDFs and zero-page PDFs are detected inside the graph; the job status
goes to `failed` with the error in `job.error`. No 422 from the endpoint itself.

`202` body:
```json
{
  "job_id": "a3f1c9d2...",
  "status": "queued",
  "file_name": "invoice.pdf",
  "created_at": "2026-05-30T21:12:00Z"
}
```

---

### `GET /jobs/{job_id}`

Returns the full `JobRecord`. On `completed`, `result` holds the
`hierarchical_document_tree`. On `failed`, `error` holds the exception message.
`events` accumulates per-node completion lines as the job runs.

| Code | Meaning |
|---|---|
| `200 OK` | Job found |
| `404 Not Found` | Unknown job_id |

---

### `DELETE /jobs/{job_id}`

| Job state | Response |
|---|---|
| `queued` or `running` | 409 Conflict |
| `completed` or `failed` | 204 No Content — record and temp file removed |

---

## Background task (`src/api/runner.py`)

```python
async def run_extraction(job_id: str, file_path: str, graph, langfuse, force: bool):
    job = jobs[job_id]
    job.status = "running"
    try:
        config = {"configurable": {"thread_id": job_id}}
        input_data = await _resolve_input(graph, file_path, config, force)

        await run_with_tracing(
            graph=graph,
            input_data=input_data,
            config=config,
            display_name=job.file_name,
            session_id=job_id,
            langfuse=langfuse,
            on_event=lambda node: job.events.append(f"[GRAPH] Node '{node}' completed."),
        )

        final_state = await graph.aget_state(config)
        # graph.aget_state() always returns a StateSnapshot, never None.
        # values={} on a run that never checkpointed (e.g., failed before first node).
        tree = final_state.values.get("hierarchical_document_tree")
        job.result = tree
        job.warnings = tree.get("extraction_warnings", []) if tree else []
        job.document_type = tree.get("document_type") if tree else None
        job.total_pages = final_state.values.get("total_pages")
        job.status = "completed"
        job.completed_at = datetime.utcnow()
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = datetime.utcnow()
    finally:
        Path(file_path).unlink(missing_ok=True)
```

`_resolve_input` is the resume-detection helper from §2.
`run_with_tracing` is the shared helper from `src/utils/tracing.py` (§4).
The task is launched via `asyncio.create_task()` in the endpoint handler, not
via FastAPI `BackgroundTasks`, so a handle is available for future cancellation.

---

## `api.py` (entry point)

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000
uv run uvicorn api:app --reload   # development
```

The `lifespan` context manager:
1. Creates `Path(__file__).parent / "tmp" / "uploads"` — anchored to `api.py`'s location, not CWD, so `uvicorn api:app` works from any directory
2. Opens `AsyncSqliteSaver(str(Path(__file__).parent / "api_checkpoint.db"))`
3. Compiles LangGraph app via `build_app(checkpointer)`
4. Initialises `Langfuse()` if `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` present
5. On shutdown: calls `langfuse.shutdown()` (once)

---

## Error handling summary

| Condition | HTTP code | Where caught |
|---|---|---|
| `Content-Type` not `application/pdf` | 400 | Upload handler |
| File > 32 MB | 413 | Upload handler |
| `force=true` on a running job | 409 | Duplicate-run guard |
| DELETE on a running/queued job | 409 | DELETE handler |
| Encrypted PDF | — | `job.status = "failed"` |
| Zero-page PDF | — | `job.status = "failed"` |
| Any other pipeline exception | — | `job.status = "failed"` |

---

## Open issues / devil's advocate concerns

| # | Concern | Resolution |
|---|---|---|
| 1 | In-memory store lost on restart | Accepted for "basic testing." Checkpoint in `api_checkpoint.db` allows resume; only the job metadata (status, events) is lost. |
| 2 | Concurrent bursts from multiple jobs exceed `CONCURRENCY_LIMIT` | The `asyncio.Semaphore` in `worker_node.py` is process-global — caps total Anthropic calls across all jobs. No additional throttling needed. |
| 3 | DELETE on running job races with background task | Resolved — DELETE returns 409 for active jobs. Task always has a valid store entry. |
| 4 | Same PDF submitted twice concurrently | Resolved — `setdefault` is synchronous (no await), atomic in the asyncio event loop. First caller wins; second returns 202 without starting a task or writing the file. |
| 5 | `graph.aget_state()` vs `graph.get_state()` | Use `aget_state()` (async) throughout the background task coroutine. |
| 6 | Langfuse `span.update()` after `propagate_attributes` exits | Same as `main.py`: `span.update()` is inside `with span` but outside `with propagate_attributes` — targets only the parent span. Correct. |
| 7 | `tmp/uploads/` gitignored? | Yes — add `tmp/` to `.gitignore`. |
| 8 | Content-Type spoofing | Content-Type check is a hint only; `pypdf.PdfReader` in `native_extractor_node` will raise on non-PDF bytes and mark the job failed. |
| 9 | resume logic when snapshot.next is non-empty but file was deleted | If the server crashed after extraction finished but before cleanup, `snapshot.next` is `()` — the run completed, so no resume is attempted. If the server crashed mid-burst, `file_path` points to a file that may or may not still exist. The runner re-uploads the file (from the new request) before starting the resume, so the file is always present at resume time. |
| 10 | `propagate_attributes` context bleed across concurrent jobs | Job-level isolation is safe (each `run_extraction` is an `asyncio.create_task()`). Burst-phase Send workers may not inherit the ContextVar — LangGraph's `submit()` does not guarantee propagation. Known observability limitation; burst spans may appear detached in Langfuse. Affects CLI equally; not addressed at API layer. |

---

## Implementation steps (ordered)

1. `uv add fastapi "uvicorn[standard]" python-multipart`
2. Add `tmp/` to `.gitignore`
3. Create `src/utils/tracing.py` — `run_with_tracing()` shared helper; update `main.py` to use it
4. Create `src/api/__init__.py` (empty)
5. Create `src/api/models.py` — Pydantic `JobResponse` and `HealthResponse`
6. Create `src/api/jobs.py` — `JobRecord` dataclass + `jobs` store
7. Create `src/api/runner.py` — `run_extraction()` + `_resolve_input()`
8. Create `api.py` — FastAPI app with lifespan and routes
9. Create `API_README.md` — dedicated API reference (endpoints, request/response shapes, job lifecycle, `uvicorn` startup command, env vars)
10. Update `README.md` — add "API Server" section under "Usage" linking to `API_README.md`
11. Update `CHANGELOG.md` — document as new feature (version bump on implementation completion)
