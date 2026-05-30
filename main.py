import os
import sys
import asyncio
import json
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.graph import build_app
from src.utils.pdf_utils import hash_file


async def main():
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("CRITICAL ENVIRONMENT ERROR: ANTHROPIC_API_KEY environment variable missing.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("EXECUTION ERROR: Missing file path. Usage: uv run main.py <path_to_pdf>")
        sys.exit(1)

    target_pdf = sys.argv[1]
    pdf_hash = hash_file(target_pdf)
    config = {"configurable": {"thread_id": pdf_hash}}
    initial_inputs = {"file_path": target_pdf}

    print(f"Initializing extraction pipeline for: {target_pdf} (thread: {pdf_hash[:8]}...)")

    async with AsyncSqliteSaver.from_conn_string("state_checkpoint.db") as checkpointer:
        app = build_app(checkpointer)

        async for event in app.stream(initial_inputs, config):
            for node_name in event:
                print(f"[GRAPH] Node '{node_name}' completed.")

        final_state = await app.get_state(config)
        tree_result = final_state.values.get("hierarchical_document_tree")

    if tree_result and tree_result.get("extraction_warnings"):
        print("\nWARNINGS:")
        for w in tree_result["extraction_warnings"]:
            print(f"  ! {w}")

    print("\nExtraction complete. Output tree:\n")
    print(json.dumps(tree_result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
