# Migration Plan: Replace pdfplumber with Claude PDF Chat + Lightweight Page Counter

**Date:** 2026-05-30  
**Branch:** `main-YyDgA`  
**Scope:** Complete replacement of `pdfplumber`-based text extraction with Claude's native PDF vision API. A single lightweight library (`pypdf`) is retained for the sole purpose of counting pages before API dispatch.

---

## 1. Motivation

The current architecture uses `pdfplumber` to extract raw text and word-level bounding boxes, then feeds that extracted content to Claude as a JSON payload. This approach has two structural problems:

1. **Scanned / image-only PDFs produce empty text** — pdfplumber cannot read pixels, so the entire extraction pipeline silently receives empty strings for image-based documents.
2. **pdfplumber is the wrong tool for the job** — we were using it as a text pre-processor for a vision model. Claude's PDF Chat API renders each page as an image *and* extracts text natively, achieving far higher fidelity on complex layouts, multi-column documents, and scanned content.

Claude's PDF Chat is fully visual: every page is processed as both an image and as extracted text simultaneously. This makes `pdfplumber`'s role entirely redundant.

---

## 2. Claude PDF Chat API — Key Facts

Source: https://platform.claude.com/docs/en/build-with-claude/pdf-support

| Property | Value |
|---|---|
| Supported input methods | base64-encoded PDF, URL reference, Files API `file_id` |
| Max request size | 32 MB (entire request payload) |
| Max pages per request | 600 (100 for 200k-context models) |
| Encryption/passwords | Not supported — PDFs must be unencrypted |
| Scanned PDFs | Fully supported via vision |
| Models | All active Claude models |
| Prompt caching | Supported — `cache_control: ephemeral` on the `document` block |

**How it works internally:** The API converts each PDF page into an image and also extracts the embedded text. Claude receives both representations simultaneously, enabling understanding of visual elements (charts, diagrams, tables, layout structure) alongside text content.

**API message shape:**

```python
{
    "type": "document",
    "source": {
        "type": "base64",
        "media_type": "application/pdf",
        "data": "<base64-encoded-pdf>"
    },
    "cache_control": {"type": "ephemeral"}   # optional — enables prompt caching
}
```

**Prompt caching upgrade:** Previously `cache_control` was applied to a `text` block containing the `native_text_metadata` JSON string. After migration it is applied directly to the `document` block containing the encoded PDF. This is strictly better — Claude caches its actual processed representation of the PDF (image + text per page), not a secondary text extraction of it.

---

## 3. Page-Count Library Evaluation

We need a library for exactly one thing: **determining how many pages a PDF has** before dispatching Claude API calls. The rest of the extraction pipeline moves to Claude.

### Candidates Evaluated

| Library | Wheel Size | Dependencies | License | Maintained | Page Count API | Encrypted PDF | Corrupt PDF |
|---|---|---|---|---|---|---|---|
| **pypdf** | 343.9 kB | None (pure Python) | BSD-3-Clause | ✅ Active (v6.12.2, May 2026) | `len(PdfReader(path).pages)` | Detects, partial decrypt | Basic error |
| **pikepdf** | 23.7 MB | None (wraps C++ qpdf) | MPL-2.0 | ✅ Active (v10.7.2) | `len(Pdf.open(path).pages)` | Full AES-256/RC4 | ✅ Auto-repairs |
| **pypdfium2** | 2.8–4.4 MB | None | BSD-3/Apache-2 | ✅ Active (v5.8.0, May 2026) | `len(PdfDocument(path))` | Good | Good |
| **pymupdf** | Platform-dep | None | AGPL v3 ⚠️ | ✅ Active | `len(pymupdf.open(path))` | Good | Good |
| **pdfminer.six** | 6.6 MB | None | MIT | ✅ Active | Requires full page iteration | Limited | Limited |
| **pdfrw** | 69.5 kB | None | MIT | ❌ Dead (2017) | `len(PdfReader(path).pages)` | Outdated | Minimal |

