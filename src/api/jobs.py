import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import aiosqlite


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
_db_path: str = ""


async def init(db_path: str) -> None:
    """Create table, mark interrupted jobs as failed, and load records into memory."""
    global _db_path
    _db_path = db_path
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                job_id        TEXT PRIMARY KEY,
                file_name     TEXT NOT NULL,
                status        TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                completed_at  TEXT,
                total_pages   INTEGER,
                document_type TEXT,
                warnings      TEXT NOT NULL DEFAULT '[]',
                error         TEXT,
                result        TEXT,
                events        TEXT NOT NULL DEFAULT '[]'
            )"""
        )
        # Jobs still "running" or "queued" after restart were interrupted — mark failed.
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE jobs SET status='failed', error='Server restart interrupted this job.', "
            "completed_at=? WHERE status IN ('running','queued')",
            (now,),
        )
        await db.commit()
        async with db.execute("SELECT * FROM jobs") as cur:
            async for row in cur:
                r = _from_row(row)
                jobs[r.job_id] = r


def _from_row(row: tuple) -> JobRecord:
    (
        job_id,
        file_name,
        status,
        created_at,
        completed_at,
        total_pages,
        document_type,
        warnings,
        error,
        result,
        events,
    ) = row
    return JobRecord(
        job_id=job_id,
        file_name=file_name,
        status=status,
        created_at=datetime.fromisoformat(created_at),
        completed_at=datetime.fromisoformat(completed_at) if completed_at else None,
        total_pages=total_pages,
        document_type=document_type,
        warnings=json.loads(warnings),
        error=error,
        result=json.loads(result) if result else None,
        events=json.loads(events),
    )


async def save(record: JobRecord) -> None:
    """Upsert record to the in-memory dict and DB. No-op when DB is not initialised."""
    jobs[record.job_id] = record
    if not _db_path:
        return
    async with aiosqlite.connect(_db_path) as db:
        await db.execute(
            """INSERT OR REPLACE INTO jobs
               (job_id, file_name, status, created_at, completed_at, total_pages,
                document_type, warnings, error, result, events)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.job_id,
                record.file_name,
                record.status,
                record.created_at.isoformat(),
                record.completed_at.isoformat() if record.completed_at else None,
                record.total_pages,
                record.document_type,
                json.dumps(record.warnings),
                record.error,
                json.dumps(record.result) if record.result is not None else None,
                json.dumps(record.events),
            ),
        )
        await db.commit()


async def remove(job_id: str) -> None:
    """Remove from in-memory dict and DB. No-op when DB is not initialised."""
    jobs.pop(job_id, None)
    if not _db_path:
        return
    async with aiosqlite.connect(_db_path) as db:
        await db.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        await db.commit()
