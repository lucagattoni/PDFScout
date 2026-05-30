from datetime import datetime, timezone
from pathlib import Path

from src.api.jobs import jobs
from src.utils.tracing import tracing_span


async def _resolve_input(graph, file_path: str, config: dict, force: bool) -> dict | None:
    """Returns graph input for stream(): None to resume an interrupted run, or
    {"file_path": ...} to start fresh. force=True always starts fresh."""
    if force:
        return {"file_path": file_path}
    snapshot = await graph.aget_state(config)
    # snapshot.next is non-empty when a run was interrupted mid-execution.
    # Empty tuple means the run completed or never started — start fresh.
    if snapshot.values and snapshot.next:
        return None
    return {"file_path": file_path}


async def run_extraction(
    job_id: str,
    file_path: str,
    graph,
    langfuse,
    force: bool = False,
) -> None:
    job = jobs[job_id]
    job.status = "running"
    try:
        config = {"configurable": {"thread_id": job_id}}
        if langfuse:
            from langfuse.langchain import CallbackHandler
            config["callbacks"] = [CallbackHandler()]

        input_data = await _resolve_input(graph, file_path, config, force)

        async with tracing_span(langfuse, job.file_name, job_id) as span:
            async for event in graph.stream(input_data, config):
                for node_name in event:
                    job.events.append(f"[GRAPH] Node '{node_name}' completed.")

            final_state = await graph.aget_state(config)
            tree = final_state.values.get("hierarchical_document_tree")
            job.result = tree
            job.warnings = tree.get("extraction_warnings", []) if tree else []
            job.document_type = tree.get("document_type") if tree else None
            job.total_pages = final_state.values.get("total_pages")

            if span:
                span.update(metadata={
                    "file": job.file_name,
                    "pdf_hash": job_id,
                    "document_type": job.document_type or "",
                    "total_pages": str(job.total_pages or ""),
                    "extraction_warnings": "\n".join(job.warnings),
                })

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = datetime.now(timezone.utc)
    finally:
        Path(file_path).unlink(missing_ok=True)