### Detailed Assessment

**pypdf — Recommended ✅**

Pros:
- Smallest viable wheel at 343.9 kB — roughly 40× lighter than pdfplumber's full dependency tree
- Zero external dependencies; pure Python install with no native compilation step
- BSD-3-Clause license — no commercial or copyleft restrictions
- Actively maintained under the py-pdf organization
- Single-line page count: `len(PdfReader(path).pages)`
- Detects encrypted PDFs via `reader.is_encrypted` — allows early rejection with a clean error message before a wasted API call

Cons:
- Does not auto-repair corrupted PDFs — raises an exception on severely malformed files
- Does not fully decrypt all encryption schemes

Assessment of cons: Both cons are acceptable here. A corrupt PDF would fail at Claude's API level anyway. Encrypted PDFs are unsupported by Claude PDF Chat regardless (`"Format: Standard PDF (no passwords/encryption)"`), so early rejection at the page-count stage is desirable, not a weakness.

**pikepdf — Runner-up**

Best robustness for corrupted files. 23.7 MB wheel and C++ native build. Justified if the user base is expected to feed malformed or repaired PDFs regularly. MPL-2.0 license is permissive.

**pymupdf — Excluded**

AGPL v3 license is a hard constraint for any future commercial use of this project. Excluded.

**pdfrw — Excluded**

Unmaintained since 2017. Incompatible with modern Python and PDF standards. Excluded.

### Decision

**Use `pypdf`.** It is the lightest, zero-dependency, actively maintained option that fully meets the single requirement: reading the page count of a standard PDF file.

---

## 4. Architecture Changes

### 4.1 What Is Removed

| Component | Reason |
|---|---|
| `pdfplumber` package | Replaced entirely by Claude PDF Chat |
| `pydantic` package | The only Pydantic models (`NativeWord`, `NativePageMetadata`) live in `src/extractors/base.py`. That file is deleted. After migration, no code imports from pydantic. |
| `src/extractors/base.py` | `BaseNativeExtractor`, `NativeWord`, `NativePageMetadata` Pydantic models are no longer needed |
| `src/extractors/plumber_engine.py` | `PlumberExtractor` is no longer needed |
| `PDFParserState.native_text_metadata` | Was the pdfplumber output; no longer computed or used |

### 4.2 What Is Added

| Component | Description |
|---|---|
| `pypdf` package | Page counting + encrypted PDF detection only |
| `src/extractors/page_counter.py` | Thin wrapper: calls `pypdf.PdfReader`, raises on encrypted PDFs |
| `coordinates` schema `description` field | All three JSON schemas gain an explicit `"description": "Bounding box as [ymin, xmin, ymax, xmax] integers in page coordinate space."` on the `coordinates` property. Previously the order was enforced in pdfplumber code; now it must be encoded in the schema so Claude generates coordinates in the expected order for `geometric_pre_sorter`. |

### 4.3 What Changes (but stays)

| Component | Old behaviour | New behaviour |
|---|---|---|
| `native_extractor_node` | Opens PDF with pdfplumber, extracts words + coordinates for all pages | Opens PDF with pypdf for page count and encrypted-PDF guard; computes hash. No text extraction. No base64 encoding. |
| `classifier_node` | Sends `first_page_text` (4000 chars of pdfplumber output) to Claude | Reads `file_path` from state, encodes to base64, sends PDF as `document` block |
| `worker_node` | Sends `native_text_metadata` JSON as a `text` block with `cache_control`; imports `json` | Reads `file_path` from state, encodes to base64, sends PDF as `document` block with `cache_control: ephemeral`. `import json` is removed. |

**Why workers re-read from `file_path` rather than storing `pdf_base64` in state:**

