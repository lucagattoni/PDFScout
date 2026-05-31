import os
from contextlib import asynccontextmanager
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


@pytest.fixture(autouse=True, scope="session")
def set_test_env():
    os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake"
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "")
    os.environ.setdefault("LANGFUSE_SECRET_KEY", "")


@pytest.fixture(autouse=True)
def clear_jobs_store():
    yield
    from src.api.jobs import jobs
    jobs.clear()


@pytest.fixture(scope="session")
def minimal_pdf_bytes() -> bytes:
    from pypdf import PdfWriter

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


async def _empty_stream(*args, **kwargs):
    if False:
        yield


@pytest.fixture
def mock_graph():
    graph = MagicMock()
    graph.stream = _empty_stream
    snapshot = MagicMock()
    snapshot.values = {}
    snapshot.next = ()
    graph.aget_state = AsyncMock(return_value=snapshot)
    return graph


@pytest.fixture
async def api_client(mock_graph):
    import api as app_module

    original_lifespan = app_module.app.router.lifespan_context

    @asynccontextmanager
    async def override_lifespan(app):
        import api as _api_mod
        _api_mod._UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        app.state.graph = mock_graph
        app.state.langfuse = None
        yield

    app_module.app.router.lifespan_context = override_lifespan
    try:
        from asgi_lifespan import LifespanManager

        async with LifespanManager(app_module.app) as manager:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=manager.app),
                base_url="http://test",
            ) as client:
                yield client
    finally:
        app_module.app.router.lifespan_context = original_lifespan


@pytest.fixture
def sample_block():
    return {
        "block_id": "blk-001",
        "type": "paragraph",
        "text": "Hello world.",
        "bbox": {
            "page_number": 1,
            "coordinates": [100, 50, 200, 80],
        },
        "is_continued": False,
        "metadata": {},
    }


@pytest.fixture
def sample_state(minimal_pdf_path):
    return {
        "file_path": minimal_pdf_path,
        "pdf_hash": "a" * 64,
        "total_pages": 1,
        "document_type": "baseline_core",
        "target_json_schema": {},
        "current_page": 1,
        "retry_count": 0,
        "last_validation_error": None,
        "extracted_flat_blocks": [],
        "extraction_warnings": [],
        "hierarchical_document_tree": None,
    }
