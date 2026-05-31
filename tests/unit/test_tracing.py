from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from src.utils.tracing import tracing_span


class TestTracingSpan:
    async def test_none_langfuse_yields_none(self):
        async with tracing_span(None, "test_op", "sess-123") as span:
            assert span is None

    async def test_active_langfuse_yields_span(self):
        mock_span = MagicMock()
        mock_langfuse = MagicMock()

        @contextmanager
        def fake_start_as_current_span(name):
            yield mock_span

        mock_langfuse.start_as_current_span = fake_start_as_current_span

        @contextmanager
        def fake_propagate(session_id):
            yield

        with patch("langfuse.propagate_attributes", fake_propagate):
            async with tracing_span(mock_langfuse, "my_op", "sess-abc") as span:
                assert span is mock_span

    async def test_active_langfuse_propagates_session_id(self):
        mock_span = MagicMock()
        mock_langfuse = MagicMock()
        captured_kwargs = {}

        @contextmanager
        def fake_start_as_current_span(name):
            yield mock_span

        mock_langfuse.start_as_current_span = fake_start_as_current_span

        @contextmanager
        def fake_propagate(**kwargs):
            captured_kwargs.update(kwargs)
            yield

        with patch("langfuse.propagate_attributes", fake_propagate):
            async with tracing_span(mock_langfuse, "my_op", "sess-xyz"):
                pass

        assert captured_kwargs.get("session_id") == "sess-xyz"
