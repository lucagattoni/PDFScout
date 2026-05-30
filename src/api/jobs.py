from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class JobRecord:
    job_id: str
    file_name: str
    created_at: datetime
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    completed_at: datetime | None = None
    total_pages: int | None = None
    document_type: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    result: dict | None = None
    events: list[str] = field(default_factory=list)


jobs: dict[str, JobRecord] = {}
