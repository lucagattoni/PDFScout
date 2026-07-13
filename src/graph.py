from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from src.config import VALIDATION_MAX_RETRIES
from src.edges import pioneer_validation_route
from src.nodes.classifier_node import classifier_node
from src.nodes.coverage_node import coverage_auditor_node
from src.nodes.extractor_node import native_extractor_node
from src.nodes.hierarchy_node import layout_hierarchy_agent_node
from src.nodes.retry_node import retry_incrementor_node
from src.nodes.worker_node import burst_worker_node, window_parser_node
from src.state import PDFParserState


def burst_dispatcher_node(state: PDFParserState) -> dict[str, Any]:
    """Passthrough node. Writes a warning if pioneer validation degraded after max retries."""
    if state["retry_count"] >= VALIDATION_MAX_RETRIES:
        return {
            "extraction_warnings": [
                f"Pioneer page (page 1) failed schema validation after {VALIDATION_MAX_RETRIES} retries. "
                "Page 1 data may be incomplete or structurally invalid."
            ]
        }
    return {}


def dispatch_pages(state: PDFParserState) -> list[Send] | str:
    """Dispatches pages 2-N as concurrent Send tasks. Single-page docs skip to hierarchy."""
    if state["total_pages"] < 2:
        return "coverage_auditor"
    return [
        Send("parser_worker", {**state, "current_page": page, "last_validation_error": None})
        for page in range(2, state["total_pages"] + 1)
    ]


def build_app(checkpointer=None):
    """Factory — pass a checkpointer instance, or None for an in-memory (test) graph."""
    workflow = StateGraph(PDFParserState)

    workflow.add_node("native_extractor", native_extractor_node)
    workflow.add_node("classifier", classifier_node)
    workflow.add_node("pioneer_parser", window_parser_node)  # page 1 — has pioneer routing
    workflow.add_node("retry_node", retry_incrementor_node)
    workflow.add_node("burst_dispatcher", burst_dispatcher_node)
    workflow.add_node("parser_worker", burst_worker_node)  # pages 2-N — inline validation retry
    workflow.add_node("coverage_auditor", coverage_auditor_node)  # native-text completeness oracle
    workflow.add_node("hierarchy_node", layout_hierarchy_agent_node)

    workflow.add_edge(START, "native_extractor")
    workflow.add_edge("native_extractor", "classifier")
    workflow.add_edge("classifier", "pioneer_parser")

    workflow.add_conditional_edges(
        "pioneer_parser",
        pioneer_validation_route,
        {"retry_node": "retry_node", "burst_dispatcher": "burst_dispatcher"},
    )
    workflow.add_edge("retry_node", "pioneer_parser")

    workflow.add_conditional_edges(
        "burst_dispatcher", dispatch_pages, ["parser_worker", "coverage_auditor"]
    )
    workflow.add_edge("parser_worker", "coverage_auditor")
    workflow.add_edge("coverage_auditor", "hierarchy_node")
    workflow.add_edge("hierarchy_node", END)

    return workflow.compile(checkpointer=checkpointer)
