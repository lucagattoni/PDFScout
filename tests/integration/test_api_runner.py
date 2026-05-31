from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.jobs import JobRecord, jobs
from src.api.runner import _resolve_input, run_extraction


def make_snapshot(values=None, next_nodes=()):
    snap = MagicMock()
    snap.values = values or {}
    snap.next = next_nodes
    return snap


def _make_graph_with_stream(events: list, final_snapshot):
    graph = MagicMock()

    async def _stream(*args, **kwargs):
        for event in events:
            yield event

    graph.stream = _stream
    graph.aget_state = AsyncMock(return_value=final_snapshot)
    return graph


def _pre_seed_job(job_id: str, file_name: str = "test.pdf") -> JobRecord:
    record = JobRecord(
        job_id=job_id, file_name=file_name, created_at=datetime.now(timezone.utc)
    )
    jobs[job_id] = record
    return record


class TestResolveInput:
    async def test_force_true_always_fresh(self):
        graph = MagicMock()
        graph.aget_state = AsyncMock(return_value=make_snapshot(values={"x": 1}, next_nodes=("node",)))
        result = await _resolve_input(graph, "/some/file.pdf", {}, force=True)
        assert result == {"file_path": "/some/file.pdf"}

    async def test_never_started_returns_fresh(self):
        graph = MagicMock()
        graph.aget_state = AsyncMock(return_value=make_snapshot(values={}, next_nodes=()))
        result = await _resolve_input(graph, "/f.pdf", {}, force=False)
        assert result == {"file_path": "/f.pdf"}

    async def test_interrupted_returns_none(self):
        graph = MagicMock()
        graph.aget_state = AsyncMock(
            return_value=make_snapshot(values={"some": "state"}, next_nodes=("pending_node",))
        )
        result = await _resolve_input(graph, "/f.pdf", {}, force=False)
        assert result is None

    async def test_completed_returns_fresh(self):
        graph = MagicMock()
        graph.aget_state = AsyncMock(
            return_value=make_snapshot(values={"some": "state"}, next_nodes=())
        )
        result = await _resolve_input(graph, "/f.pdf", {}, force=False)
        assert result == {"file_path": "/f.pdf"}


class TestRunExtraction:
    async def test_happy_path_completes(self, tmp_path):
        job_id = "happy-job"
        file_path = str(tmp_path / "test.pdf")
        (tmp_path / "test.pdf").write_bytes(b"fake")
        _pre_seed_job(job_id)

        final_snap = make_snapshot(values={
            "hierarchical_document_tree": {
                "document_type": "baseline_core",
                "extraction_warnings": [],
                "structured_payload": [],
            },
            "total_pages": 1,
        })
        graph = _make_graph_with_stream(
            [{"native_extractor": {}}, {"hierarchy_node": {}}],
            final_snap,
        )

        await run_extraction(job_id, file_path, graph, langfuse=None)

        job = jobs[job_id]
        assert job.status == "completed"
        assert job.result is not None
        assert job.total_pages == 1
        assert job.document_type == "baseline_core"
        assert job.warnings == []
        assert len(job.events) == 2

    async def test_happy_path_deletes_temp_file(self, tmp_path):
        job_id = "del-job"
        file_path = str(tmp_path / "test.pdf")
        (tmp_path / "test.pdf").write_bytes(b"fake")
        _pre_seed_job(job_id)

        final_snap = make_snapshot(values={
            "hierarchical_document_tree": {
                "document_type": "baseline_core",
                "extraction_warnings": [],
                "structured_payload": [],
            },
            "total_pages": 1,
        })
        graph = _make_graph_with_stream([], final_snap)
        await run_extraction(job_id, file_path, graph, langfuse=None)

        from pathlib import Path
        assert not Path(file_path).exists()

    async def test_exception_path_fails_job(self, tmp_path):
        job_id = "fail-job"
        file_path = str(tmp_path / "test.pdf")
        (tmp_path / "test.pdf").write_bytes(b"fake")
        _pre_seed_job(job_id)

        async def _error_stream(*args, **kwargs):
            raise RuntimeError("boom")
            yield  # make it an async generator

        graph = MagicMock()
        graph.stream = _error_stream
        graph.aget_state = AsyncMock(return_value=make_snapshot())

        await run_extraction(job_id, file_path, graph, langfuse=None)

        job = jobs[job_id]
        assert job.status == "failed"
        assert job.error == "boom"

    async def test_exception_path_deletes_temp_file(self, tmp_path):
        job_id = "fail-del"
        file_path = str(tmp_path / "test.pdf")
        (tmp_path / "test.pdf").write_bytes(b"fake")
        _pre_seed_job(job_id)

        async def _error_stream(*args, **kwargs):
            raise RuntimeError("oops")
            yield

        graph = MagicMock()
        graph.stream = _error_stream
        graph.aget_state = AsyncMock(return_value=make_snapshot())

        await run_extraction(job_id, file_path, graph, langfuse=None)

        from pathlib import Path
        assert not Path(file_path).exists()

    async def test_langfuse_none_no_attribute_error(self, tmp_path):
        job_id = "lf-none"
        file_path = str(tmp_path / "test.pdf")
        (tmp_path / "test.pdf").write_bytes(b"fake")
        _pre_seed_job(job_id)

        final_snap = make_snapshot(values={
            "hierarchical_document_tree": {
                "document_type": "baseline_core",
                "extraction_warnings": [],
                "structured_payload": [],
            },
            "total_pages": 1,
        })
        graph = _make_graph_with_stream([], final_snap)
        # Should not raise AttributeError
        await run_extraction(job_id, file_path, graph, langfuse=None)
        assert jobs[job_id].status == "completed"
