# Unit & Integration Test Plan

**Date:** 2026-05-31  
**Branch:** `claude/unit-integration-tests-plan-P9ZyN`

---

## 1. Goals

- Achieve comprehensive test coverage of all pure logic without hitting external APIs.
- Guard the LangGraph pipeline topology and state mutation contracts.
- Cover all FastAPI endpoints including edge cases (idempotency, force-rerun, conflict detection).
- Enable CI to run the full suite in isolation (no `ANTHROPIC_API_KEY` required).

---

## 2. Test Infrastructure

### 2.1 New Dependencies (added to `pyproject.toml`)

```toml
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
    "pytest-cov>=5.0",
    "httpx>=0.27",              # AsyncClient for FastAPI tests
    "asgi-lifespan>=2.1",       # LifespanManager for FastAPI lifespan in tests
]
```

`pypdf` is already a production dependency and does not need to be added.

### 2.2 `pytest` Configuration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths    = ["tests"]
```

Coverage is **not** baked into `addopts` — it slows every run. Use an explicit command when needed:

```bash
uv run pytest --cov=. --cov-report=term-missing
```

---

## 3. Directory Layout

```
tests/
├── __init__.py
├── conftest.py                         # shared fixtures
├── unit/
│   ├── __init__.py
│   ├── test_state.py
│   ├── test_schema_registry.py
│   ├── test_edges.py
│   ├── test_pdf_utils.py
│   ├── test_page_counter.py
│   ├── test_tracing.py
│   ├── test_models.py
│   ├── test_graph.py
│   └── nodes/
│       ├── __init__.py
│       ├── test_extractor_node.py
│       ├── test_classifier_node.py
│       ├── test_worker_node.py
│       ├── test_retry_node.py
│       └── test_hierarchy_node.py
└── integration/
    ├── __init__.py
    ├── test_api_health.py
    ├── test_api_extract.py
    ├── test_api_jobs.py
    ├── test_api_runner.py
    └── test_graph_pipeline.py
```

`__init__.py` files are required in every test subdirectory so pytest treats them as separate packages. Without them, two files with the same name in sibling directories (e.g., a future `conftest.py` in both `unit/` and `integration/`) would cause import collisions.

`test_config.py` and `test_jobs.py` are intentionally excluded — testing that constants have specific values and that `@dataclass` defaults are set is testing the Python interpreter, not application behaviour. Those invariants are exercised indirectly by every other test that relies on them.

There is no committed `tests/fixtures/minimal.pdf`. The minimal PDF is generated programmatically inside `conftest.py` at session start (see §4).

---

## 4. Shared Fixtures (`tests/conftest.py`)

### 4.1 Environment

Every node constructs `AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])` using `os.environ[...]` (not `os.getenv`), so the dict lookup happens before any mock intercepts the class. A session-scoped autouse fixture unconditionally overwrites the key so tests never hit a `KeyError` and a misconfigured patch can never accidentally call the real API using a valid key from the CI environment:

```python
@pytest.fixture(autouse=True, scope="session")
def set_fake_api_key():
    os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake"
```

`os.environ.setdefault` must not be used here: if `ANTHROPIC_API_KEY` is already set in the environment, `setdefault` leaves the real value in place. A patch that silently fails to apply would then call the real Anthropic API.

### 4.2 Global `jobs` Store Isolation

`src/api/jobs.py` exports a module-level dict `jobs: dict[str, JobRecord] = {}`. Without explicit cleanup, state from one test leaks into the next. An autouse function-scoped fixture clears it after every test:

```python
@pytest.fixture(autouse=True)
def clear_jobs_store():
    yield
    from src.api.jobs import jobs
    jobs.clear()
```

### 4.3 PDF Fixtures

```python
@pytest.fixture(scope="session")
def minimal_pdf_bytes() -> bytes:
    """Generates a valid 1-page PDF in memory using pypdf's PdfWriter."""
    from pypdf import PdfWriter
    from io import BytesIO
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()

@pytest.fixture
def minimal_pdf_path(tmp_path, minimal_pdf_bytes) -> str:
    p = tmp_path / "test.pdf"
    p.write_bytes(minimal_pdf_bytes)
    return str(p)
