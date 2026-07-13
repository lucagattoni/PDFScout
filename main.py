import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.graph import build_app
from src.utils.pdf_utils import hash_file
from src.utils.tracing import tracing_span
from src.utils.usage import summarize_usage

load_dotenv()

_LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
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

    callbacks = [CallbackHandler()] if _LANGFUSE_ENABLED else []
    config = {"configurable": {"thread_id": pdf_hash}}
    if callbacks:
        config["callbacks"] = callbacks

    tree_result = None
    usage_totals = summarize_usage([])
    try:
        async with tracing_span(
            _langfuse, f"PDFScout — {os.path.basename(target_pdf)}", pdf_hash
        ) as span:
            async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
                app = build_app(checkpointer)
                async for event in app.astream({"file_path": target_pdf}, config):
                    for node_name in event:
                        print(f"[GRAPH] Node '{node_name}' completed.")
                final_state = await app.aget_state(config)
            state_values = final_state.values if final_state else {}
            tree_result = state_values.get("hierarchical_document_tree")
            extraction_warnings = tree_result.get("extraction_warnings", []) if tree_result else []
            usage_totals = summarize_usage(state_values.get("usage_log", []) or [])
            if span:
                span.update(
                    metadata={
                        "file": os.path.basename(target_pdf),
                        "pdf_hash": pdf_hash,
                        "document_type": tree_result.get("document_type") if tree_result else "",
                        "total_pages": str(state_values.get("total_pages", "")),
                        "extraction_warnings": "\n".join(extraction_warnings),
                        **{f"usage_{k}": v for k, v in usage_totals.items()},
                    }
                )
    finally:
        if _langfuse:
            _langfuse.shutdown()

    if tree_result and tree_result.get("extraction_warnings"):
        print("\nWARNINGS:")
        for w in tree_result["extraction_warnings"]:
            print(f"  ! {w}")

    if usage_totals["api_calls"]:
        print(
            f"\nUSAGE: {usage_totals['api_calls']} API calls | "
            f"input {usage_totals['input_tokens']} | "
            f"output {usage_totals['output_tokens']} | "
            f"cache_read {usage_totals['cache_read_input_tokens']} | "
            f"cache_write {usage_totals['cache_creation_input_tokens']}",
            file=sys.stderr,
        )

    print("\nExtraction complete. Output tree:\n")
    print(json.dumps(tree_result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
