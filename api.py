import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from langfuse import Langfuse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.api.jobs import JobRecord, jobs
from src.api.models import HealthResponse, JobResponse
from src.api.runner import run_extraction
from src.config import FALLBACK_DOC_TYPE, MODEL, SUPPORTED_DOC_TYPES
from src.graph import build_app

load_dotenv()

_API_ROOT = Path(__file__).parent
_UPLOAD_DIR = _API_ROOT / "tmp" / "uploads"
_CHECKPOINT_DB = str(_API_ROOT / "api_checkpoint.db")
_MAX_UPLOAD_BYTES = 32 * 1024 * 1024

_LANGFUSE_ENABLED = bool(
    os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    langfuse = Langfuse() if _LANGFUSE_ENABLED else None
    async with AsyncSqliteSaver.from_conn_string(_CHECKPOINT_DB) as checkpointer:
        app.state.graph = build_app(checkpointer)
        app.state.langfuse = langfuse
        yield
    if langfuse:
        langfuse.shutdown()


app = FastAPI(title="PDFScout API", version="0.3.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model=MODEL,
        supported_doc_types=sorted(SUPPORTED_DOC_TYPES),
        fallback_doc_type=FALLBACK_DOC_TYPE,
        langfuse_enabled=_LANGFUSE_ENABLED,
    )


@app.post("/extract", response_model=JobResponse, status_code=202)
async def extract(file: UploadFile, force: bool = False) -> JobResponse:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF (content-type: application/pdf).")

    content = await file.read()

    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 32 MB limit.")

    job_id = hashlib.sha256(content).hexdigest()

    existing = jobs.get(job_id)
    if existing:
        if existing.status in ("queued", "running"):
            if force:
                raise HTTPException(
                    status_code=409,
                    detail=f"Job is currently {existing.status}. Wait for it to finish before using force=true.",
                )
            return JobResponse.from_record(existing)
        if not force:
            return JobResponse.from_record(existing)
        del jobs[job_id]

    new_record = JobRecord(
        job_id=job_id,
        file_name=file.filename or "upload.pdf",
        created_at=datetime.now(timezone.utc),
    )
    existing = jobs.setdefault(job_id, new_record)
    if existing is not new_record:
        return JobResponse.from_record(existing)

    tmp_path = _UPLOAD_DIR / f"{job_id}.pdf"
    await asyncio.to_thread(tmp_path.write_bytes, content)

    asyncio.create_task(
        run_extraction(job_id, str(tmp_path), app.state.graph, app.state.langfuse, force)
    )

    return JobResponse.from_record(new_record)


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JobResponse.from_record(job)


@app.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.status in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete a {job.status} job. Wait for it to complete first.",
        )
    del jobs[job_id]
    ((_UPLOAD_DIR / f"{job_id}.pdf")).unlink(missing_ok=True)