```

`minimal_pdf_bytes` has session scope (generate once). `minimal_pdf_path` has function scope because `tmp_path` is function-scoped — each test gets its own file path.

### 4.4 FastAPI Test Client

The real `lifespan` in `api.py` opens a SQLite checkpoint database and optionally connects to Langfuse. Tests must not run that setup. The approach: temporarily override `app.router.lifespan_context` with a lightweight replacement that injects a mock graph, then restore the original on teardown.

The `mock_graph.stream` method must be an async generator, not a coroutine. An `AsyncMock` with a plain `return_value` returns a coroutine when called, which `async for` cannot iterate. The helper below produces a proper async generator:

```python
async def _empty_stream(*args, **kwargs):
    return
    yield   # makes this an async generator function

@pytest.fixture
async def mock_graph():
    graph = AsyncMock()
    graph.stream = _empty_stream
    # aget_state must return an object with .values (dict) and .next (empty tuple)
    snapshot = MagicMock()
    snapshot.values = {}
    snapshot.next = ()
    graph.aget_state = AsyncMock(return_value=snapshot)
    return graph

@pytest.fixture
async def api_client(mock_graph):
    from asgi_lifespan import LifespanManager
    import api as app_module

    original_lifespan = app_module.app.router.lifespan_context

    @asynccontextmanager
    async def override_lifespan(app):
        app.state.graph = mock_graph
        app.state.langfuse = None
        yield

    app_module.app.router.lifespan_context = override_lifespan
    try:
        async with LifespanManager(app_module.app) as manager:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=manager.app),
                base_url="http://test",
            ) as client:
                yield client
    finally:
        app_module.app.router.lifespan_context = original_lifespan
