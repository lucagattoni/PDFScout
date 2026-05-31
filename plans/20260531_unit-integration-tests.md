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
    "pytest-cov>=6.0",
    "httpx>=0.27",          # AsyncClient for FastAPI tests
    "pypdf>=6.0.0",         # already in prod; used to build minimal test PDFs
]
```

### 2.2 `pytest` Configuration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
asyncio_mode    = "auto"
testpaths       = ["tests"]
addopts         = "--cov=src --cov=api --cov-report=term-missing"
```

---

## 3. Directory Layout

```
tests/
├── conftest.py                         # shared fixtures
├── fixtures/
│   └── minimal.pdf                     # programmatically generated 1-page PDF
├── unit/
│   ├── test_state.py
│   ├── test_config.py
│   ├── test_schema_registry.py
│   ├── test_edges.py
│   ├── test_pdf_utils.py
│   ├── test_page_counter.py
│   ├── test_jobs.py
│   ├── test_models.py
│   ├── test_graph.py
│   └── nodes/
│       ├── test_extractor_node.py
│       ├── test_classifier_node.py
│       ├── test_worker_node.py
│       ├── test_retry_node.py
│       └── test_hierarchy_node.py
└── integration/
    ├── test_api_health.py
    ├── test_api_extract.py
    ├── test_api_jobs.py
    └── test_graph_pipeline.py
```

---

## 4. Shared Fixtures (`tests/conftest.py`)

| Fixture | Scope | Description |
|---|---|---|
| `minimal_pdf_bytes` | session | Raw bytes of a valid 1-page PDF (written with `pypdf`) |
| `minimal_pdf_path` | function | Writes `minimal_pdf_bytes` to a tmp file; yields path string |
| `sample_block` | function | One well-formed extracted block dict (page 1) |
| `sample_state` | function | Minimal `PDFParserState`-compatible dict for node tests |
| `api_client` | function | `httpx.AsyncClient` against a `LifespanManager`-wrapped FastAPI app with mocked graph |
| `mock_anthropic` | function | `AsyncMock` of `AsyncAnthropic` with configurable `.messages.create` return values |

The `minimal.pdf` fixture is generated at session start using `pypdf`'s writer API so tests never rely on a committed binary file.

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

### 5.2 `tests/unit/test_config.py` — Constants

- `SUPPORTED_DOC_TYPES` is a set containing `"invoice"` and `"scientific_paper"`.
- `FALLBACK_DOC_TYPE` is `"baseline_core"`.
- `CONCURRENCY_LIMIT` is a positive integer.
- `COLUMN_BUCKET_PX` is a positive integer.

---

### 5.3 `tests/unit/test_schema_registry.py` — SchemaRegistry

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

### 5.4 `tests/unit/test_edges.py` — `pioneer_validation_route`

All tests use a state dict with `document_type="baseline_core"` and pre-set blocks/retry counts.

| Scenario | retry_count | blocks | Expected return |
|---|---|---|---|
| No blocks extracted | 0 | `[]` | `"retry_node"` |
| No blocks extracted, max retries | 3 | `[]` | `"burst_dispatcher"` |
| Blocks pass validation | 0 | valid blocks | `"burst_dispatcher"` |
| Blocks fail validation | 1 | invalid blocks | `"retry_node"` |
| Blocks fail validation, max retries | 3 | invalid blocks | `"burst_dispatcher"` |

---

### 5.5 `tests/unit/test_pdf_utils.py` — `hash_file`, `encode_pdf_async`

**`hash_file`**
- Returns a 64-character hexadecimal string (SHA-256).
- Same file hashed twice yields the same digest.
- Different content yields a different digest.

**`encode_pdf_async`**
- Returns a non-empty string.
- Decoded bytes match the original file content.

---

### 5.6 `tests/unit/test_page_counter.py` — `get_page_count`

- Valid 1-page PDF returns `1`.
- Valid 3-page PDF returns `3`.
- Encrypted PDF raises `ValueError` with `"encrypted"` in the message.

*Encrypted PDF fixture: write an encrypted PDF programmatically with `pypdf`'s `PdfWriter.encrypt()`.*

---

### 5.7 `tests/unit/nodes/test_extractor_node.py` — `native_extractor_node`

- Normal 2-page PDF: result contains `pdf_hash` (64-char hex), `total_pages=2`, `current_page=1`, `retry_count=0`, `last_validation_error=None`, `extracted_flat_blocks=None`.
- Zero-page scenario (mock `get_page_count` returning `0`): raises `ValueError` containing `"zero pages"`.