Storing `pdf_base64` in `PDFParserState` would cause `{**state, ...}` in `dispatch_pages` to copy the full encoded PDF into every `Send` message — one copy per page. A 10 MB PDF becomes ~13 MB of base64 × N-1 copies simultaneously in memory, plus each copy is checkpointed to SQLite. Reading from `file_path` (always present in state) per worker call eliminates this entirely at the cost of one extra disk read per API call, which is negligible for a local file.

### 4.4 What Stays Unchanged

- `schemas/` — three JSON Schema files (gains `description` on `coordinates` only)
- `src/config.py` — unchanged
- `src/state.py` — one field removed (`native_text_metadata`); no field added
- `src/schema_registry.py` — unchanged
- `src/edges.py` — unchanged
- `src/nodes/retry_node.py` — unchanged
- `src/nodes/hierarchy_node.py` — unchanged (`geometric_pre_sorter` still valid; coordinate order is now enforced via the schema description)
- `src/graph.py` — unchanged
- `main.py` — unchanged

---

## 5. Revised State Definition

```python
class PDFParserState(TypedDict):
    # Static Input
    file_path: str
    pdf_hash: str
    total_pages: int
    # native_text_metadata REMOVED — pdfplumber extraction eliminated

    # Polymorphic Blueprint Configuration
    document_type: str
    target_json_schema: dict[str, Any]

    # State Iteration Engine (pioneer page only)
    current_page: int
    retry_count: int
    last_validation_error: str | None

    # Aggregate Buffers
    extracted_flat_blocks: Annotated[list[dict[str, Any]], merge_flat_blocks]
    extraction_warnings: Annotated[list[str], merge_warnings]
    hierarchical_document_tree: dict[str, Any] | None
```

---

## 6. File-by-File Implementation Plan

### Step 1 — Update dependencies

```bash
uv remove pdfplumber pydantic
uv add "pypdf>=6.0.0"
```

`pyproject.toml` diff:
```toml
# Remove:
"pdfplumber>=0.11.9",
"pydantic>=2.13.4",

# Add:
"pypdf>=6.0.0",
```

---

### Step 2 — Add coordinate order description to all three schemas

Add `"description"` to the `coordinates` property in `schemas/invoice.json`, `schemas/scientific_paper.json`, and `schemas/baseline_core.json`:

```json
"coordinates": {
    "type": "array",
    "description": "Bounding box as [ymin, xmin, ymax, xmax] integers in page coordinate space.",
    "items": { "type": "integer" },
    "minItems": 4,
    "maxItems": 4
}
```

This is required because `geometric_pre_sorter` in `hierarchy_node.py` unpacks `ymin, xmin, _, _ = b["bbox"]["coordinates"]`. Previously this order was enforced by pdfplumber's coordinate mapping code. After migration, Claude generates the coordinates and must be explicitly told the expected format.

---

### Step 3 — Replace `src/extractors/` contents

**Delete:**
- `src/extractors/base.py`
- `src/extractors/plumber_engine.py`

**Create: `src/extractors/page_counter.py`**

```python
from pypdf import PdfReader


def get_page_count(file_path: str) -> int:
    reader = PdfReader(file_path)
    if reader.is_encrypted:
        raise ValueError(
            f"PDF at '{file_path}' is encrypted. "
            "Claude PDF Chat does not support password-protected PDFs."
        )
    return len(reader.pages)
```

`src/extractors/__init__.py` remains empty.

---

### Step 4 — Update `src/state.py`

Remove `native_text_metadata`. No field is added.

```python
class PDFParserState(TypedDict):
    file_path: str
    pdf_hash: str
    total_pages: int

    document_type: str
    target_json_schema: dict[str, Any]

    current_page: int
    retry_count: int
    last_validation_error: str | None

    extracted_flat_blocks: Annotated[list[dict[str, Any]], merge_flat_blocks]
    extraction_warnings: Annotated[list[str], merge_warnings]
    hierarchical_document_tree: dict[str, Any] | None
```

---

### Step 5 — Rewrite `src/nodes/extractor_node.py`