```

The `finally` block restores the original lifespan. Without it, the module-level `app` object is permanently mutated for the entire test session.

`mock_graph` and `api_client` are separate fixtures so tests that need to configure the mock graph's behaviour (e.g., to simulate a running job's stream) can request `mock_graph` directly alongside `api_client`.

`asgi-lifespan` is required for this (`asgi-lifespan>=2.1` in dev deps).

### 4.5 Other Fixtures

| Fixture | Scope | Description |
|---|---|---|
| `sample_block` | function | One well-formed extracted block dict with `bbox.page_number=1` |
| `sample_state` | function | Minimal `PDFParserState`-compatible dict for node tests |

---

## 5. Unit Tests

### 5.1 `tests/unit/test_state.py` — Merge Reducers

**`merge_flat_blocks`**
- `existing=[], new=[block]` → returns `[block]`
- `existing=[block1], new=[block2]` → returns `[block1, block2]`
- `existing=[block1], new=None` → returns `[]` (reset sentinel)
- `existing=[], new=None` → returns `[]`

**`merge_warnings`**
- `existing=[], new=["w"]` → `["w"]`
- `existing=["w1"], new=["w2"]` → `["w1", "w2"]`
- `existing=["w1"], new=[]` → `["w1"]`
- `existing=[], new=None` → `[]`

---

### 5.2 `tests/unit/test_schema_registry.py` — SchemaRegistry

**`_load_schema`**
- Known type `"invoice"` loads `schemas/invoice.json` without error.
- Known type `"scientific_paper"` loads `schemas/scientific_paper.json`.
- Unknown type `"xyz"` falls back to `baseline_core.json`.

**`get_schema_and_tool`**
- Returns a `(schema, tool)` tuple.
- `tool["input_schema"]` does **not** contain `"$schema"` or `"title"` keys.
- `tool["name"]` equals `f"extract_{doc_type}_structure"`.

**`validate`**
- Valid minimal payload for `"baseline_core"` passes without exception.
- Payload missing required `"blocks"` raises `jsonschema.ValidationError`.
- Payload with wrong block `"type"` enum value raises `jsonschema.ValidationError`.

---

### 5.3 `tests/unit/test_edges.py` — `pioneer_validation_route`

All tests use `document_type="baseline_core"`. Blocks must have `bbox.page_number=1` to be seen as active — this is the filter inside the function.

| Scenario | retry_count | blocks | Expected |
|---|---|---|---|
| No blocks extracted | 0 | `[]` | `"retry_node"` |
| No blocks, max retries | 3 | `[]` | `"burst_dispatcher"` |
| Blocks on wrong page (page_number=2, not 1) | 0 | valid blocks but page 2 | `"retry_node"` — same as empty |
| Blocks on wrong page, max retries | 3 | valid blocks but page 2 | `"burst_dispatcher"` |
| Blocks pass validation | 0 | valid blocks (page 1) | `"burst_dispatcher"` |
| Blocks fail validation | 1 | invalid blocks (page 1) | `"retry_node"` |
| Blocks fail validation, max retries | 3 | invalid blocks (page 1) | `"burst_dispatcher"` |

---

### 5.4 `tests/unit/test_pdf_utils.py` — `hash_file`, `encode_pdf_async`

**`hash_file`**
- Returns a 64-character hexadecimal string (SHA-256).
- Same file hashed twice yields the same digest.
- Different content yields a different digest.

**`encode_pdf_async`**
- Returns a non-empty string.
- Decoded bytes match the original file content.

---

### 5.5 `tests/unit/test_page_counter.py` — `get_page_count`

- Valid 1-page PDF returns `1`.
- Valid 3-page PDF returns `3`.
- Encrypted PDF raises `ValueError` with `"encrypted"` in the message.

*Encrypted PDF fixture: write programmatically with `pypdf`'s `PdfWriter.encrypt()`.*

---

### 5.6 `tests/unit/test_tracing.py` — `tracing_span`

The function has two branches:

- `langfuse=None` → context manager yields `None` without calling any Langfuse API.
- `langfuse` is a mock with `.start_as_current_span()` as a context manager → context manager yields the mock span; `propagate_attributes` is called with the correct `session_id`.

The second branch requires a mock Langfuse client that supports:
- `langfuse.start_as_current_span(name=...)` as a sync context manager yielding a `span` object.
- `propagate_attributes(session_id=...)` as a sync context manager (patch `src.utils.tracing.propagate_attributes`).

This is the only place the active Langfuse path is tested. The `run_extraction` tests all use `langfuse=None`, so without this unit test `tracing.py` cannot reach 100% coverage.

---

### 5.7 `tests/unit/test_models.py` — Pydantic Models

**`JobResponse.from_record`**
- All 10 fields from `JobRecord` map to their counterpart on `JobResponse`.
- `status`, `job_id`, `file_name`, `created_at` values are preserved exactly.

**`HealthResponse`**
- Instantiates without error with all required fields.

*`JobRecord` dataclass defaults are not explicitly tested here — they are exercised by every test that constructs one.*

---

### 5.7 `tests/unit/test_graph.py` — Graph Topology

**`burst_dispatcher_node`**
- `retry_count=0` → returns `{}`.
- `retry_count=2` → returns `{}` (boundary: just below threshold).
- `retry_count=3` → returns dict with `extraction_warnings` containing the degradation message (boundary: at threshold, `>= 3`).

**`dispatch_pages`**
- `total_pages=1` → returns the string `"hierarchy_node"`.
- `total_pages=3` → returns a list of two `Send` objects for pages 2 and 3.
- Each `Send` targets `"parser_worker"` and carries `current_page` set to the correct page number.

**`build_app`**
- `build_app(checkpointer=None)` compiles without raising.
- Compiled graph exposes all seven expected node names.

---

### 5.8 `tests/unit/nodes/test_extractor_node.py` — `native_extractor_node`

Patch target: `src.nodes.extractor_node.get_page_count`.

- Normal 2-page PDF: result contains `pdf_hash` (64-char hex), `total_pages=2`, `current_page=1`, `retry_count=0`, `last_validation_error=None`, `extracted_flat_blocks=None`.
- `get_page_count` returns `0`: raises `ValueError` with `"zero pages"` in the message.
- File does not exist: `hash_file` raises `FileNotFoundError` (no special handling expected — propagates naturally).

---

### 5.9 `tests/unit/nodes/test_classifier_node.py` — `classifier_node`

Patch target: `src.nodes.classifier_node.AsyncAnthropic` (not `anthropic.AsyncAnthropic`).

- Response text `"invoice"` → `document_type="invoice"`, schema loaded correctly.
- Response text `"scientific_paper"` → `document_type="scientific_paper"`.
- Response text `"unknown_garbage"` → `document_type=FALLBACK_DOC_TYPE`.
- Response text `"  invoice  "` (whitespace) → stripped to `"invoice"` and matched.

---

### 5.10 `tests/unit/nodes/test_worker_node.py` — `window_parser_node`

Patch target: `src.nodes.worker_node.AsyncAnthropic`.

- Response contains `tool_use` block with `blocks=[block]` → returns `{"extracted_flat_blocks": [block]}`.
- Response contains **no** `tool_use` block → raises `ValueError`.
- State has `last_validation_error="some error"` → a content block containing that error text is present in the captured API call args.
- State has `last_validation_error=None` → no extra content block is added (content list has exactly 2 items).

---

### 5.11 `tests/unit/nodes/test_retry_node.py` — `retry_incrementor_node`

- `extracted_flat_blocks=None` (the reset sentinel) → treated as no blocks; error detail mentions "No blocks".
- `extracted_flat_blocks=[]` (explicit empty list) → same "No blocks" path.
- Valid-structured but schema-failing blocks → `error_detail` contains the field path from jsonschema.
- `retry_count` increments by exactly 1 each call.
- `extracted_flat_blocks` is reset to `None` in the returned dict.
- `last_validation_error` string contains `"(attempt X/3)"` where X is the new count.

---

### 5.12 `tests/unit/nodes/test_hierarchy_node.py`

Patch target: `src.nodes.hierarchy_node.AsyncAnthropic`.

**`geometric_pre_sorter`**
- Input: list with one block → output: list with the same block unchanged.
- Three blocks on different pages → sorted ascending by page number.
- Two blocks on same page, same column bucket, different `ymin` → sorted by `ymin` ascending.
- Two blocks on same page, different `xmin` (crossing a bucket boundary) → sorted by column bucket ascending.

**`layout_hierarchy_agent_node`**
- `extracted_flat_blocks=None` → raises `TypeError`. This is an existing defensive gap; the test documents and pins the current (broken) behaviour so that a future fix is an explicit, visible change.
- Empty list `[]` → skips API call, returns `hierarchical_document_tree` with `structured_payload=[]`.
- One block → skips API call, block gets `parent_id=None`.
- Multiple blocks with mocked API response → blocks get correct `parent_id` values.
- Duplicate `block_id` in input → each unique id appears exactly once in `structured_payload`.
- Block missing from the API's `relation_map` → `parent_id=None`, orphan warning added to `extraction_warnings`.
- API response has no `tool_use` block → raises `ValueError`.

---

## 6. Integration Tests

### 6.1 FastAPI Lifespan Strategy

The real `lifespan` in `api.py` calls `AsyncSqliteSaver.from_conn_string(...)` and optionally initialises Langfuse. Tests must not run this. The `api_client` fixture (§4.4) overrides `app.router.lifespan_context` with a lightweight replacement that injects a configurable `AsyncMock` graph and sets `langfuse=None`. `asgi-lifespan`'s `LifespanManager` drives the startup/shutdown hooks so `app.state` is populated before any request is made.

---

### 6.2 `tests/integration/test_api_health.py`

- `GET /` with `follow_redirects=False` → `307` redirect with `location: /docs`. The test must disable redirect-following; `httpx.AsyncClient` follows redirects by default and would land on `/docs`, hiding the 307.
- `GET /health` → `200`, body matches `HealthResponse` schema.
- `status == "ok"`, `model == MODEL`, `fallback_doc_type == FALLBACK_DOC_TYPE`.
- `supported_doc_types` is sorted alphabetically.
- `langfuse_enabled` is `False` (no Langfuse env vars set in CI).

---

### 6.3 `tests/integration/test_api_extract.py`

| Test | Setup | Expected |
|---|---|---|
| Valid PDF upload | — | `202`, body has `job_id` and `status="queued"` |
| Wrong content-type | send `text/plain` | `400` |
| File > 32 MB | send 33 MB body | `413` |
| Same file twice (no existing job) | two identical uploads | both `202`, same `job_id` |
| Same file, job queued, no force | pre-seed queued record | `202`, returns existing queued job without creating a new one |
| Same file, job running, no force | pre-seed running record | `202`, returns existing running job |
| Same file, job completed, no force | pre-seed completed record | `202`, returns existing completed job |
| Same file, job completed, `force=true` | pre-seed completed record | `202`, new `status="queued"` |
| Same file, job running, `force=true` | pre-seed running record | `409` |
| Same file, job queued, `force=true` | pre-seed queued record | `409` |

The "concurrent idempotent uploads" case is removed. A single-event-loop `asyncio.gather` does not exercise the actual race condition and would pass trivially without testing anything meaningful.

---

### 6.4 `tests/integration/test_api_jobs.py`

| Test | Setup | Expected |
|---|---|---|
| `GET /jobs/{id}` — exists | pre-seed job | `200`, correct fields |
| `GET /jobs/{bad-id}` — not found | — | `404` |
| `DELETE /jobs/{id}` — completed | pre-seed completed job; patch `Path.unlink` | `204`, job removed from store, `unlink` called |
| `DELETE /jobs/{bad-id}` — not found | — | `404` |
| `DELETE /jobs/{id}` — running | pre-seed running job | `409` |
| `DELETE /jobs/{id}` — queued | pre-seed queued job | `409` |

The DELETE test for file cleanup patches `pathlib.Path.unlink` rather than creating a real file. `api.py` calls `(_UPLOAD_DIR / f"{job_id}.pdf").unlink(missing_ok=True)` where `_UPLOAD_DIR` is an absolute path inside the source tree. Writing to that path during tests would pollute the working tree. Patching `Path.unlink` on the specific instance (or via `mocker.patch.object`) verifies that the call is made with `missing_ok=True` without touching the filesystem.

---

### 6.5 `tests/integration/test_api_runner.py` — `run_extraction` and `_resolve_input`

These test the background task directly, bypassing the HTTP layer. No HTTP client is needed; call `_resolve_input` and `run_extraction` as plain async functions.

**`_resolve_input`**

`_resolve_input` takes `graph` as a parameter, so no patching is needed — pass an `AsyncMock` graph configured to return the appropriate snapshot. A snapshot is an object with `.values` (dict) and `.next` (tuple).

```python
# helper used across all _resolve_input tests
def make_snapshot(values=None, next_nodes=()):
    snap = MagicMock()
    snap.values = values or {}
    snap.next = next_nodes
    return snap
