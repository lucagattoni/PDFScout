from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from src.api.jobs import JobRecord


class HealthResponse(BaseModel):
    status: str
    model: str
    supported_doc_types: list[str]
    fallback_doc_type: str
    langfuse_enabled: bool


class JobResponse(BaseModel):
    job_id: str
    file_name: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    completed_at: datetime | None = None
    total_pages: int | None = None
    document_type: str | None = None
    warnings: list[str] = []
    error: str | None = None
    result: dict[str, Any] | None = None
    events: list[str] = []

    @classmethod
    def from_record(cls, record: JobRecord) -> JobResponse:
        return cls(
            job_id=record.job_id,
            file_name=record.file_name,
            status=record.status,
            created_at=record.created_at,
            completed_at=record.completed_at,
            total_pages=record.total_pages,
            document_type=record.document_type,
            warnings=record.warnings,
            error=record.error,
            result=record.result,
            events=record.events,
        )
