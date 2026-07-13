from langgraph.types import Send

from src.graph import build_app, burst_dispatcher_node, dispatch_pages


class TestBurstDispatcherNode:
    def test_retry_count_zero_returns_empty(self):
        result = burst_dispatcher_node({"retry_count": 0, "extraction_warnings": []})
        assert result == {}

    def test_retry_count_below_threshold_returns_empty(self):
        result = burst_dispatcher_node({"retry_count": 2, "extraction_warnings": []})
        assert result == {}

    def test_retry_count_at_threshold_adds_warning(self):
        result = burst_dispatcher_node({"retry_count": 3, "extraction_warnings": []})
        assert "extraction_warnings" in result
        assert len(result["extraction_warnings"]) == 1
        assert "page 1" in result["extraction_warnings"][0].lower()


class TestDispatchPages:
    def test_single_page_routes_to_coverage_auditor(self, sample_state):
        # 1-page docs skip the burst fan-out and go straight to the
        # completeness oracle (which precedes the hierarchy agent).
        state = {**sample_state, "total_pages": 1}
        result = dispatch_pages(state)
        assert result == "coverage_auditor"

    def test_multi_page_returns_send_objects(self, sample_state):
        state = {**sample_state, "total_pages": 3}
        result = dispatch_pages(state)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(s, Send) for s in result)

    def test_send_targets_parser_worker(self, sample_state):
        state = {**sample_state, "total_pages": 3}
        sends = dispatch_pages(state)
        assert all(s.node == "parser_worker" for s in sends)

    def test_send_carries_correct_page_numbers(self, sample_state):
        state = {**sample_state, "total_pages": 3}
        sends = dispatch_pages(state)
        pages = [s.arg["current_page"] for s in sends]
        assert pages == [2, 3]


class TestBuildApp:
    def test_compiles_without_error(self):
        app = build_app(checkpointer=None)
        assert app is not None

    def test_exposes_all_node_names(self):
        app = build_app(checkpointer=None)
        expected = {
            "native_extractor",
            "classifier",
            "pioneer_parser",
            "retry_node",
            "burst_dispatcher",
            "parser_worker",
            "coverage_auditor",
            "hierarchy_node",
        }
        assert expected.issubset(set(app.nodes.keys()))
