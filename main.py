import os
import sys
import asyncio
import json
from dotenv import load_dotenv
from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.graph import build_app
from src.utils.pdf_utils import hash_file

load_dotenv()

# Graceful degradation: tracing only activates when both keys are present.
# Absent keys → pipeline runs unchanged, no import error, no crash.
_LANGFUSE_ENABLED = bool(
    os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
)
_langfuse = Langfuse() if _LANGFUSE_ENABLED else None


async def main():
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("CRITICAL ENVIRONMENT ERROR: ANTHROPIC_API_KEY environment variable missing.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("EXECUTION ERROR: Missing file path. Usage: uv run main.py <path_to_pdf>")
        sys.exit(1)

    target_pdf = sys.argv[1]
    pdf_hash = hash_file(target_pdf)
    print(f"Initializing extraction pipeline for: {target_pdf} (thread: {pdf_hash[:8]}...)")

    # Conditionally inject the Langfuse callback — single graph execution path.
    callbacks = [CallbackHandler()] if _LANGFUSE_ENABLED else []
    config = {"configurable": {"thread_id": pdf_hash}}
    if callbacks:
        config["callbacks"] = callbacks

    if _LANGFUSE_ENABLED:
        try:
            with _langfuse.start_as_current_span(
                name=f"PDFScout — {os.path.basename(target_pdf)}",
            ) as span:
                # propagate_attributes is the v4 API for setting session_id and
                # other trace-level fields on this span and all child observations.
                # session_id=pdf_hash groups all runs for the same PDF in the
                # Langfuse Sessions view (trace_context merge is broken in v4,
                # see plans/20260530_2026-langfuse-integration.md).
                with propagate_attributes(session_id=pdf_hash):
                    async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
                        app = build_app(checkpointer)
                        async for event in app.stream({"file_path": target_pdf}, config):
                            for node_name in event:
                                print(f"[GRAPH] Node '{node_name}' completed.")
                        final_state = await app.get_state(config)

                # Post-run metadata enrichment — inside the with span block so
                # the span is still open, outside propagate_attributes since
                # span.update() targets this span only, not children.
                # Langfuse v4 coerces metadata values to str (max 200 chars);
                # use "\n".join() for lists rather than passing them raw.
                state_values = final_state.values if final_state else {}
                tree_result = state_values.get("hierarchical_document_tree")
                extraction_warnings = (
                    tree_result.get("extraction_warnings", []) if tree_result else []
                )
                span.update(metadata={
                    "file": os.path.basename(target_pdf),
                    "pdf_hash": pdf_hash,
                    "document_type": tree_result.get("document_type") if tree_result else "",
                    "total_pages": str(state_values.get("total_pages", "")),
                    "extraction_warnings": "\n".join(extraction_warnings),
                })
            # ← with __exit__ fires here: span end-time is recorded and enqueued
        finally:
            # shutdown() runs AFTER with __exit__ so the parent span end-event
            # is already in the queue and gets sent along with child spans.
            # Guard against None in case Langfuse() construction failed.
            # No manual atexit: SDK registers its own; a second one risks a
            # double-shutdown hang (confirmed Langfuse bug #6515).
            if _langfuse:
                _langfuse.shutdown()
    else:
        async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
            app = build_app(checkpointer)
            async for event in app.stream({"file_path": target_pdf}, config):
                for node_name in event:
                    print(f"[GRAPH] Node '{node_name}' completed.")
            final_state = await app.get_state(config)
        tree_result = final_state.values.get("hierarchical_document_tree") if final_state else None

    if tree_result and tree_result.get("extraction_warnings"):
        print("\nWARNINGS:")
        for w in tree_result["extraction_warnings"]:
            print(f"  ! {w}")

    print("\nExtraction complete. Output tree:\n")
    print(json.dumps(tree_result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