```python
import hashlib
from typing import Any
from src.extractors.page_counter import get_page_count


def _hash_file(file_path: str) -> str:
    """Chunked SHA-256 — avoids loading the entire file into memory."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def native_extractor_node(state: dict[str, Any]) -> dict[str, Any]:
    file_path = state["file_path"]
    pdf_hash = _hash_file(file_path)
    total_pages = get_page_count(file_path)  # raises on encrypted PDFs

    if total_pages == 0:
        raise ValueError(
            f"PDF at '{file_path}' yielded zero pages. "
            "The file may be empty or corrupted."
        )

    return {
        "pdf_hash": pdf_hash,
        "total_pages": total_pages,
        "current_page": 1,
        "retry_count": 0,
        "last_validation_error": None,
        "extracted_flat_blocks": [],
        "extraction_warnings": []
    }
```

---

### Step 6 — Rewrite `src/nodes/classifier_node.py`

Reads `file_path` from state and encodes on the fly. Replaces first-page text approach with a full PDF document block.

```python
import base64
import os
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import MODEL, SUPPORTED_DOC_TYPES, FALLBACK_DOC_TYPE
from src.schema_registry import SchemaRegistry


def _encode_pdf(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _classify(client: AsyncAnthropic, pdf_base64: str) -> str:
    response = await client.messages.create(
        model=MODEL,
        max_tokens=10,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_base64
                    }
                },
                {
                    "type": "text",
                    "text": (
                        f"Classify this document. Return ONLY one token from "
                        f"{sorted(SUPPORTED_DOC_TYPES)}."
                    )
                }
            ]
        }]
    )
    return response.content[0].text.strip().lower()


async def classifier_node(state: dict) -> dict:
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    pdf_base64 = _encode_pdf(state["file_path"])
    doc_type = await _classify(client, pdf_base64)

    if doc_type not in SUPPORTED_DOC_TYPES:
        doc_type = FALLBACK_DOC_TYPE

    schema, _ = SchemaRegistry().get_schema_and_tool(doc_type)
    return {"document_type": doc_type, "target_json_schema": schema}
```

---

### Step 7 — Rewrite `src/nodes/worker_node.py`

Reads `file_path` from state, encodes on the fly. Removes `import json` (was only used to serialize `native_text_metadata`). Moves `cache_control: ephemeral` from the old text block to the document block.

```python
import asyncio
import base64
import os
from typing import Any
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import MODEL, CONCURRENCY_LIMIT
from src.schema_registry import SchemaRegistry

_semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)


def _encode_pdf(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def _call_api(client: AsyncAnthropic, messages: list, tool_definition: dict) -> Any:
    return await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        temperature=0.0,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": tool_definition["name"]},
        messages=messages
    )


async def window_parser_node(state: dict[str, Any]) -> dict[str, Any]:
    async with _semaphore:
        client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        current_page = state["current_page"]
        _, tool_definition = SchemaRegistry().get_schema_and_tool(state["document_type"])
        pdf_base64 = _encode_pdf(state["file_path"])

        content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_base64
                },
                "cache_control": {"type": "ephemeral"}
            },
            {
                "type": "text",
                "text": (
                    f"CRITICAL TASK: Extract structure elements EXCLUSIVELY located on physical "
                    f"Page {current_page}. Coordinates must follow [ymin, xmin, ymax, xmax] order. "
                    f"Use the tool '{tool_definition['name']}' to return structured data matching "
                    f"the schema parameters."
                )
            }
        ]

        if state.get("last_validation_error"):
            content.append({
                "type": "text",
                "text": (
                    f"PREVIOUS VALIDATION ERROR:\n{state['last_validation_error']}\n"
                    f"Fix the schema alignment issue in your response."
                )
            })

        response = await _call_api(client, [{"role": "user", "content": content}], tool_definition)
        tool_block = next(b for b in response.content if b.type == "tool_use")
        return {"extracted_flat_blocks": tool_block.input.get("blocks", [])}
```