```

- `force=True`, any snapshot → returns `{"file_path": file_path}`.
- `force=False`, `snapshot.values={}`, `snapshot.next=()` (never started) → returns `{"file_path": file_path}`.
- `force=False`, `snapshot.values={"some": "state"}`, `snapshot.next=("pending_node",)` (interrupted) → returns `None`.
- `force=False`, `snapshot.values={"some": "state"}`, `snapshot.next=()` (completed) → returns `{"file_path": file_path}`.

**`run_extraction`**

The mock graph needs:
- `stream`: an async generator that yields node-event dicts (e.g., `{"native_extractor": {...}}`).
- `aget_state`: `AsyncMock` returning a snapshot whose `.values` dict contains `hierarchical_document_tree`, `total_pages`, etc.

```python
async def _node_events(*args, **kwargs):
    yield {"native_extractor": {}}
    yield {"hierarchy_node": {}}

mock_graph.stream = _node_events
mock_graph.aget_state = AsyncMock(return_value=make_snapshot(
    values={
        "hierarchical_document_tree": {
            "document_type": "baseline_core",
            "extraction_warnings": [],
            "structured_payload": [],
        },
        "total_pages": 1,
    }
))
```

Test cases:

- **Happy path**: job transitions `queued → running → completed`; `job.result` equals the tree dict; `job.total_pages=1`; `job.document_type="baseline_core"`; `job.warnings=[]`; two events recorded in `job.events`; temp file deleted (assert `Path(file_path).exists() == False`).
- **Exception path**: `graph.stream` raises `RuntimeError("boom")` → `job.status="failed"`, `job.error="boom"`, temp file still deleted.
- **`langfuse=None`**: no `AttributeError` raised; `tracing_span` yields `None`; `span.update` is never called.

---

### 6.6 `tests/integration/test_graph_pipeline.py` — End-to-end Graph

These run the compiled `build_app(checkpointer=None)` graph with all external I/O patched.

**Patch targets (full module paths required):**
- `src.nodes.extractor_node.get_page_count`
- `src.nodes.extractor_node.hash_file`
- `src.nodes.classifier_node.AsyncAnthropic` (for `_classify`)
- `src.nodes.classifier_node.encode_pdf_async`
- `src.nodes.worker_node.AsyncAnthropic` (for `_call_api`)
- `src.nodes.worker_node.encode_pdf_async`
- `src.nodes.hierarchy_node.AsyncAnthropic` (for `_call_api`)

**Happy path (baseline_core, 1 page)**
1. `get_page_count` → `1`, `hash_file` → fixed hex string.
2. Classifier mock returns `"baseline_core"`.
3. Worker mock returns tool_use with 1 valid block.
4. Hierarchy mock returns `set_block_relations` with `parent_id=null`.
5. Stream graph from `{"file_path": "<minimal_pdf_path>"}`.
6. Assert final state has `hierarchical_document_tree.structured_payload` with 1 block carrying `parent_id=None`.

**Pioneer retry then success (2 pages)**

Both `pioneer_parser` and `parser_worker` nodes call the same `window_parser_node` function, which calls `_call_api` inside `src.nodes.worker_node`. Use `side_effect` on the `AsyncAnthropic` mock so successive calls return different responses:

```python
mock_client.messages.create = AsyncMock(side_effect=[
    invalid_tool_use_response,   # call 1: pioneer (will trigger retry)
    valid_tool_use_response,     # call 2: pioneer retry (passes validation)
    valid_tool_use_response,     # call 3: page 2 burst worker
])
```

1. Stream the graph and collect all emitted node-name events.
2. Assert the event sequence contains `"retry_node"` exactly once, then `"burst_dispatcher"`, then `"parser_worker"`. Verifies routing, not just final state.
3. Assert final state `extraction_warnings=[]`.

**Pioneer max-retry degradation (1 page)**
1. Worker mock always returns invalid blocks (all 3 retries fail).
2. Assert event sequence contains `"retry_node"` three times, then `"burst_dispatcher"`.
3. Assert final `extraction_warnings` contains the degradation message about page 1 failing validation.

---

## 7. Coverage Targets

| Module | Target | Notes |
|---|---|---|
| `src/state.py` | 100% | pure functions |
| `src/schema_registry.py` | 100% | |
| `src/edges.py` | 100% | |
| `src/utils/pdf_utils.py` | 100% | |
| `src/utils/tracing.py` | 100% | `langfuse=None` path in unit test; `langfuse` active path in `run_extraction` test |
| `src/extractors/page_counter.py` | 100% | |
| `src/api/jobs.py` | 100% | |
| `src/api/models.py` | 100% | |
| `src/graph.py` | ≥ 90% | |
| `src/nodes/*.py` | ≥ 85% | tenacity retry decorator internals not covered |
| `src/api/runner.py` | ≥ 90% | both `_resolve_input` paths + happy/fail `run_extraction` paths covered explicitly |
| `api.py` | ≥ 75% | lifespan is overridden in tests; its real I/O lines are not exercised |

Coverage numbers alone are insufficient for `src/api/runner.py` — the critical paths (`_resolve_input` resume branch, exception handler, Langfuse span) must each have an explicit named test case regardless of whether the line count target is met.

---

## 8. Implementation Order

1. **Infrastructure** — dev deps, `[tool.pytest.ini_options]`, `conftest.py` with all fixtures.
2. **Pure-logic units** — `test_state`, `test_schema_registry`, `test_pdf_utils`, `test_page_counter`, `test_models`.
3. **Edge and graph** — `test_edges`, `test_graph`.
4. **Node units** — `test_extractor_node`, `test_retry_node`, `test_hierarchy_node`, `test_worker_node`, `test_classifier_node`.
5. **API integration** — `test_api_health`, `test_api_jobs`, `test_api_extract`, `test_api_runner`.
6. **Pipeline integration** — `test_graph_pipeline`.

Each step should leave the suite green before moving to the next.

---

## 9. Mock Strategy

| Dependency | Patch target (full path) |
|---|---|
| `AsyncAnthropic` in classifier | `src.nodes.classifier_node.AsyncAnthropic` |
| `AsyncAnthropic` in worker | `src.nodes.worker_node.AsyncAnthropic` |
| `AsyncAnthropic` in hierarchy | `src.nodes.hierarchy_node.AsyncAnthropic` |
| `encode_pdf_async` in classifier | `src.nodes.classifier_node.encode_pdf_async` |
| `encode_pdf_async` in worker | `src.nodes.worker_node.encode_pdf_async` |
| `get_page_count` | `src.nodes.extractor_node.get_page_count` |
| `hash_file` | `src.nodes.extractor_node.hash_file` |
| LangGraph checkpointer | `checkpointer=None` passed to `build_app()` |
| Langfuse | `app.state.langfuse = None` in override lifespan |
| FastAPI lifespan I/O | `app.router.lifespan_context` override + `asgi-lifespan` |
| File I/O | `tmp_path` pytest fixture |
| `ANTHROPIC_API_KEY` | session-autouse fixture sets `os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake"` |

No real HTTP calls to Anthropic; no real SQLite database created during tests.
