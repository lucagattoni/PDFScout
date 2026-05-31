from datetime import UTC, datetime

from src.api.jobs import JobRecord, jobs


def _pdf_upload(pdf_bytes: bytes, filename: str = "test.pdf"):
    return {"file": (filename, pdf_bytes, "application/pdf")}


class TestExtractEndpoint:
    async def test_valid_pdf_returns_202(self, api_client, minimal_pdf_bytes):
        response = await api_client.post("/extract", files=_pdf_upload(minimal_pdf_bytes))
        assert response.status_code == 202

    async def test_valid_pdf_has_job_id(self, api_client, minimal_pdf_bytes):
        body = (await api_client.post("/extract", files=_pdf_upload(minimal_pdf_bytes))).json()
        assert "job_id" in body
        assert len(body["job_id"]) == 64

    async def test_valid_pdf_status_queued(self, api_client, minimal_pdf_bytes):
        body = (await api_client.post("/extract", files=_pdf_upload(minimal_pdf_bytes))).json()
        assert body["status"] in ("queued", "running", "completed")

    async def test_wrong_content_type_returns_400(self, api_client):
        response = await api_client.post(
            "/extract", files={"file": ("test.txt", b"not a pdf", "text/plain")}
        )
        assert response.status_code == 400

    async def test_oversized_file_returns_413(self, api_client):
        big_bytes = b"\x00" * (33 * 1024 * 1024)
        response = await api_client.post("/extract", files=_pdf_upload(big_bytes))
        assert response.status_code == 413

    async def test_same_file_twice_returns_same_job_id(self, api_client, minimal_pdf_bytes):
        r1 = (await api_client.post("/extract", files=_pdf_upload(minimal_pdf_bytes))).json()
        r2 = (await api_client.post("/extract", files=_pdf_upload(minimal_pdf_bytes))).json()
        assert r1["job_id"] == r2["job_id"]

    async def test_existing_queued_no_force_returns_existing(self, api_client, minimal_pdf_bytes):
        import hashlib

        job_id = hashlib.sha256(minimal_pdf_bytes).hexdigest()
        jobs[job_id] = JobRecord(
            job_id=job_id, file_name="test.pdf", created_at=datetime.now(UTC), status="queued"
        )
        body = (await api_client.post("/extract", files=_pdf_upload(minimal_pdf_bytes))).json()
        assert body["job_id"] == job_id
        assert body["status"] == "queued"

    async def test_existing_running_no_force_returns_existing(self, api_client, minimal_pdf_bytes):
        import hashlib

        job_id = hashlib.sha256(minimal_pdf_bytes).hexdigest()
        jobs[job_id] = JobRecord(
            job_id=job_id, file_name="test.pdf", created_at=datetime.now(UTC), status="running"
        )
        body = (await api_client.post("/extract", files=_pdf_upload(minimal_pdf_bytes))).json()
        assert body["job_id"] == job_id
        assert body["status"] == "running"

    async def test_existing_completed_no_force_returns_existing(
        self, api_client, minimal_pdf_bytes
    ):
        import hashlib

        job_id = hashlib.sha256(minimal_pdf_bytes).hexdigest()
        jobs[job_id] = JobRecord(
            job_id=job_id, file_name="test.pdf", created_at=datetime.now(UTC), status="completed"
        )
        body = (await api_client.post("/extract", files=_pdf_upload(minimal_pdf_bytes))).json()
        assert body["status"] == "completed"

    async def test_existing_completed_force_creates_new(self, api_client, minimal_pdf_bytes):
        import hashlib

        job_id = hashlib.sha256(minimal_pdf_bytes).hexdigest()
        jobs[job_id] = JobRecord(
            job_id=job_id, file_name="test.pdf", created_at=datetime.now(UTC), status="completed"
        )
        body = (
            await api_client.post("/extract?force=true", files=_pdf_upload(minimal_pdf_bytes))
        ).json()
        assert body["status"] in ("queued", "running", "completed")

    async def test_existing_running_force_returns_409(self, api_client, minimal_pdf_bytes):
        import hashlib

        job_id = hashlib.sha256(minimal_pdf_bytes).hexdigest()
        jobs[job_id] = JobRecord(
            job_id=job_id, file_name="test.pdf", created_at=datetime.now(UTC), status="running"
        )
        response = await api_client.post(
            "/extract?force=true", files=_pdf_upload(minimal_pdf_bytes)
        )
        assert response.status_code == 409

    async def test_existing_queued_force_returns_409(self, api_client, minimal_pdf_bytes):
        import hashlib

        job_id = hashlib.sha256(minimal_pdf_bytes).hexdigest()
        jobs[job_id] = JobRecord(
            job_id=job_id, file_name="test.pdf", created_at=datetime.now(UTC), status="queued"
        )
        response = await api_client.post(
            "/extract?force=true", files=_pdf_upload(minimal_pdf_bytes)
        )
        assert response.status_code == 409
