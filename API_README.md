# PDFScout API

HTTP interface for the PDFScout extraction pipeline. Accepts PDF uploads,
runs the LangGraph pipeline asynchronously, and exposes job status via polling.

---

## Starting the server

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000
```

Development mode (auto-reload on file changes):

```bash
uv run uvicorn api:app --reload
```

Interactive API docs are available at `http://localhost:8000/docs` (Swagger UI)
once the server is running.

---

## Environment variables

Same as the CLI — set in `.env` at the project root:

```text
ANTHROPIC_API_KEY=sk-ant-...          # required

LANGFUSE_PUBLIC_KEY=pk-lf-...         # optional — enables tracing
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

---

## Job lifecycle

```text
POST /extract  →  202 Accepted  →  job_id (status: "queued")
                                        │
                                   background task starts
                                        │
                                   status: "running"
                                        │
                              ┌─────────┴──────────┐
                         "completed"           "failed"
                         result: {...}         error: "..."
```

Poll `GET /jobs/{job_id}` until `status` is `completed` or `failed`.

---

## Endpoints

### `GET /health`

Returns server status and configuration.

**Response `200 OK`**

```json
{
  "status": "ok",
  "model": "claude-sonnet-4-6",
  "supported_doc_types": ["contract", "invoice", "scientific_paper"],
  "fallback_doc_type": "baseline_core",
  "langfuse_enabled": false
}
```

---

### `POST /extract`

Upload a PDF and start an extraction job.

**Request** — `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | yes | PDF file (`content-type: application/pdf`) |
| `force` | bool | no | Re-run a completed or failed job (default: `false`) |

#### Responses

| Code | Meaning |
|---|---|
| `202 Accepted` | Job created or existing record returned |
| `400 Bad Request` | File is not `application/pdf` |
| `409 Conflict` | `force=true` on a running or queued job |
| `413 Content Too Large` | File exceeds 32 MB |

**`202` body** — same shape as `GET /jobs/{job_id}`.

**Idempotency**: the `job_id` is the SHA-256 hash of the PDF. Submitting the
same file twice returns the same `job_id` without starting a duplicate pipeline
run. Use `force=true` to explicitly re-run a completed or failed job.

**Checkpoint resume**: if the server was restarted mid-extraction, re-submitting
the same PDF automatically resumes from the last checkpoint rather than
restarting from page 1.

---

### `GET /jobs/{job_id}`

Poll extraction status and retrieve the result.

**Response `200 OK`**

```json
{
  "job_id": "a3f1c9d2...",
  "file_name": "invoice.pdf",
  "status": "completed",
  "created_at": "2026-05-30T21:12:00Z",
  "completed_at": "2026-05-30T21:12:45Z",
  "total_pages": 3,
  "document_type": "invoice",
  "warnings": [],
  "error": null,
  "result": { ... },
  "events": [
    "[GRAPH] Node 'native_extractor' completed.",
    "[GRAPH] Node 'classifier' completed.",
    "[GRAPH] Node 'pioneer_parser' completed.",
    "[GRAPH] Node 'burst_dispatcher' completed.",
    "[GRAPH] Node 'parser_worker' completed.",
    "[GRAPH] Node 'hierarchy_node' completed."
  ]
}
```

| Field | Description |
|---|---|
| `status` | `queued` → `running` → `completed` \| `failed` |
| `result` | Full `hierarchical_document_tree` — present only when `completed` |
| `error` | Exception message — present only when `failed` |
| `events` | Per-node completion log, appended in real time |
| `warnings` | Extraction warnings (e.g., pioneer page validation degraded) |

**Response `404 Not Found`** — unknown `job_id` (job store is in-memory; cleared on server restart).

---

### `DELETE /jobs/{job_id}`

Remove a completed or failed job record and clean up the temp file.

| Code | Meaning |
|---|---|
| `204 No Content` | Record deleted |
| `404 Not Found` | Unknown `job_id` |
| `409 Conflict` | Job is `queued` or `running` — wait for it to finish |

---

## Notes

- **In-memory job store** — job records are lost when the server restarts.
  The extraction checkpoint in `api_checkpoint.db` persists, so the result can
  be recovered by re-submitting the PDF.
- **Checkpoint DB** — the API uses `api_checkpoint.db` (separate from the CLI's
  `state_checkpoint.db`) to avoid SQLite write contention.
- **Encrypted PDFs** — detected inside the pipeline; the job goes to `failed`
  with the error message in `job.error`.
- **Max file size** — 32 MB (Anthropic API limit).
- **Concurrency** — the burst-phase semaphore (`CONCURRENCY_LIMIT = 3` in
  `src/config.py`) caps total concurrent Anthropic API calls across all running
  jobs.
- **Langfuse tracing** — when enabled, each job produces a top-level Langfuse
  span. Burst-phase worker spans may appear detached in the Langfuse UI because
  LangGraph's Send fan-out does not propagate asyncio ContextVars to dispatched
  tasks.
