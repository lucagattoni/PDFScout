from datetime import UTC, datetime
from unittest.mock import patch

import src.api.jobs as job_module
from src.api.jobs import JobRecord, jobs


class TestGetJob:
    async def test_existing_job_returns_200(self, api_client):
        jobs["job-001"] = JobRecord(
            job_id="job-001", file_name="test.pdf", created_at=datetime.now(UTC)
        )
        response = await api_client.get("/jobs/job-001")
        assert response.status_code == 200
        assert response.json()["job_id"] == "job-001"

    async def test_unknown_job_returns_404(self, api_client):
        response = await api_client.get("/jobs/does-not-exist")
        assert response.status_code == 404


class TestDeleteJob:
    async def test_delete_completed_job_returns_204(self, api_client):
        jobs["job-done"] = JobRecord(
            job_id="job-done",
            file_name="test.pdf",
            created_at=datetime.now(UTC),
            status="completed",
        )
        with patch("pathlib.Path.unlink"):
            response = await api_client.delete("/jobs/job-done")
        assert response.status_code == 204
        assert "job-done" not in jobs

    async def test_delete_completed_calls_unlink(self, api_client):
        jobs["job-del"] = JobRecord(
            job_id="job-del",
            file_name="test.pdf",
            created_at=datetime.now(UTC),
            status="completed",
        )
        with patch("pathlib.Path.unlink") as mock_unlink:
            await api_client.delete("/jobs/job-del")
        mock_unlink.assert_called_once()

    async def test_delete_unknown_returns_404(self, api_client):
        response = await api_client.delete("/jobs/no-such-job")
        assert response.status_code == 404

    async def test_delete_running_returns_409(self, api_client):
        jobs["job-run"] = JobRecord(
            job_id="job-run",
            file_name="test.pdf",
            created_at=datetime.now(UTC),
            status="running",
        )
        response = await api_client.delete("/jobs/job-run")
        assert response.status_code == 409

    async def test_delete_queued_returns_409(self, api_client):
        jobs["job-q"] = JobRecord(
            job_id="job-q",
            file_name="test.pdf",
            created_at=datetime.now(UTC),
            status="queued",
        )
        response = await api_client.delete("/jobs/job-q")
        assert response.status_code == 409


class TestJobStorePersistence:
    async def test_job_survives_reinit(self, tmp_path):
        """Completed job written to SQLite is reloaded after re-init (simulates restart)."""
        db_path = str(tmp_path / "jobs.db")
        record = JobRecord(
            job_id="persist-001",
            file_name="doc.pdf",
            created_at=datetime.now(UTC),
            status="completed",
        )
        try:
            await job_module.init(db_path)
            await job_module.save(record)
            job_module.jobs.clear()          # lose in-memory state
            await job_module.init(db_path)   # reload from SQLite
            assert "persist-001" in job_module.jobs
            reloaded = job_module.jobs["persist-001"]
            assert reloaded.status == "completed"
            assert reloaded.file_name == "doc.pdf"
        finally:
            job_module.jobs.clear()
            job_module._db_path = ""

    async def test_running_job_marked_failed_on_reinit(self, tmp_path):
        """Jobs still running at restart are marked failed on re-init."""
        db_path = str(tmp_path / "jobs.db")
        record = JobRecord(
            job_id="was-running",
            file_name="doc.pdf",
            created_at=datetime.now(UTC),
            status="running",
        )
        try:
            await job_module.init(db_path)
            await job_module.save(record)
            job_module.jobs.clear()
            await job_module.init(db_path)
            assert job_module.jobs["was-running"].status == "failed"
        finally:
            job_module.jobs.clear()
            job_module._db_path = ""