Note: the coordinate order reminder (`Coordinates must follow [ymin, xmin, ymax, xmax] order.`) is added to the task prompt to reinforce the schema description, since `geometric_pre_sorter` depends on this ordering.

---

## 7. Dependency Diff

| Package | Before | After | Reason |
|---|---|---|---|
| `pdfplumber` | ≥ 0.11.9 | **Removed** | Replaced by Claude PDF Chat |
| `pydantic` | ≥ 2.13.4 | **Removed** | Only Pydantic models were `NativeWord`/`NativePageMetadata` in the deleted extractor files; zero remaining usage |
| `pypdf` | — | ≥ 6.0.0 | Page count + encrypted PDF detection only |
| `langgraph` | ≥ 1.2.2 | unchanged | |
| `langgraph-checkpoint-sqlite` | ≥ 3.1.0 | unchanged | |
| `anthropic` | ≥ 0.105.2 | unchanged | |
| `jsonschema` | ≥ 4.26.0 | unchanged | |
| `tenacity` | ≥ 9.1.4 | unchanged | |

`pdfplumber` pulls in `pdfminer.six`, `Pillow`, `pypdfium2`, `cryptography`, and `cffi`. Removing it alongside `pydantic` significantly reduces the install footprint.

---

## 8. Limitations & Known Constraints (Post-Migration)

| Constraint | Detail |
|---|---|
| Encrypted PDFs | Not supported by Claude PDF Chat. `pypdf`'s `is_encrypted` check in `page_counter.py` gives an early, clean error before wasting an API call. |
| Max request size | 32 MB total payload. PDFs approaching this limit should use the Files API (upload once → reference by `file_id`) instead of per-call base64 encoding. |
| Max pages | 600 per request (100 for 200k-context models). `native_extractor_node` guards against zero pages; a `total_pages > 600` guard should be added for very large documents. |
| Disk reads per worker | Each `classifier_node` and `window_parser_node` call reads and encodes the full PDF file from disk. For local files this is negligible. For network-mounted or slow storage, consider the Files API upgrade path. |
| Cache TTL | Anthropic prompt cache TTL remains 5 minutes. No change from before. |
| Scanned PDFs | Fully supported — this is the primary motivation for the migration. |

---

## 9. Files API Upgrade Path (Future)

For workflows involving large PDFs or repeated analysis of the same document, the Files API eliminates per-request encoding overhead:

1. Upload PDF once in `native_extractor_node` → receive `file_id`
2. Store `file_id` in state instead of re-reading from disk
3. All nodes reference `{"type": "file", "file_id": file_id}` in the `document` source
4. Requires `betas=["files-api-2025-04-14"]` header on messages

This is a clean follow-on change after the base64 migration stabilizes.

---

## 10. Execution Order

1. `uv remove pdfplumber pydantic && uv add "pypdf>=6.0.0"`
2. Update `pyproject.toml`
3. Add `"description"` to `coordinates` in `schemas/invoice.json`, `schemas/scientific_paper.json`, `schemas/baseline_core.json`
4. Delete `src/extractors/base.py` and `src/extractors/plumber_engine.py`
5. Create `src/extractors/page_counter.py`
6. Update `src/state.py` — remove `native_text_metadata`
7. Rewrite `src/nodes/extractor_node.py`
8. Rewrite `src/nodes/classifier_node.py`
9. Rewrite `src/nodes/worker_node.py`
10. Run import check: `uv run python -c "from src.graph import build_app; build_app()"`
11. Confirm zero pydantic imports: `grep -r "pydantic" src/` should return empty
12. Run schema validation smoke test
13. Run end-to-end test with a real PDF (text-based + scanned)
14. Verify `cache_read_input_tokens` on burst page invocations
15. Update `README.md` — remove pdfplumber from Limitations, replace with Claude PDF Chat architecture description
