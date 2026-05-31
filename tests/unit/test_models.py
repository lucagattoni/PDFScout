from datetime import datetime, timezone

from src.api.jobs import JobRecord
from src.api.models import HealthResponse, JobResponse
from src.config import FALLBACK_DOC_TYPE, MODEL, SUPPORTED_DOC_TYPES


class TestJobResponseFromRecord:
    def test_all_fields_mapped(self):
        now = datetime.now(timezone.utc)
        record = JobRecord(
            job_id="abc123",
            file_name="test.pdf",
            created_at=now,
            status="completed",
            completed_at=now,
            total_pages=5,
            document_type="invoice",
            warnings=["w1"],
            error=None,
            result={"key": "val"},
            events=["[GRAPH] done"],
        )
        response = JobResponse.from_record(record)
        assert response.job_id == "abc123"
        assert response.file_name == "test.pdf"
        assert response.status == "completed"
        assert response.created_at == now
        assert response.completed_at == now
        assert response.total_pages == 5
        assert response.document_type == "invoice"
        assert response.warnings == ["w1"]
        assert response.error is None
        assert response.result == {"key": "val"}
        assert response.events == ["[GRAPH] done"]

    def test_queued_defaults(self):
        now = datetime.now(timezone.utc)
        record = JobRecord(job_id="xyz", file_name="f.pdf", created_at=now)
        response = JobResponse.from_record(record)
        assert response.status == "queued"
        assert response.completed_at is None
        assert response.total_pages is None
        assert response.result is None
        assert response.warnings == []
        assert response.events == []


class TestHealthResponse:
    def test_instantiates(self):
        h = HealthResponse(
            status="ok",
            model=MODEL,
            supported_doc_types=sorted(SUPPORTED_DOC_TYPES),
            fallback_doc_type=FALLBACK_DOC_TYPE,
            langfuse_enabled=False,
        )
        assert h.status == "ok"
        assert h.model == MODEL