---

### 5.8 `tests/unit/nodes/test_classifier_node.py` — `classifier_node`

Mock `AsyncAnthropic.messages.create` to control Claude's response text.

- Response text `"invoice"` → `document_type="invoice"`, schema loaded correctly.
- Response text `"scientific_paper"` → `document_type="scientific_paper"`.
- Response text `"unknown_garbage"` → `document_type=FALLBACK_DOC_TYPE`.
- Response text with leading/trailing whitespace → stripped and matched.

---

### 5.9 `tests/unit/nodes/test_worker_node.py` — `window_parser_node`

Mock `AsyncAnthropic.messages.create`.

- Response contains `tool_use` block with `blocks=[block]` → returns `{"extracted_flat_blocks": [block]}`.
- Response contains **no** `tool_use` block → raises `ValueError` containing `"no tool_use block"`.
- State has `last_validation_error="some error"` → the error text appears in the request content.
- State has `last_validation_error=None` → no validation error content block added.

---

### 5.10 `tests/unit/nodes/test_retry_node.py` — `retry_incrementor_node`

- `extracted_flat_blocks=[]` and `current_page=1` → `error_detail` mentions "No blocks".
- Valid-structured but schema-failing blocks → `error_detail` contains the field path.
- `retry_count` increments by exactly 1 each call.
- `extracted_flat_blocks` is reset to `None` in output.
- `last_validation_error` string contains attempt number in `"(attempt X/3)"` form.

---

### 5.11 `tests/unit/nodes/test_hierarchy_node.py`

**`geometric_pre_sorter`**
- Single block returns unchanged (wrapped in list).
- Three blocks on different pages sorted ascending by page.
- Two blocks on same page, same column bucket, sorted by `ymin`.
- Two blocks on same page, different `xmin` bucket, sorted by column bucket.

**`layout_hierarchy_agent_node`**
- Zero blocks: skips API, returns `hierarchical_document_tree` with `structured_payload=[]`.
- One block: skips API, block gets `parent_id=None`.
- Multiple blocks: mocked API returns full `relations` list → blocks get correct `parent_id`.
- Duplicate `block_id` in input: deduplicated, each unique block appears exactly once.
- Block missing from `relation_map`: promoted to root (`parent_id=None`), orphan warning added.
- API returns response with **no** `tool_use` block → raises `ValueError`.

---

### 5.12 `tests/unit/test_graph.py` — Graph Topology

**`burst_dispatcher_node`**
- `retry_count=0` → returns `{}`.
- `retry_count=3` → returns dict with `extraction_warnings` containing the degradation message.

**`dispatch_pages`**
- `total_pages=1` → returns string `"hierarchy_node"`.
- `total_pages=3` → returns list of two `Send` objects for pages 2 and 3.
- Each `Send` object targets `"parser_worker"` and has `current_page` set correctly.

**`build_app`**
- `build_app(checkpointer=None)` compiles without raising.
- Compiled graph exposes node names: `native_extractor`, `classifier`, `pioneer_parser`, `retry_node`, `burst_dispatcher`, `parser_worker`, `hierarchy_node`.

---

### 5.13 `tests/unit/test_jobs.py` — JobRecord

- New `JobRecord` has `status="queued"` by default.
- `completed_at`, `result`, `error`, `document_type`, `total_pages` default to `None`.
- `warnings` and `events` default to empty lists.

---

### 5.14 `tests/unit/test_models.py` — Pydantic Models

**`JobResponse.from_record`**
- All 10 fields from `JobRecord` map to their counterpart on `JobResponse`.
- `warnings=[]` and `events=[]` by default.

**`HealthResponse`**
- Instantiates without error with all required fields.

---

## 6. Integration Tests

All FastAPI integration tests use `httpx.AsyncClient` with `base_url="http://test"` and `app` wrapped in a lifespan that replaces the real graph with a `MagicMock`.

### 6.1 `tests/integration/test_api_health.py`

- `GET /health` → `200`, body matches `HealthResponse` schema.
- `status == "ok"`, `model == MODEL`, `fallback_doc_type == FALLBACK_DOC_TYPE`.
- `supported_doc_types` is sorted alphabetically.

---

### 6.2 `tests/integration/test_api_extract.py`

| Test | Method | Expected |
|---|---|---|
| Valid PDF upload | `POST /extract` | `202`, body has `job_id` and `status="queued"` |
| Wrong content-type | `POST /extract` | `400` |
| File > 32 MB | `POST /extract` | `413` |
| Same file twice | `POST /extract` × 2 | Second call returns `202` with **same** `job_id` |
| Same file twice, first is completed, no force | `POST /extract` | Returns existing completed job |
| Same file twice, first is completed, `force=true` | `POST /extract?force=true` | New job created, `status="queued"` |
| Upload when job is running, `force=true` | `POST /extract?force=true` | `409` |
| Concurrent idempotent uploads | `POST /extract` × N same file | All return same `job_id` |

---

### 6.3 `tests/integration/test_api_jobs.py`

| Test | Method | Expected |
|---|---|---|
| Get existing queued job | `GET /jobs/{id}` | `200`, correct fields |
| Get non-existent job | `GET /jobs/bad-id` | `404` |
| Delete completed job | `DELETE /jobs/{id}` | `204`, job removed from store |
| Delete non-existent job | `DELETE /jobs/bad-id` | `404` |
| Delete running job | `DELETE /jobs/{id}` | `409` |
| Delete queued job | `DELETE /jobs/{id}` | `409` |

---

### 6.4 `tests/integration/test_graph_pipeline.py` — End-to-end Graph

These tests run the compiled `build_app(checkpointer=None)` graph against real in-memory state but with **mocked Anthropic API calls** (`AsyncMock`).

**Happy path (baseline_core, 1 page)**
1. Patch `get_page_count` → `1`.
2. Patch `classifier_node._classify` → `"baseline_core"`.
3. Patch `worker_node._call_api` → returns tool_use block with 2 valid blocks.
4. Patch `hierarchy_node._call_api` → returns `set_block_relations` with correct relation list.
5. Stream the graph from `{"file_path": "<minimal_pdf_path>"}`.
6. Assert final state has `hierarchical_document_tree` with `structured_payload` containing the 2 blocks, each with `parent_id`.

**Pioneer retry then success (3 pages)**
1. First `window_parser_node` call returns invalid blocks → `retry_node` fires.
2. Second call returns valid blocks → `burst_dispatcher` fires → pages 2–3 dispatched.
3. Assert `retry_count` was 1 in the final snapshot, `extraction_warnings=[]`.

**Pioneer max-retry degradation**
1. `window_parser_node` always returns invalid blocks.
2. After 3 retries, graph routes to `burst_dispatcher` with degradation warning.
3. Final state has `extraction_warnings` containing the degradation message.

---

## 7. Coverage Targets

| Module | Target |
|---|---|
| `src/state.py` | 100% |
| `src/config.py` | 100% |
| `src/schema_registry.py` | 100% |
| `src/edges.py` | 100% |
| `src/utils/pdf_utils.py` | 100% |
| `src/extractors/page_counter.py` | 100% |
| `src/api/jobs.py` | 100% |
| `src/api/models.py` | 100% |
| `src/graph.py` | ≥ 90% |
| `src/nodes/*.py` | ≥ 85% |
| `src/api/runner.py` | ≥ 80% |
| `api.py` | ≥ 80% |
| **Overall** | **≥ 85%** |

---

## 8. Implementation Order

1. **Infrastructure** — add dev deps to `pyproject.toml`, add `[tool.pytest.ini_options]`, create `tests/conftest.py` with all fixtures, generate `tests/fixtures/minimal.pdf`.
2. **Pure-logic units** — `test_state`, `test_config`, `test_schema_registry`, `test_pdf_utils`, `test_page_counter`, `test_jobs`, `test_models`.
3. **Edge and graph** — `test_edges`, `test_graph`.
4. **Node units** — `test_extractor_node`, `test_retry_node`, `test_hierarchy_node` (pure parts), `test_worker_node`, `test_classifier_node`.
5. **API integration** — `test_api_health`, `test_api_jobs`, `test_api_extract`.
6. **Pipeline integration** — `test_graph_pipeline`.

Each step should leave the suite green before moving to the next.

---

## 9. Mock Strategy

| Dependency | Mock approach |
|---|---|
| `anthropic.AsyncAnthropic` | `pytest-mock` `mocker.patch` / `AsyncMock` |
| `src.utils.pdf_utils.encode_pdf_async` | `AsyncMock` returning fixed base64 string |
| `src.extractors.page_counter.get_page_count` | `mocker.patch` returning int |
| `langgraph` checkpointer | `checkpointer=None` (in-memory mode) |
| Langfuse | patched to `None` / no-op |
| File I/O | `tmp_path` pytest fixture; never write to the real project tree |

No real HTTP calls; no `ANTHROPIC_API_KEY` needed in CI.
